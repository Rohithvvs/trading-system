from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

# Import models so they are registered with SQLAlchemy metadata.
# This keeps table metadata available for tools that import db.base
# (note: importing models here is intentional to ensure tables are
# registered; avoid circular-work by keeping only imports).
from ..models.fyers_token import FyersToken
from ..models.fyers_token_history import FyersTokenHistory
