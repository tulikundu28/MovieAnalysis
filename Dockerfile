# syntax=docker/dockerfile:1
# To pin to a digest after pulling:
#   docker inspect --format='{{index .RepoDigests 0}}' python:3.13.3-slim

# ---- builder: install Python deps only ----
FROM python:3.13.3-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- final: lean runtime image ----
FROM python:3.13.3-slim

RUN addgroup --system appgroup \
 && adduser --system --ingroup appgroup --no-create-home appuser

WORKDIR /app

COPY --from=builder /install /usr/local

COPY auth/         auth/
COPY controllers/  controllers/
COPY db/           db/
COPY migrations/   migrations/
COPY models/       models/
COPY repositories/ repositories/
COPY services/     services/
COPY ui/           ui/
COPY utils/        utils/
COPY alembic.ini main.py routers.py ./

USER appuser

ENV APP_PORT=8000
# EXPOSE reflects the build-time default; override APP_PORT at runtime to change the actual port.
EXPOSE ${APP_PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://localhost:'+os.environ.get('APP_PORT','8000')+'/healthz')" || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${APP_PORT}"]
