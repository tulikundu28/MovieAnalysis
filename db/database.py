"""Async SQLAlchemy engine and session factory; provides the get_db dependency."""
import logging
import os
import sys
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

load_dotenv()

logger = logging.getLogger(__name__)


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"FATAL: required environment variable {name!r} is not set")
    return value


DATABASE_URL = (
    f"postgresql+asyncpg://{_require('POSTGRES_USER')}:{_require('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}/{_require('POSTGRES_DB')}"
)

engine = create_async_engine(DATABASE_URL, echo=os.getenv("APP_ENV", "dev") == "dev")

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

logger.debug("Database engine initialised: host=%s db=%s", os.getenv("POSTGRES_HOST", "localhost"), os.getenv("POSTGRES_DB"))


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
