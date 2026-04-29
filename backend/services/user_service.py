import duckdb
from pathlib import Path
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("voxa.users")

class UserService:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the users table if it doesn't exist."""
        conn = duckdb.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR,
                    username VARCHAR UNIQUE,
                    email VARCHAR UNIQUE,
                    password VARCHAR,
                    role VARCHAR,
                    profile_pic VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Check if default user exists
            res = conn.execute("SELECT COUNT(*) FROM users WHERE username = 'user'").fetchone()
            if res[0] == 0:
                logger.info("Initializing default user in database")
                conn.execute("""
                    INSERT INTO users (id, name, username, email, password, role)
                    VALUES ('1', 'Plant Manager', 'user', 'user@voxa.ai', 'password123', 'manager')
                """)
        finally:
            conn.close()

    def get_user_by_email_or_username(self, identifier: str) -> Optional[Dict[str, Any]]:
        conn = duckdb.connect(str(self.db_path))
        try:
            res = conn.execute("""
                SELECT id, name, username, email, password, role, profile_pic 
                FROM users 
                WHERE email = ? OR username = ?
            """, [identifier, identifier]).fetchone()
            
            if res:
                return {
                    "id": res[0],
                    "name": res[1],
                    "username": res[2],
                    "email": res[3],
                    "password": res[4],
                    "role": res[5],
                    "profile_pic": res[6]
                }
            return None
        finally:
            conn.close()

    def create_user(self, name: str, username: str, email: str, password: str) -> Dict[str, Any]:
        conn = duckdb.connect(str(self.db_path))
        try:
            new_id = str(conn.execute("SELECT COUNT(*) + 1 FROM users").fetchone()[0])
            conn.execute("""
                INSERT INTO users (id, name, username, email, password, role)
                VALUES (?, ?, ?, ?, ?, 'user')
            """, [new_id, name, username, email, password])
            
            return {
                "id": new_id,
                "name": name,
                "username": username,
                "email": email,
                "role": "user",
                "profile_pic": None
            }
        finally:
            conn.close()

    def update_password(self, username: str, new_password: str):
        conn = duckdb.connect(str(self.db_path))
        try:
            conn.execute("""
                UPDATE users SET password = ? WHERE username = ? OR email = ?
            """, [new_password, username, username])
        finally:
            conn.close()

    def update_profile_pic(self, user_id: str, profile_pic_url: str):
        conn = duckdb.connect(str(self.db_path))
        try:
            conn.execute("""
                UPDATE users SET profile_pic = ? WHERE id = ?
            """, [profile_pic_url, user_id])
        finally:
            conn.close()

_user_service = None

def get_user_service(db_path: Optional[Path] = None) -> UserService:
    global _user_service
    if _user_service is None:
        if db_path is None:
            from config import DATA_DIR
            db_path = DATA_DIR / "voxa_system.duckdb"
        _user_service = UserService(db_path)
    return _user_service
