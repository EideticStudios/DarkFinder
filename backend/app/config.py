from pathlib import Path

# Absolute path to backend/data/
DATA_DIR = Path(__file__).parent.parent / "data"

PROCESSED_DIR = DATA_DIR / "processed"

API_PREFIX = "/api/v1"

FRONTEND_ORIGIN = "http://localhost:5173"
