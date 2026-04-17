from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from .settings import settings
import sys


def _safe_print(msg: str):
    """Print with fallback for Windows cp1252 terminals that can't handle emoji."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


class Database:
    client: Optional[AsyncIOMotorClient] = None
    database = None
    
    @classmethod
    async def connect_db(cls):
        try:
            cls.client = AsyncIOMotorClient(settings.MONGODB_URL)
            cls.database = cls.client[settings.DATABASE_NAME]
            await cls.client.admin.command('ping')
            _safe_print(f"[OK] MongoDB Connected: {settings.DATABASE_NAME}")
        except Exception as e:
            _safe_print(f"[ERROR] MongoDB Connection Error: {e}")
            raise e
    
    @classmethod
    async def close_db(cls):
        if cls.client:
            cls.client.close()
            _safe_print("[INFO] MongoDB Connection Closed")
    
    @classmethod
    def get_collection(cls, collection_name: str):
        if cls.database is None:
            raise Exception("Database not connected")
        return cls.database[collection_name]


db = Database()


def get_projects_collection():
    return db.get_collection("projects")
