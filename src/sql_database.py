import os
import re
import logging
import sqlite3
import pandas as pd
import numpy as np
from .config import RAGConfig
from .text_processing import clean_text
from .llm_gemini import GeminiLLM
from .utils import get_safe_filename

logger = logging.getLogger(__name__)

def get_safe_table_name(file_name, sheet_name=None):
    safe_base = get_safe_filename(file_name)
    if sheet_name:
         safe_sheet = re.sub(r'[^\w]', '_', sheet_name)
         name = f"{safe_base}_{safe_sheet}"
    else:
        name = safe_base
    if not re.match(r"^[a-zA-Z_]", name):
        name = "_" + name
    return name[:60].lower()

def table_exists(db_cursor, table_name):
    if not db_cursor: return False
    try:
        db_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
        return db_cursor.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"Error checking if table '{table_name}' exists: {e}")
        return False

def infer_sql_type(series):
    num_numeric = pd.to_numeric(series, errors='coerce').notna().sum()
    num_total = len(series)
    if num_total > 0 and num_numeric / num_total > 0.9:
        numeric_series = pd.to_numeric(series, errors='coerce').dropna()
        if not numeric_series.empty and (numeric_series == numeric_series.astype(np.int64)).all():
             return "INTEGER"
        return "REAL"
    if pd.api.types.is_integer_dtype(series.dtype): return "INTEGER"
    if pd.api.types.is_float_dtype(series.dtype): return "REAL"
    if pd.api.types.is_bool_dtype(series.dtype): return "INTEGER"
    if pd.api.types.is_datetime64_any_dtype(series.dtype): return "TEXT"
    return "TEXT"

def load_df_to_sql(db_conn, db_cursor, df, table_name, column_metadata, file_name, sheet_name=None):
    if not db_conn or not db_cursor:
        logger.error("Database connection not available. Cannot load table.")
        return False, {}
    if not table_name:
        logger.error("Invalid table name provided. Cannot load table.")
        return False, {}
    if table_exists(db_cursor, table_name):
         logger.warning(f"Table '{table_name}' already exists. Replacing.")
         try:
             db_cursor.execute(f'DROP TABLE "{table_name}"')
         except sqlite3.Error as e_drop:
             logger.error(f"Error dropping existing table {table_name}: {e_drop}")
             return False, {}
    try:
        logger.info(f"Loading DataFrame into SQL table '{table_name}'...")
        df.columns = [meta['name'] for meta in column_metadata]
        temp_df = df.copy()
        for meta in column_metadata:
            col, sql_type = meta['name'], meta['type']
            if sql_type in ["INTEGER", "REAL"]:
                temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')
                if sql_type == "INTEGER":
                     try:
                         temp_df[col] = temp_df[col].astype('Int64')
                     except Exception: pass
            elif sql_type == "TEXT":
                 temp_df[col] = temp_df[col].astype(str)

        temp_df.to_sql(table_name, db_conn, if_exists='replace', index=False)
        db_conn.commit()
        logger.info(f"DataFrame loaded into table '{table_name}' ({len(df)} rows).")

        table_meta = {
            "columns": column_metadata,
            "source_file": file_name,
            "source_sheet": sheet_name,
            "row_count": len(df)
        }
        return True, table_meta
    except Exception as e:
        logger.error(f"Error loading DataFrame to table '{table_name}': {e}", exc_info=True);
        try:
            db_conn.rollback()
        except: pass
        return False, {}

def extract_and_load_xlsx(file_path, file_name, db_conn, db_cursor, llm: GeminiLLM, config: RAGConfig, context=None):
    base_filename = os.path.basename(file_path)
    processed_tables = {}
    try:
        excel_file = pd.ExcelFile(file_path)
        sheet_names = excel_file.sheet_names
        logger.info(f"Processing XLSX: {base_filename} (Sheets: {len(sheet_names)})")
        if not sheet_names:
            logger.warning(f"No sheets found in {base_filename}")
            return processed_tables

        for i, sheet_name in enumerate(sheet_names):
            logger.info(f"Processing sheet '{sheet_name}' ({i+1}/{len(sheet_names)}) in {base_filename}")
            try:
                df = excel_file.parse(sheet_name)
                df = df.fillna('')
                df.columns = [re.sub(r'[^a-zA-Z0-9_]', '_', str(col)).strip('_') for col in df.columns]
                df.columns = [f"col_{j}" if not name else name for j, name in enumerate(df.columns)]

                cols = pd.Series(df.columns)
                for dup_idx, dup_val in cols[cols.duplicated()].items():
                     indices = cols[cols == dup_val].index.tolist()
                     for k_idx, col_idx in enumerate(indices):
                         if k_idx > 0:
                             cols[col_idx] = f"{dup_val}_{k_idx}"
                df.columns = cols

                if df.empty:
                    logger.warning(f"Sheet '{sheet_name}' in {base_filename} is empty. Skipping.")
                    continue

                table_name = get_safe_table_name(file_name, sheet_name)
                if not table_name:
                    logger.error(f"Could not generate table name for sheet '{sheet_name}'. Skipping SQL load.")
                    continue

                column_metadata = llm.generate_column_metadata(df, file_name, sheet_name, context=context)
                if not column_metadata:
                    logger.warning(f"Failed to get column metadata for sheet '{sheet_name}'. Proceeding without descriptions.")
                    column_metadata = [{"name": col, "type": infer_sql_type(df[col]), "description": "N/A - Metadata generation failed."} for col in df.columns]

                sql_loaded, table_meta = load_df_to_sql(db_conn, db_cursor, df, table_name, column_metadata, file_name, sheet_name)
                if sql_loaded:
                    processed_tables[table_name] = table_meta
                    logger.info(f"Successfully loaded sheet '{sheet_name}' into SQL table '{table_name}'")
                else:
                    logger.error(f"Failed to load sheet '{sheet_name}' into SQL.")
            except Exception as e_sheet:
                logger.error(f"Error processing sheet '{sheet_name}' in {base_filename}: {e_sheet}", exc_info=True)

        return processed_tables
    except Exception as e:
        logger.error(f"Error opening or processing XLSX file {base_filename}: {e}", exc_info=True)
        return processed_tables

def extract_and_load_csv(file_path, file_name, db_conn, db_cursor, llm: GeminiLLM, config: RAGConfig, context=None):
    base_filename = os.path.basename(file_path)
    df = None
    processed_tables = {}
    try:
        logger.info(f"Processing CSV: {base_filename}")
        encodings_to_try = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        for enc in encodings_to_try:
            try:
                df = pd.read_csv(file_path, encoding=enc, low_memory=False, on_bad_lines='warn')
                df = df.fillna('')
                df.columns = [re.sub(r'[^a-zA-Z0-9_]', '_', str(col)).strip('_') for col in df.columns]
                df.columns = [f"col_{j}" if not name else name for j, name in enumerate(df.columns)]
                cols = pd.Series(df.columns)
                for dup_idx, dup_val in cols[cols.duplicated()].items():
                     indices = cols[cols == dup_val].index.tolist()
                     for k_idx, col_idx in enumerate(indices):
                         if k_idx > 0:
                             cols[col_idx] = f"{dup_val}_{k_idx}"
                df.columns = cols
                logger.info(f"Read CSV {base_filename} using encoding: {enc}. (Rows: {len(df)}, Cols: {len(df.columns)})")
                break
            except UnicodeDecodeError:
                continue
            except Exception as e_read:
                logger.warning(f"Pandas read_csv error for {base_filename} with encoding {enc}: {e_read}")

        if df is None:
            logger.error(f"Could not read CSV {base_filename} after trying encodings.")
            return {}
        if df.empty:
            logger.warning(f"CSV {base_filename} is empty.")
            return {}

        table_name = get_safe_table_name(file_name)
        if not table_name:
            logger.error("Could not generate table name for CSV. Skipping SQL load.")
            return {}

        column_metadata = llm.generate_column_metadata(df, file_name, context=context)
        if not column_metadata:
            logger.warning("Failed to get column metadata for CSV. Proceeding without descriptions.")
            column_metadata = [{"name": col, "type": infer_sql_type(df[col]), "description": "N/A - Metadata generation failed."} for col in df.columns]

        sql_loaded, table_meta = load_df_to_sql(db_conn, db_cursor, df, table_name, column_metadata, file_name)
        if sql_loaded:
            processed_tables[table_name] = table_meta
            logger.info(f"Successfully loaded CSV {base_filename} into SQL table '{table_name}'")
        else:
            logger.error(f"Failed to load CSV {base_filename} into SQL.")

        return processed_tables
    except Exception as e:
        logger.error(f"Error processing CSV file {base_filename}: {e}", exc_info=True)
        return {}

def execute_sql_query(db_conn, sql_query):
    if not db_conn:
        return None, "Database connection error."
    if not sql_query:
        return None, "No SQL query generated."
    try:
        logger.info(f"Executing SQL: {sql_query}")
        df_results = pd.read_sql_query(sql_query, db_conn)
        if df_results.empty:
            return "No results found.", None
        output_str = df_results.to_string(index=False, max_rows=25, na_rep='NULL')
        if len(df_results) > 25:
            output_str += f"\n... (truncated, {len(df_results)} total rows)"
        return f"Query Result ({len(df_results)} row(s)):\n" + output_str, None
    except Exception as e_sql:
        err_msg = f"SQLite execution error: {e_sql}"
        logger.error(err_msg, exc_info=False)
        return None, f"Database error: {e_sql}"
