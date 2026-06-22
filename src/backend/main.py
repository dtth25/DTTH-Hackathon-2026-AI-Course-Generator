from fastapi import FastAPI
from contextlib import asynccontextmanager
from db import init_milvus, create_database

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_milvus()
    create_database("my_ai_db")
    yield
    # Shutdown (nếu cần)

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Backend ready"}
