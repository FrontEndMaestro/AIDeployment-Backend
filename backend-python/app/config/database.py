from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from .settings import settings


class Database:
    client: Optional[AsyncIOMotorClient] = None
    database = None

    @classmethod
    async def connect_db(cls):
        try:
            cls.client = AsyncIOMotorClient(settings.MONGODB_URL)
            cls.database = cls.client[settings.DATABASE_NAME]
            await cls.client.admin.command('ping')
            print(f"MongoDB connected: {settings.DATABASE_NAME}")
        except Exception as e:
            print(f"MongoDB connection error: {e}")
            raise e

    @classmethod
    async def close_db(cls):
        if cls.client:
            cls.client.close()
            print("MongoDB connection closed")

    @classmethod
    def get_collection(cls, collection_name: str):
        if cls.database is None:
            raise Exception("Database not connected")
        return cls.database[collection_name]


db = Database()


def get_projects_collection():
    return db.get_collection("projects")
