from datetime import datetime, timezone
from sqlalchemy import Integer, JSON, String, Text, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utc_now, index=True)
    level: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    source: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    module: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(String, nullable=True)
    error_hash: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    correlationId: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    userId: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    symbol: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    orderId: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    environment: Mapped[str | None] = mapped_column(String, default="DEV", index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class DeadLetterJob(Base):
    __tablename__ = "dead_letter_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int | None] = mapped_column(Integer, default=0)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class ServiceHealth(Base):
    __tablename__ = "service_health"

    service_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
