from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

from app.api.routes.auth import router as auth_router
from app.api.routes.published import router as published_router
from app.api.routes.sessions import router as sessions_router
from app.config.logging import setup_logging
from app.config.settings import settings
from app.db.session import init_db


setup_logging()

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("app started")
    yield


app = FastAPI(title="FastAPI Agent Loop", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(published_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
