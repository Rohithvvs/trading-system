from __future__ import annotations

from typing import Optional

from pymongo import MongoClient

from ..config import settings

_client: Optional[MongoClient] = None


def get_mongo_client() -> Optional[MongoClient]:
    global _client
    if _client is not None:
        return _client
    if not settings.mongo_url:
        return None
    _client = MongoClient(settings.mongo_url)
    return _client


def get_transactions_collection():
    client = get_mongo_client()
    if client is None:
        return None
    db = client[settings.mongo_db_name or "trading_system"]
    return db["transactions"]
