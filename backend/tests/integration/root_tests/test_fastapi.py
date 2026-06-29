from fastapi import FastAPI
import asyncio

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
