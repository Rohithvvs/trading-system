from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)

# Import models so they are registered with SQLAlchemy metadata.
# This keeps table metadata available for tools that import db.base
# (note: importing models here is intentional to ensure tables are
# registered; avoid circular-work by keeping only imports).
