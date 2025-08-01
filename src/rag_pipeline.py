import os
import logging
import sqlite3
from sentence_transformers import SentenceTransformer

from .config import RAGConfig
from .llm_gemini import GeminiLLM
from . import file_extractor
from . import text_processing
from . import vector_store
from . import sql_database
from . import utils

logger = logging.getLogger(__name__)

class RAGPipeline:
    def __init__(self, config_path="config.ini"):
        self.config = RAGConfig(config_path)

        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.config.log_file),
                logging.StreamHandler()
            ]
        )

        logger.info("Initializing RAG Pipeline...")

        try:
            self.encoder_model = SentenceTransformer(self.config.encoder_model, device=self.config.device)
            logger.info("Embedding model loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading embedding model: {e}", exc_info=True)
            raise

        self.llm = GeminiLLM(self.config)

        self.db_conn = None
        self.db_cursor = None
        self._connect_db()

        self.global_index = None
        self.global_chunks = None
        self.table_metadata = {}

        self.embedding_dim = self.encoder_model.get_sentence_embedding_dimension()
        self._load_global_vector_store()

    def _connect_db(self):
        try:
            self.db_conn = sqlite3.connect(self.config.sqlite_db_path, check_same_thread=False)
            self.db_cursor = self.db_conn.cursor()
            logger.info(f"Connected to SQLite database at '{self.config.sqlite_db_path}'")
        except sqlite3.Error as e:
            logger.error(f"Error connecting to SQLite database: {e}", exc_info=True)
            raise ConnectionError(f"Failed to connect to SQLite DB: {e}") from e

    def _load_global_vector_store(self):
        """Loads the global vector index and chunks from disk."""
        logger.info("Loading global vector store...")
        self.global_index, self.global_chunks = vector_store.load_index_and_chunks(
            self.config.index_dir, "global_index", self.embedding_dim
        )

    def process_documents(self):
        """
        Orchestrates the processing of all documents in the data directory.
        This includes:
        - Scanning for project folders.
        - Processing text files (PDF, PPTX) and building a global vector store.
        - Building a local vector store for each project.
        - Processing spreadsheets (CSV, XLSX) and using the local vector store for context
          to generate column metadata.
        """
        logger.info("Starting document processing...")
        data_dir = self.config.data_dir
        all_global_text_chunks = []

        # Clear existing in-memory data
        self.table_metadata = {}
        if self.config.sqlite_db_path == ":memory:" and self.db_cursor:
            logger.info("Clearing existing tables from in-memory database...")
            try:
                self.db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = self.db_cursor.fetchall()
                for table_tuple in tables:
                    self.db_cursor.execute(f'DROP TABLE IF EXISTS "{table_tuple[0]}"')
                self.db_conn.commit()
                logger.info(f"Dropped {len(tables)} tables.")
            except sqlite3.Error as e_drop:
                logger.error(f"Error dropping tables: {e_drop}")

        project_folders = [f for f in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, f))]
        if not project_folders:
            logger.warning(f"No project folders found in {data_dir}. Processing files in root directory.")
            project_folders = ['.']

        for project_name in project_folders:
            project_path = os.path.join(data_dir, project_name)
            logger.info(f"--- Processing Project: {project_name} ---")

            project_text_chunks = []
            files_in_project = os.listdir(project_path)

            # First pass: Process text files to build local context
            for file_name in files_in_project:
                file_path = os.path.join(project_path, file_name)
                file_ext = os.path.splitext(file_name)[1].lower()

                if file_ext in ['.pdf', '.pptx']:
                    logger.info(f"Extracting text from: {file_name}")
                    if file_ext == '.pdf':
                        content = file_extractor.extract_pdf(file_path, self.config)
                    else:
                        content = file_extractor.extract_pptx(file_path, self.config)

                    chunks = text_processing.chunk_content(content, self.config)
                    for chunk in chunks:
                        chunk['source_info']['project'] = project_name
                    project_text_chunks.extend(chunks)

            # Create and save the local vector store for this project
            if project_text_chunks:
                logger.info(f"Creating local vector store for project '{project_name}'...")
                local_index_name = utils.get_safe_filename(project_name)
                vector_store.create_and_save_index(
                    project_text_chunks, self.encoder_model, self.config.index_dir, local_index_name
                )

            all_global_text_chunks.extend(project_text_chunks)

            # Second pass: Process spreadsheets using the local context
            for file_name in files_in_project:
                file_path = os.path.join(project_path, file_name)
                file_ext = os.path.splitext(file_name)[1].lower()

                if file_ext in ['.csv', '.xlsx']:
                    logger.info(f"Processing spreadsheet: {file_name} with context from '{project_name}'")
                    if file_ext == '.xlsx':
                        tables = sql_database.extract_and_load_xlsx(
                            file_path, file_name, self.db_conn, self.db_cursor, self.llm, self.config, context=project_text_chunks
                        )
                    else: # .csv
                        tables = sql_database.extract_and_load_csv(
                            file_path, file_name, self.db_conn, self.db_cursor, self.llm, self.config, context=project_text_chunks
                        )
                    self.table_metadata.update(tables)

        # Create and save the global vector store
        if all_global_text_chunks:
            logger.info("Creating global vector store...")
            vector_store.create_and_save_index(
                all_global_text_chunks, self.encoder_model, self.config.index_dir, "global_index"
            )
            self._load_global_vector_store() # Reload into memory

        logger.info("--- Document Processing Complete ---")

    def run_query(self, query, chat_history):
        """
        Runs a query through the RAG pipeline.
        This includes:
        - Refining the query based on chat history.
        - Classifying the query as 'text', 'sql', or 'hybrid'.
        - Routing the query to the appropriate retrieval and generation pipeline.
        """
        logger.info(f"--- Running query: '{query[:100]}...' ---")

        refined_query = self.llm.refine_query_with_history(query, chat_history)
        logger.info(f"Refined query: '{refined_query[:100]}...'")

        classification = self.llm.classify_query(refined_query, self.table_metadata)

        if classification == 'text':
            return self._run_text_query(refined_query, chat_history)
        elif classification == 'sql':
            return self._run_sql_query(refined_query, chat_history)
        elif classification == 'hybrid':
            return self._run_hybrid_query(refined_query, chat_history)
        else:
            logger.warning(f"Unknown classification '{classification}'. Defaulting to text query.")
            return self._run_text_query(refined_query, chat_history)

    def _run_text_query(self, query, chat_history):
        logger.info("Running TEXT query pipeline...")
        retrieved_chunks = vector_store.query_index(
            query, self.global_index, self.global_chunks, self.encoder_model, self.config
        )

        if not retrieved_chunks:
            logger.warning("No relevant text chunks found for the query.")
            return "I could not find any relevant information in the text documents to answer your question."

        # Diagnostic logging
        logger.info(f"Retrieved {len(retrieved_chunks)} chunks for query: '{query}'")
        for i, chunk in enumerate(retrieved_chunks):
            logger.debug(f"  Chunk {i+1} (Score: {chunk['score']}):")
            logger.debug(f"    Source: {chunk.get('source_info', 'N/A')}")
            logger.debug(f"    Content: {chunk['content'][:150]}...")

        context = text_processing.aggregate_context(retrieved_chunks, self.config)
        logger.debug(f"Aggregated context sent to LLM:\n{context}")

        return self.llm.synthesize_answer(query, context, chat_history)

    def _run_sql_query(self, query, chat_history):
        logger.info("Running SQL query pipeline...")
        target_table = self.llm.identify_target_sql_table(query, self.table_metadata)
        logger.debug(f"Identified target table: {target_table}")

        if not target_table or target_table not in self.table_metadata:
            logger.warning("Could not identify a relevant spreadsheet table for the query.")
            return "I could not identify a relevant spreadsheet to answer your question."

        table_meta = self.table_metadata[target_table]
        sql_query = self.llm.generate_sql_query(query, target_table, table_meta)
        logger.debug(f"Generated SQL query: {sql_query}")

        if not sql_query:
            logger.warning("LLM failed to generate a SQL query.")
            return "I was unable to construct a SQL query to answer your question."

        sql_result, error = sql_database.execute_sql_query(self.db_conn, sql_query)

        if error:
            logger.error(f"SQL execution error: {error}")
            return f"I encountered an error while querying the database: {error}"

        logger.debug(f"SQL query result:\n{sql_result}")
        context = f"The following data was retrieved from the database table '{target_table}':\n\n{sql_result}"
        return self.llm.synthesize_answer(query, context, chat_history)

    def _run_hybrid_query(self, query, chat_history):
        logger.info("Running HYBRID query pipeline...")
        decomposed_queries = self.llm.decompose_hybrid_query(query)

        if not decomposed_queries or "text_query" not in decomposed_queries or "sql_query" not in decomposed_queries:
            logger.warning("Failed to decompose hybrid query. Defaulting to text query.")
            return self._run_text_query(query, chat_history)

        text_query = decomposed_queries["text_query"]
        sql_query_prompt = decomposed_queries["sql_query"]

        # Run text query part
        text_results = vector_store.query_index(
            text_query, self.global_index, self.global_chunks, self.encoder_model, self.config
        )
        text_context = text_processing.aggregate_context(text_results, self.config)

        # Run SQL query part
        target_table = self.llm.identify_target_sql_table(sql_query_prompt, self.table_metadata)
        sql_context = ""
        if target_table and target_table in self.table_metadata:
            table_meta = self.table_metadata[target_table]
            sql_query = self.llm.generate_sql_query(sql_query_prompt, target_table, table_meta)
            if sql_query:
                sql_result, error = sql_database.execute_sql_query(self.db_conn, sql_query)
                if not error:
                    sql_context = f"Data from table '{target_table}':\n{sql_result}"

        # Combine contexts and synthesize final answer
        combined_context = f"Information from text documents:\n{text_context}\n\nInformation from spreadsheets:\n{sql_context}"
        return self.llm.synthesize_answer(query, combined_context, chat_history)

    def __del__(self):
        if self.db_conn:
            self.db_conn.close()
