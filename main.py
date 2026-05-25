from fastapi import FastAPI
from controllers.movie_controller import router as movie_router

app = FastAPI(
    title="Movies API",
    version="1.0.0"
)
app.include_router(movie_router)