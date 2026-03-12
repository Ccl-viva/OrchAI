import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "orchai_demo.db"
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
EXPORT_DIR = STORAGE_DIR / "exports"

PREVIEW_MAX_ROWS = 20
DEFAULT_LLM_PROVIDER = os.getenv("ORCHAI_DEFAULT_LLM_PROVIDER", "openai")
DEFAULT_LLM_MODEL = os.getenv("GOAL_PARSER_MODEL", "gpt-4.1-mini")

for directory in (STORAGE_DIR, UPLOAD_DIR, EXPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)
