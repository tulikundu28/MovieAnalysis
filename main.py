import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from routers import register_routers
from services.role_expiry_service import role_expiry_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(role_expiry_loop())
    yield
    task.cancel()


app = FastAPI(title="Movies API", version="1.0.0", lifespan=lifespan)
register_routers(app)

app.mount("/ui", StaticFiles(directory="ui"), name="ui")

@app.get("/")
async def root():
    return FileResponse("ui/index.html")