# job-agent

Agente que busca ofertas remotas (Himalayas API) y las evalúa contra un CV con Claude (Agent SDK, Python).

## Comandos
- `uv sync` — instala dependencias
- `uv run job-agent buscar` — busca y filtra → `private/candidatas.json`
- `uv run job-agent evaluar --limite 3` — evalúa con Claude → `private/evaluadas.json` (saltea las ya evaluadas)
- `uv run job-agent agente "pedido" --objetivo 5 --max-evaluaciones 8` — agente con herramientas
- `uv run job-agent evals preparar --n 25` / `evals correr --repeticiones 2` — evals contra etiquetas humanas
- `docker compose up -d` — Postgres + pgvector en localhost:5433
- `uv run job-agent rag indexar --feed 10` / `rag buscar "..."` / `rag similares <link>` — índice semántico
- `uv run job-agent carta <link> [--idioma Spanish]` — carta con RAG sobre `private/experiencia.md` + verificador
- `uv run pytest` — tests (los de pgvector necesitan `DATABASE_URL_TEST`)

## Estructura
- `src/job_agent/filtros.py` — filtros determinísticos, funciones puras. Todo filtro nuevo lleva test.
- `src/job_agent/sources/` — un módulo por fuente de ofertas.
- `src/job_agent/evaluador.py` — prompt, schema y llamada al SDK.
- `src/job_agent/vectores.py`, `embeddings.py` — pgvector + model2vec (Embedder es un Protocol).
- `src/job_agent/carta.py` — RAG sobre la experiencia: redactor + chequeo de citas + verificador.
- `src/job_agent/agente.py` — agente: herramientas MCP en proceso, presupuesto, hook de logs.
- `src/job_agent/models.py` — modelos pydantic; `Evaluacion` define el JSON Schema de la salida.
- `private/` — CV, criterios y resultados. Ignorado por git. Nunca commitear nada de ahí.
- `docs/APRENDIZAJE.md` — qué se hizo en cada fase y por qué.

## Reglas
- Lo que se puede decidir con código va en `filtros.py`; el LLM solo para criterio (encaje, leer texto libre).
- Una llamada al modelo por oferta. `tools=[]` en el evaluador.
- Nombres de dominio en español, como el resto del código.
