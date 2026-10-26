import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from project root if it exists
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

# Firebase configuration
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
if not os.path.isabs(FIREBASE_CREDENTIALS_PATH):
    FIREBASE_CREDENTIALS_PATH = str(BASE_DIR / FIREBASE_CREDENTIALS_PATH)

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", None)

# Backend server configuration
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
DEFAULT_SESSION_ID = os.getenv("ATTENDANCE_SESSION", "DEFAULT_SESSION")

# Recognition threshold
RECOGNITION_THRESHOLD = float(os.getenv("RECOGNITION_THRESHOLD", "0.55"))

# Firestore Collections
COLLECTION_STUDENTS = "students"
COLLECTION_EMBEDDINGS = "embeddings"
COLLECTION_ATTENDANCE = "attendance"
