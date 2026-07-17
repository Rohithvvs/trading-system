from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    environment: str
    disclaimer: str
    database: str = "ok"
    redis: str = "ok"
    fyers: str = "ok"
    websocket: str = "ok"
