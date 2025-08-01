import os
import re
import logging
import json
import google.generativeai as genai
from .config import RAGConfig

logger = logging.getLogger(__name__)

class GeminiLLM:
    def __init__(self, config: RAGConfig):
        self.config = config
        self.api_key = config.gemini_api_key
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables or config file.")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.config.gemini_model)
        logger.info(f"Gemini LLM initialized with model: {self.config.gemini_model}")

    def _call_llm(self, prompt, temperature=0.1):
        """Calls the Gemini LLM and handles errors."""
        try:
            logger.debug(f"Calling Gemini with prompt: {prompt[:100]}...")
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    top_p=self.config.top_p,
                    max_output_tokens=self.config.max_output_tokens,
                )
            )

            if response.parts:
                return response.text
            else:
                logger.warning(f"Gemini response was empty or blocked. Finish reason: {response.prompt_feedback}")
                return None
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}", exc_info=True)
            return None

    def generate_column_metadata(self, df, file_name, sheet_name=None, context=None):
        """Generates column metadata using Gemini, with optional context from text files."""
        sample_data_str = df.head(3).to_string(index=False)
        column_names = list(df.columns)

        context_str = ""
        if context and isinstance(context, list):
            context_str = "\n\nHere is some context from related text documents in the same folder:\n"
            for chunk in context[:5]: # Limit context size
                context_str += f"- {chunk['content']}\n"

        prompt = f"""Analyze the table columns from a spreadsheet ('{file_name}'{f", sheet '{sheet_name}'" if sheet_name else ""}).
{context_str}
The column names are: {column_names}
Here are the first few rows of data:
{sample_data_str}

For each column name, provide:
1. A concise one-sentence description of what the data represents. Use the provided context if it helps clarify the meaning.
2. The most appropriate SQLite-compatible SQL data type (choose from: TEXT, INTEGER, REAL).

Respond ONLY with a valid JSON object where keys are the exact column names and values are objects with 'description' and 'sql_type'. Example:
{{
  "ColumnA": {{ "description": "Unique identifier for each record.", "sql_type": "INTEGER" }}
}}
"""

        raw_response = self._call_llm(prompt, temperature=0.0)
        if not raw_response:
            return None

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_response, re.DOTALL)
        if not json_match:
            json_match = re.search(r"(\{.*?\})", raw_response, re.DOTALL)

        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON metadata from Gemini: {raw_response}")
                return None
        else:
            logger.error(f"Could not find JSON object in Gemini response for metadata: {raw_response}")
            return None

    def classify_query(self, query, table_metadata):
        """Classifies the user query as 'text', 'sql', or 'hybrid'."""

        schema_overview = "None"
        if table_metadata:
            schema_overview = "Available SQL Tables:\n"
            for table_name, meta in table_metadata.items():
                col_descs = [f"`{col.get('name')}`" for col in meta.get('columns', [])]
                schema_overview += f"- Table `{table_name}` (from file `{meta.get('source_file')}`) has columns: {', '.join(col_descs)}\n"

        prompt = f"""You are an expert query analyzer. Your task is to classify a user query into one of three categories: 'text', 'sql', or 'hybrid'.

Here is the context you have:
1.  A collection of text documents (like PDFs and PPTs).
2.  A database with the following tables and schemas:
{schema_overview}

Classification Guidelines:
- 'text': The query can likely be answered using only the text documents. It usually asks for descriptions, summaries, or qualitative information.
- 'sql': The query requires structured data from the database tables. It often involves calculations (e.g., "total", "average"), specific numbers, or filtering on columns.
- 'hybrid': The query requires information from BOTH text documents AND the database. For example, asking for a summary of a project (text) and its total budget (sql).

User Query: "{query}"

Analyze the query and the available table schemas. Respond ONLY with a valid JSON object containing the key "classification" and the value 'text', 'sql', or 'hybrid'.

Example:
Query: "What is the total budget for the alpha_data project?"
Response: {{"classification": "sql"}}

Query: "Summarize the goals of Project Alpha and what is its budget?"
Response: {{"classification": "hybrid"}}
"""

        raw_response = self._call_llm(prompt, temperature=0.0)
        if not raw_response:
            return "text"  # Default classification

        try:
            # The response might be wrapped in markdown
            json_match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                classification = result.get("classification")
                if classification in ["text", "sql", "hybrid"]:
                    logger.info(f"Query classified as '{classification}'")
                    return classification
            logger.warning(f"Could not parse classification JSON from Gemini: {raw_response}")
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"Failed to parse classification from Gemini: '{raw_response}'. Defaulting to 'text'.")

        return "text"

    def identify_target_sql_table(self, query, table_metadata):
        if not table_metadata:
            return None

        schema_overview = "Available SQL Tables:\n"
        table_options = []
        for table_name, meta in table_metadata.items():
            table_options.append(table_name)
            col_descs = [f"- `{col.get('name')}` (Desc: {col.get('description')})" for col in meta.get('columns', [])]
            schema_overview += f"\nTable: `{table_name}` (From: '{meta.get('source_file')}')\n" + "\n".join(col_descs) + "\n"

        prompt = f"""Given the user query, choose the single most relevant SQL table to answer it.
{schema_overview}
User Query: "{query}"
Respond ONLY with the exact name of the single most appropriate table from {table_options}. If none are relevant, respond "NONE".
"""
        response = self._call_llm(prompt, temperature=0.0)
        if response and response.strip() in table_options:
            return response.strip()
        return None

    def generate_sql_query(self, query, table_name, table_meta):
        schema_description = f"Table: `{table_name}`\nColumns:\n"
        for col in table_meta['columns']:
            schema_description += f"- \"{col['name']}\" (Type: {col.get('type', 'TEXT')}, Desc: {col.get('description', 'N/A')})\n"

        prompt = f"""You are an expert SQLite query writer. Your task is to write a single, valid SQLite query to answer the user's question based on the provided table schema.

**Instructions:**
- Respond ONLY with the SQLite query.
- Do not include any explanations, markdown, or any text other than the query itself.
- Use double quotes for column names.
- If a calculation is needed, use the appropriate SQL aggregate function (e.g., SUM, AVG, COUNT).

**Schema for table `{table_name}`:**
{schema_description}

---
**Examples:**

User Query: "What is the total budget?"
SQL Query: SELECT SUM("budget") FROM "{table_name}"

User Query: "Show me all the tasks that are in progress."
SQL Query: SELECT * FROM "{table_name}" WHERE "status" = 'in-progress'

User Query: "how many subscribers did we have in february"
SQL Query: SELECT "subscribers" FROM "{table_name}" WHERE "month" = 'Feb'
---

**User's Query:** "{query}"

**SQL Query:**
"""
        response = self._call_llm(prompt, temperature=0.0)
        if response:
            # Clean up the response to get only the SQL
            sql_query = response.strip()
            if sql_query.upper().startswith("SELECT"):
                logger.info(f"Generated SQL for '{table_name}': {sql_query}")
                return sql_query
            else:
                logger.warning(f"Generated response was not a valid SELECT query: {sql_query}")
        return None

    def synthesize_answer(self, query, context, chat_history):
        history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])

        prompt = f"""You are a helpful AI assistant. Answer the user's query based ONLY on the provided context and conversation history.
Do not use any prior knowledge. If the answer is not in the context, say so.

Conversation History:
{history_str}

Context:
---
{context}
---

User Query: {query}

Answer:
"""
        return self._call_llm(prompt, temperature=self.config.temperature)

    def refine_query_with_history(self, current_query, chat_history):
        if not chat_history:
            return current_query

        history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])
        prompt = f"""Given the chat history and the latest user query, rewrite the query to be a standalone question.
If the query is already standalone, return it as is.

Chat History:
{history_str}

Latest User Query: "{current_query}"

Standalone Query:
"""
        response = self._call_llm(prompt, temperature=0.0)
        return response if response else current_query

    def decompose_hybrid_query(self, query):
        prompt = f"""The user has asked a question that requires information from both text documents and a database.
Your task is to decompose this query into two separate questions:
1. A 'text_query' that can be answered by searching through text.
2. A 'sql_query' that can be answered by querying a database.

Original Query: "{query}"

Respond ONLY in a valid JSON format with the keys "text_query" and "sql_query".
Example:
{{"text_query": "What are the project goals for SkyWatch?", "sql_query": "What is the total budget for the SkyWatch project?"}}
"""
        raw_response = self._call_llm(prompt, temperature=0.0)
        if not raw_response:
            return None

        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse decomposed query from Gemini: {raw_response}")
            return None
