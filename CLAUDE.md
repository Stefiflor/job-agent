# job-agent

Agente que busca ofertas remotas (Himalayas API) y las evalúa contra un CV con Claude (Agent SDK, Python).

## Comandos
- `uv sync` — instala dependencias
- `uv run job-agent buscar` — busca y filtra → `private/candidatas.json`
- `uv run job-agent evaluar --limite 3` — evalúa con Claude → `private/evaluadas.json` (saltea las ya evaluadas)
- `uv run pytest` — tests

## Estructura
- `src/job_agent/filtros.py` — filtros determinísticos, funciones puras. Todo filtro nuevo lleva test.
- `src/job_agent/sources/` — un módulo por fuente de ofertas.
- `src/job_agent/evaluador.py` — prompt, schema y llamada al SDK.
- `src/job_agent/models.py` — modelos pydantic; `Evaluacion` define el JSON Schema de la salida.
- `private/` — CV, criterios y resultados. Ignorado por git. Nunca commitear nada de ahí.
- `docs/APRENDIZAJE.md` — qué se hizo en cada fase y por qué.

## Reglas
- Lo que se puede decidir con código va en `filtros.py`; el LLM solo para criterio (encaje, leer texto libre).
- Una llamada al modelo por oferta. `tools=[]` en el evaluador.
- Nombres de dominio en español, como el resto del código.
