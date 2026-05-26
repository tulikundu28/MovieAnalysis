# Movies API

FastAPI + PostgreSQL app for browsing and managing movies, with a role-based access-request workflow and a single-page Bootstrap 5 UI.

---

## Quick start (local dev)

```bash
cp .env.example .env          # fill in POSTGRES_PASSWORD and JWT_SECRET
docker compose up -d          # starts postgres + app; migrations run automatically
open http://localhost:8000
```

Generate secrets:
```bash
openssl rand -hex 16   # POSTGRES_PASSWORD
openssl rand -hex 32   # JWT_SECRET
```

Seeded admin account: `tuli.ku09@gmail.com` / `TestAdmin123`

Rebuild the DB (required when `init.sql` changes schema):
```bash
docker compose down -v && docker compose up -d
```

---

## Deploy on EC2

### 1. Install Docker

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker ubuntu
```

### 2. Export secrets (no .env file on disk)

```bash
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=$(aws secretsmanager get-secret-value \
    --secret-id prod/movies/postgres_password --query SecretString --output text)
export POSTGRES_DB=moviesdb
export POSTGRES_PORT=5432
export JWT_SECRET=$(aws secretsmanager get-secret-value \
    --secret-id prod/movies/jwt_secret --query SecretString --output text)
```

Or write a `/etc/movies.env` owned by root (mode 600) and use `EnvironmentFile=` in a systemd unit.

### 3. Pin the image digest and deploy

After pushing a release tag (e.g. `v1.2.3`), get the digest:
```bash
docker pull tulikundu/movie-analysis:1.2.3
docker inspect --format='{{index .RepoDigests 0}}' tulikundu/movie-analysis:1.2.3
```

Update the `image:` line in `docker-compose.prod.yml`, then:

```bash
git clone https://github.com/tulikundu/MovieAnalysis.git
cd MovieAnalysis

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build
```

The app container runs `alembic upgrade head` on startup — schema migrations are applied automatically before the server accepts traffic.

### 4. Redeploy

```bash
# update docker-compose.prod.yml with the new digest, then:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build
```

---

## Releasing a new version

1. Tag the commit: `git tag v1.2.3 && git push origin v1.2.3`
2. GitHub Actions builds `linux/amd64` + `linux/arm64` and pushes tags  
   `1.2.3`, `1.2`, `1`, and `latest` to Docker Hub.
3. Requires repository secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`

---

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `POSTGRES_PASSWORD` | yes | — | fail-fast on startup if missing |
| `POSTGRES_USER` | yes | — | |
| `POSTGRES_DB` | yes | — | |
| `JWT_SECRET` | yes | — | fail-fast on startup if missing |
| `POSTGRES_HOST` | no | `localhost` | set to `db` inside compose |
| `POSTGRES_PORT` | no | `5432` | |
| `JWT_ALGORITHM` | no | `HS256` | |
| `JWT_EXPIRY_MINUTES` | no | `60` | |
| `APP_ENV` | no | `dev` | set to `prod` to silence SQLAlchemy query logs |
