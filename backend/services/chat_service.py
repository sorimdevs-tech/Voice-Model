import duckdb
from pathlib import Path
import logging
import json
from typing import Dict, Any, Optional

logger = logging.getLogger("voxa.chat")

class ChatService:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the chats table if it doesn't exist."""
        conn = duckdb.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    user_id VARCHAR,
                    conversations JSON,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id)
                )
            """)
        finally:
            conn.close()

    def get_user_chats(self, user_id: str) -> Dict[str, Any]:
        conn = duckdb.connect(str(self.db_path))
        try:
            res = conn.execute("SELECT conversations FROM chats WHERE user_id = ?", [user_id]).fetchone()
            if res:
                # DuckDB JSON type returns a string or a dict depending on driver/version
                val = res[0]
                if isinstance(val, str):
                    return json.loads(val)
                return val
            return {}
        finally:
            conn.close()

    def sync_user_chats(self, user_id: str, conversations: Dict[str, Any]):
        conn = duckdb.connect(str(self.db_path))
        try:
            # We use a full replace (UPSERT) for the user's conversation map
            # This allows clearing all chats if an empty dict is passed
            conversations_json = json.dumps(conversations)
            
            # Check if exists
            exists = conn.execute("SELECT 1 FROM chats WHERE user_id = ?", [user_id]).fetchone()
            if exists:
                conn.execute("""
                    UPDATE chats SET conversations = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?
                """, [conversations_json, user_id])
            else:
                conn.execute("""
                    INSERT INTO chats (user_id, conversations) VALUES (?, ?)
                """, [user_id, conversations_json])
        finally:
            conn.close()

_chat_service = None

def get_chat_service(db_path: Optional[Path] = None) -> ChatService:
    global _chat_service
    if _chat_service is None:
        if db_path is None:
            from config import DATA_DIR
            db_path = DATA_DIR / "voxa_system.duckdb" # Use a shared system DB
        _chat_service = ChatService(db_path)
    return _chat_service
