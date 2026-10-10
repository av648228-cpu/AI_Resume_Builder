"""SQLAlchemy models for persisted resume drafts and uploaded-file metadata."""

import json
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Resume(db.Model):
    """A saved resume, its structured data, and private upload metadata."""

    id = db.Column(db.String(32), primary_key=True)
    data_json = db.Column(db.Text, nullable=False, default="{}")
    photo_filename = db.Column(db.String(255), nullable=True)
    documents_json = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def get_data(self):
        """Deserialize resume data, falling back safely when needed."""
        try:
            value = json.loads(self.data_json or "{}")
            return value if isinstance(value, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    def set_data(self, value):
        """Persist a structured resume dictionary as JSON text."""
        self.data_json = json.dumps(value, ensure_ascii=False)

    def get_documents(self):
        """Deserialize saved supporting-document metadata."""
        try:
            value = json.loads(self.documents_json or "[]")
            return value if isinstance(value, list) else []
        except (TypeError, json.JSONDecodeError):
            return []

    def set_documents(self, documents):
        """Persist supporting-document metadata as JSON text."""
        self.documents_json = json.dumps(documents, ensure_ascii=False)
