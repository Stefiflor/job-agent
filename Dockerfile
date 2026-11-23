# Imagen de despliegue: compila la UI de Vue y la sirve desde la API de Python.
# Localmente no hace falta: `uv run job-agent api` usa tu login de Claude.
# En un contenedor no hay login: necesita ANTHROPIC_API_KEY, y eso se paga por uso.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist
# private/ (CV, criterios, resultados) se monta como volumen: nunca va dentro de la imagen.
VOLUME ["/app/private"]
ENV DATABASE_URL=postgresql://jobagent:jobagent@db:5432/jobagent
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "job_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
