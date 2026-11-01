# Image de l'API. Construite depuis la racine du dépôt (contexte « . »),
# car l'API importe le schéma partagé de db/.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.8 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dépendances d'abord : cette couche reste en cache tant que uv.lock ne change pas.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY db/ db/
COPY api/ api/
COPY alembic.ini ./

# Utilisateur sans privilèges : l'API est exposée via le tunnel.
RUN useradd --create-home api
USER api

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
