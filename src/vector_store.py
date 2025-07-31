import os
import logging
import json
import faiss
import numpy as np
from .config import RAGConfig

logger = logging.getLogger(__name__)

def get_index_path(index_dir, index_name):
    return os.path.join(index_dir, f"{index_name}.index")

def get_chunks_path(index_dir, index_name):
    return os.path.join(index_dir, f"{index_name}.json")

def save_index_and_chunks(index_dir, index_name, index, chunks):
    """Saves the FAISS index and corresponding text chunks."""
    os.makedirs(index_dir, exist_ok=True)
    index_path = get_index_path(index_dir, index_name)
    chunks_path = get_chunks_path(index_dir, index_name)

    try:
        faiss.write_index(index, index_path)
        logger.info(f"Saved FAISS index to {index_path} ({index.ntotal} vectors)")
    except Exception as e:
        logger.error(f"Error saving FAISS index to {index_path}: {e}")

    try:
        with open(chunks_path, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, indent=2)
        logger.info(f"Saved {len(chunks)} text chunks to {chunks_path}")
    except Exception as e:
        logger.error(f"Error saving text chunks to {chunks_path}: {e}")

def load_index_and_chunks(index_dir, index_name, embedding_dim):
    """Loads a FAISS index and corresponding text chunks."""
    index_path = get_index_path(index_dir, index_name)
    chunks_path = get_chunks_path(index_dir, index_name)

    index = None
    chunks = None

    if os.path.exists(index_path):
        try:
            index = faiss.read_index(index_path)
            logger.info(f"Loaded FAISS index from {index_path} ({index.ntotal} vectors)")
        except Exception as e:
            logger.error(f"Error reading FAISS index {index_path}: {e}. Creating new index.")

    if index is None:
        index = faiss.IndexFlatL2(embedding_dim)

    if os.path.exists(chunks_path):
        try:
            with open(chunks_path, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
            logger.info(f"Loaded {len(chunks)} text chunks from {chunks_path}")
        except Exception as e:
            logger.error(f"Error loading/decoding text chunks from {chunks_path}: {e}.")

    return index, chunks

def create_and_save_index(texts, encoder_model, index_dir, index_name):
    """Creates embeddings and saves a new FAISS index and chunks."""
    if not texts:
        logger.warning("No texts provided to create index.")
        return None, None

    logger.info(f"Generating embeddings for {len(texts)} texts to create index '{index_name}'...")
    embeddings = encoder_model.encode(
        [t['content'] for t in texts],
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True
    ).astype('float32')

    if embeddings.shape[0] > 0:
        embedding_dim = encoder_model.get_sentence_embedding_dimension()
        index = faiss.IndexFlatL2(embedding_dim)
        index.add(embeddings)

        save_index_and_chunks(index_dir, index_name, index, texts)
        return index, texts
    else:
        logger.warning(f"Embedding process yielded no vectors for index '{index_name}'.")
        return None, None

def query_index(query, index, chunks, encoder_model, config: RAGConfig):
    """Queries a single FAISS index."""
    if index is None or index.ntotal == 0 or chunks is None:
        logger.warning("Cannot query empty or non-existent index/chunks.")
        return []

    try:
        query_embedding = encoder_model.encode(query, convert_to_numpy=True).astype("float32")
        query_embedding = np.array([query_embedding])

        if query_embedding.ndim != 2:
            raise ValueError("Query embedding has an incorrect shape.")

        k_search = min(config.k_retrieval, index.ntotal)
        distances, indices = index.search(query_embedding, k=k_search)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and 0 <= idx < len(chunks):
                chunk = chunks[idx]
                results.append({
                    "source_info": chunk.get('source_info', {}),
                    "file_type": chunk.get('file_type', 'unknown'),
                    "content": chunk.get('content', ''),
                    "score": round(float(distances[0][i]), 4),
                    "type": chunk.get('type', 'unknown'),
                    "potential_section": chunk.get('potential_section', 'unknown')
                })

        return sorted(results, key=lambda x: x['score'])
    except Exception as e_search:
        logger.error(f"Error searching index: {e_search}", exc_info=True)
        return []
