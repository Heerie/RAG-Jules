import re
import logging
from .config import RAGConfig

logger = logging.getLogger(__name__)

def clean_text(text):
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r"\(cid:.*?\)", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def chunk_content(all_content, config: RAGConfig):
    chunks = []
    if not all_content:
        return chunks

    for item_index, item in enumerate(all_content):
        content = item.get('content', '')
        source_info = item.get('source_info', {})
        file_type = item.get('file_type', 'unknown')
        content_type = item.get('type', 'unknown')
        potential_section = item.get('potential_section', 'unknown')

        if not isinstance(content, str):
            content = str(content)

        words = content.split()
        if not words:
            continue

        start_index = 0
        while start_index < len(words):
            end_index = start_index + config.chunk_size
            chunk_text = " ".join(words[start_index:end_index])

            if chunk_text:
                 chunks.append({
                     "content": chunk_text,
                     "source_info": source_info,
                     "file_type": file_type,
                     "type": content_type,
                     "potential_section": potential_section
                 })

            start_index += (config.chunk_size - config.overlap)
            if start_index >= len(words):
                break

    logger.info(f"Created {len(chunks)} text chunks from {len(all_content)} content blocks.")
    return chunks

def aggregate_context(retrieved_chunks, config: RAGConfig):
    """Aggregates and formats retrieved chunks into a single context string."""
    if not retrieved_chunks:
        return ""

    context_str = ""
    max_len = config.max_context_tokens * 4 # Heuristic for character count

    for chunk in retrieved_chunks:
        source_info = chunk.get('source_info', {})
        project = source_info.get('project', 'N/A')
        page = source_info.get('page')

        header = f"--- Context from project '{project}'"
        if page:
            header += f", page {page}"
        header += " ---\n"

        content_to_add = header + chunk['content'] + "\n\n"

        if len(context_str) + len(content_to_add) > max_len:
            break

        context_str += content_to_add

    return context_str.strip()
