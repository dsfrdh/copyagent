"""CopyAgent configuration."""
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_DOCS_DIR = DATA_DIR / "knowledge_docs"
OUTPUTS_DIR = DATA_DIR / "outputs"
DB_PATH = DATA_DIR / "copyagent.db"
CHUNKS_JSON = DATA_DIR / "chunks.json"

for d in [KNOWLEDGE_DOCS_DIR, OUTPUTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# DeepSeek API
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "your-api-key-here")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# Chunking
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

# Retrieval
TOP_K_RETRIEVAL = 5

# Generation defaults
DEFAULT_COUNT = 3
DEFAULT_LENGTH = "60秒"
DEFAULT_STYLE = "口语化"
MAX_GEN_WORDS = 500

# Scheduler default
DEFAULT_SCHEDULE_HOUR = 7
DEFAULT_SCHEDULE_MINUTE = 0
