import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from alembic.config import Config
from alembic import command as alembic_command
from routers import register_routers
from services.role_expiry_service import role_expiry_loop
from db.database import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    logger.info("Running database migrations")
    alembic_command.upgrade(Config("alembic.ini"), "head")
    logger.info("Migrations complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.get_event_loop().run_in_executor(None, _run_migrations)
    logger.info("Starting role-expiry background task")
    task = asyncio.create_task(role_expiry_loop())
    yield
    logger.info("Shutting down")
    task.cancel()


app = FastAPI(title="Movies API", version="1.0.0", lifespan=lifespan)
register_routers(app)

app.mount("/ui", StaticFiles(directory="ui"), name="ui")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        raise exc
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/")
async def root():
    return FileResponse("ui/index.html")


@app.get("/healthz", tags=["ops"])
async def healthz():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
