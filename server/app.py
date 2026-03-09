# server/app.py — Eva Gateway FastAPI application
from fastapi import FastAPI

app = FastAPI(title="Eva Gateway", version="1.0.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
