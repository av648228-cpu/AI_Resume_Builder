"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent


def _database_url():
    """Return the configured database URL, normalizing legacy Render URLs."""
    url = os.environ.get("DATABASE_URL", "sqlite:///resume_builder.db")
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Config:
    """Default local and production configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(32)
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    MAX_PHOTO_SIZE = 2 * 1024 * 1024
    MAX_DOCUMENT_SIZE = 4 * 1024 * 1024
    MAX_DOCUMENTS_PER_REQUEST = 5
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PREFERRED_URL_SCHEME = "https"
