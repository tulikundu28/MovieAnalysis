import pytest
from tests.integration.conftest import _auth

pytestmark = pytest.mark.asyncio

SAMPLE_CSV = (
    b"movieId,title,genres\n"
    b"100,New Movie A (2024),Action|Thriller\n"
    b"101,New Movie B (2023),Comedy|Drama\n"
    b"102,New Movie C (2022),(no genres listed)\n"
)

DUPLICATE_CSV = (
    b"movieId,title,genres\n"
    b"100,New Movie A Updated (2024),Action|Thriller|Updated\n"
)


# ── Search / list ─────────────────────────────────────────────────────────────

async def test_search_returns_movies_without_auth(client):
    resp = await client.get("/movies/")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert len(data["data"]) > 0


async def test_search_by_title(client):
    resp = await client.get("/movies/?title=toy")
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert any("Toy" in m["title"] for m in results)


async def test_search_by_genre(client):
    resp = await client.get("/movies/?genre=Crime")
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert all("Crime" in (m["genres"] or []) for m in results)


async def test_search_by_release_year(client):
    resp = await client.get("/movies/?release_year=1977")
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert all(m["release_year"] == 1977 for m in results)


async def test_search_no_match_returns_empty(client):
    resp = await client.get("/movies/?title=zzznomatchzzz")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_search_pagination_cursor(client):
    resp1 = await client.get("/movies/?page_size=2")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert len(data1["data"]) == 2
    assert data1["next_cursor"] is not None

    resp2 = await client.get(f"/movies/?page_size=2&cursor={data1['next_cursor']}")
    assert resp2.status_code == 200
    data2 = resp2.json()
    ids1 = {m["movie_id"] for m in data1["data"]}
    ids2 = {m["movie_id"] for m in data2["data"]}
    assert ids1.isdisjoint(ids2)


async def test_search_last_page_next_cursor_is_null(client):
    resp = await client.get("/movies/?page_size=100")
    assert resp.status_code == 200
    assert resp.json()["next_cursor"] is None


async def test_search_page_size_exceeds_max_returns_422(client):
    resp = await client.get("/movies/?page_size=999")
    assert resp.status_code == 422


# ── Get by ID ─────────────────────────────────────────────────────────────────

async def test_get_movie_by_id(client):
    resp = await client.get("/movies/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["movie_id"] == 1
    assert data["title"] == "Toy Story"
    assert data["release_year"] == 1995
    assert "Animation" in data["genres"]


async def test_get_movie_unknown_id_returns_404(client):
    resp = await client.get("/movies/999999")
    assert resp.status_code == 404


# ── CSV upload ────────────────────────────────────────────────────────────────

async def test_upload_csv_requires_auth(client):
    resp = await client.post("/movies/", files={"file": ("movies.csv", SAMPLE_CSV, "text/csv")})
    assert resp.status_code == 403


async def test_upload_csv_requires_movie_admin_role(client, full_access_token):
    resp = await client.post("/movies/",
                             files={"file": ("movies.csv", SAMPLE_CSV, "text/csv")},
                             headers=_auth(full_access_token))
    assert resp.status_code == 403


async def test_upload_csv_as_movie_admin_succeeds(client, movie_admin_token):
    resp = await client.post("/movies/",
                             files={"file": ("movies.csv", SAMPLE_CSV, "text/csv")},
                             headers=_auth(movie_admin_token))
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 3


async def test_upload_csv_twice_is_idempotent(client, movie_admin_token):
    headers = _auth(movie_admin_token)
    await client.post("/movies/", files={"file": ("movies.csv", SAMPLE_CSV, "text/csv")}, headers=headers)
    resp = await client.post("/movies/", files={"file": ("movies.csv", SAMPLE_CSV, "text/csv")}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 3


async def test_upload_csv_updates_existing_movie(client, movie_admin_token):
    headers = _auth(movie_admin_token)
    await client.post("/movies/", files={"file": ("movies.csv", SAMPLE_CSV, "text/csv")}, headers=headers)
    await client.post("/movies/", files={"file": ("movies.csv", DUPLICATE_CSV, "text/csv")}, headers=headers)
    resp = await client.get("/movies/100")
    assert resp.status_code == 200
    assert "Updated" in resp.json()["title"]


async def test_upload_csv_as_workflow_admin_succeeds(client, admin_token):
    resp = await client.post("/movies/",
                             files={"file": ("movies.csv", SAMPLE_CSV, "text/csv")},
                             headers=_auth(admin_token))
    assert resp.status_code == 200


# ── Edit movie ────────────────────────────────────────────────────────────────

async def test_edit_movie_requires_auth(client):
    resp = await client.patch("/movies/1", json={"title": "Updated Title"})
    assert resp.status_code == 403


async def test_edit_movie_requires_movie_admin_role(client, full_access_token):
    resp = await client.patch("/movies/1",
                              json={"title": "Updated Title"},
                              headers=_auth(full_access_token))
    assert resp.status_code == 403


async def test_edit_movie_updates_title(client, movie_admin_token):
    resp = await client.patch("/movies/1",
                              json={"title": "Toy Story Updated"},
                              headers=_auth(movie_admin_token))
    assert resp.status_code == 200
    assert resp.json()["title"] == "Toy Story Updated"


async def test_edit_movie_updates_genres(client, movie_admin_token):
    resp = await client.patch("/movies/1",
                              json={"genres": ["Animation", "Comedy"]},
                              headers=_auth(movie_admin_token))
    assert resp.status_code == 200
    assert resp.json()["genres"] == ["Animation", "Comedy"]


async def test_edit_movie_unknown_id_returns_404(client, movie_admin_token):
    resp = await client.patch("/movies/999999",
                              json={"title": "Ghost"},
                              headers=_auth(movie_admin_token))
    assert resp.status_code == 404


async def test_edit_movie_empty_genres_returns_422(client, movie_admin_token):
    resp = await client.patch("/movies/1",
                              json={"genres": []},
                              headers=_auth(movie_admin_token))
    assert resp.status_code == 422
