import os
import configparser
import logging
import torch

logger = logging.getLogger(__name__)

class RAGConfig:
    """Configuration class for RAG system with SambaNova."""
    def __init__(self, config_path="config1.ini"):
        self.config = configparser.ConfigParser()
        self.defaults = {
            "PATHS": {
                "data_dir": "./data/",
                "index_dir": "./faiss_index/",
                "log_file": "rag_system.log",
                "sqlite_db_path": ":memory:"
            },
            "MODELS": {
                "encoder_model": "sentence-transformers/all-MiniLM-L6-v2",
                "gemini_model": "gemini-1.5-pro",
                "device": "auto",
            },
            "PARAMETERS": {
                "chunk_size": "250",
                "overlap": "60",
                "k_retrieval": "6",
                "temperature": "0.1",
                "top_p": "0.9",
                "max_context_tokens": "6000",
                "max_output_tokens": "1024",
                "max_chars_per_element": "1200",
                "pptx_merge_threshold_words": "50",
                "dataframe_query_confidence_threshold": "0.70",
                "max_chat_history_turns": "5"
            },
            "SUPPORTED_EXTENSIONS": {
                "extensions": ".pdf, .xlsx, .csv, .pptx"
            },
            "API_KEYS": {
                 "gemini_api_key": ""
            }
        }
        if os.path.exists(config_path):
            try:
                self.config.read(config_path)
                logger.info(f"Loaded configuration from {config_path}")
                self._ensure_defaults()
            except Exception as e:
                logger.error(f"Error reading config file {config_path}: {e}")
                self._set_defaults()
        else:
            logger.warning(f"Config file {config_path} not found, using defaults")
            self._set_defaults()

    def _set_defaults(self):
        for section, options in self.defaults.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
            for option, value in options.items():
                if not self.config.has_option(section, option):
                    self.config.set(section, option, value)

    def _ensure_defaults(self):
        for section, options in self.defaults.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
                logger.info(f"Added missing section [{section}] from defaults.")
            for option, value in options.items():
                if not self.config.has_option(section, option):
                    self.config.set(section, option, value)
                    logger.info(f"Added missing option '{option} = {value}' to section [{section}] from defaults.")

    @property
    def data_dir(self): return self.config.get("PATHS", "data_dir")
    @property
    def index_dir(self): return self.config.get("PATHS", "index_dir")
    @property
    def log_file(self): return self.config.get("PATHS", "log_file")
    @property
    def sqlite_db_path(self): return self.config.get("PATHS", "sqlite_db_path", fallback=":memory:")
    @property
    def encoder_model(self): return self.config.get("MODELS", "encoder_model")
    @property
    def gemini_model(self): return self.config.get("MODELS", "gemini_model")
    @property
    def device(self):
        device_setting = self.config.get("MODELS", "device", fallback="auto")
        if device_setting == "auto": return "cuda" if torch.cuda.is_available() else "cpu"
        return device_setting
    @property
    def chunk_size(self): return self.config.getint("PARAMETERS", "chunk_size", fallback=250)
    @property
    def overlap(self): return self.config.getint("PARAMETERS", "overlap", fallback=60)
    @property
    def k_retrieval(self): return self.config.getint("PARAMETERS", "k_retrieval", fallback=6)
    @property
    def temperature(self): return self.config.getfloat("PARAMETERS", "temperature", fallback=0.1)
    @property
    def top_p(self): return self.config.getfloat("PARAMETERS", "top_p", fallback=0.9)
    @property
    def max_context_tokens(self): return self.config.getint("PARAMETERS", "max_context_tokens", fallback=6000)
    @property
    def max_output_tokens(self): return self.config.getint("PARAMETERS", "max_output_tokens", fallback=1024)
    @property
    def max_chars_per_element(self): return self.config.getint("PARAMETERS", "max_chars_per_element", fallback=1200)
    @property
    def pptx_merge_threshold_words(self): return self.config.getint("PARAMETERS", "pptx_merge_threshold_words", fallback=50)
    @property
    def supported_extensions(self):
        ext_str = self.config.get("SUPPORTED_EXTENSIONS", "extensions", fallback=".pdf, .xlsx, .csv, .pptx")
        return tuple([e.strip() for e in ext_str.lower().split(',') if e.strip()])
    @property
    def dataframe_query_confidence_threshold(self):
        return self.config.getfloat("PARAMETERS", "dataframe_query_confidence_threshold", fallback=0.70)
    @property
    def max_chat_history_turns(self):
        return self.config.getint("PARAMETERS", "max_chat_history_turns", fallback=5)
    @property
    def gemini_api_key(self):
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            key = self.config.get("API_KEYS", "gemini_api_key", fallback=None)
            if key: logger.info("Using Gemini API key from config file.")
        return key
