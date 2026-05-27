"""Declares all API routers and registers them on the FastAPI app."""
from fastapi import FastAPI, APIRouter
from models.movie import Movie, MovieSearchResponse
from models.auth import TokenResponse, RegistrationResponse
from models.access import AccessRequestResponse, AccessRequestStatusResponse, ReviewResponse
from controllers.movie_controller import search_movies, get_movie, upload_movies, edit_movie
from controllers.auth_controller import login, register
from controllers.access_controller import create_access_request, list_access_requests, get_access_request, review_request, get_audit_log_for_request
from controllers.workflow_controller import register_workflow_user

movie_router = APIRouter(prefix="/movies", tags=["movies"])
sessions_router = APIRouter(prefix="/sessions", tags=["sessions"])
users_router    = APIRouter(prefix="/users",          tags=["users"])
workflow_router = APIRouter(prefix="/workflow-users", tags=["workflow-users"])
access_router = APIRouter(prefix="/access-requests", tags=["access-requests"])

movie_router.get("/", response_model=MovieSearchResponse)(search_movies)
movie_router.get("/{movie_id}", response_model=Movie)(get_movie)
movie_router.post("/")(upload_movies)
movie_router.patch("/{movie_id}", response_model=Movie)(edit_movie)

sessions_router.post("/", response_model=TokenResponse)(login)

users_router.post("/", response_model=RegistrationResponse)(register)
workflow_router.post("/")(register_workflow_user)

access_router.post("/", response_model=AccessRequestResponse)(create_access_request)
access_router.get("/", response_model=list[AccessRequestResponse])(list_access_requests)
access_router.get("/{reference_id}/audit")(get_audit_log_for_request)
access_router.get("/{reference_id}", response_model=AccessRequestResponse | AccessRequestStatusResponse)(get_access_request)
access_router.patch("/{reference_id}", response_model=ReviewResponse)(review_request)


def register_routers(app: FastAPI):
    app.include_router(sessions_router)
    app.include_router(users_router)
    app.include_router(workflow_router)
    app.include_router(movie_router)
    app.include_router(access_router)
