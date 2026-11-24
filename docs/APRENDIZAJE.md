# Aprendizaje: cómo y por qué se construyó job-agent

Material de estudio por fase. Cada fase dice qué se hizo, por qué, qué se descartó y qué te pueden preguntar en una entrevista.

---

## Fase 0 — Prototipo en TypeScript (`v1-typescript/`)

**Qué hace:** busca ofertas en Himalayas, las filtra con código y le pide a Claude que evalúe cada una contra el CV.

**Resultado:** 178 ofertas → 27 candidatas → 3 "aplicar", 16 "dudoso", 8 "descartar".

**Lo que enseñaron los datos (y por qué importa):**
- El campo `remote` de Arbeitnow decía `false` en ofertas que en el título dicen "Remote". Los datos estructurados de una API no son confiables.
- "Remote" casi nunca es "desde cualquier país": `locationRestrictions` decía `["Germany"]`, `["South Africa"]`, etc.
- Cuando no hay salario, `salaryPeriod` igual dice `"annual"`. Hay que ignorarlo.
- Hay ofertas basura: descripción de plantilla ("Just one more step...").
- micro1 decía "cualquier país" en la API, pero el texto aclaraba que contratan en EE.UU. El LLM lo detectó leyendo el texto.

**Por qué se migró a Python:** Python era el requisito que más faltaba en las ofertas de AI Engineer (~11 de 27). El prototipo en TS sirvió para validar la idea rápido; la versión Python es la que se mantiene.

---

## Fase 1 — Migración a Python

### Arquitectura

```
criterios.json ─┐
                ▼
Himalayas API → sources/himalayas.py → filtros.py → candidatas.json → evaluador.py → evaluadas.json
  (fetch)          (dedup por guid)     (código)                        (Claude + schema)
```

Esto todavía es un **workflow**, no un agente: el código decide los pasos y el modelo solo evalúa. Ver Fase 2.

### Decisiones y trade-offs

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| Filtros en código, LLM solo para criterio | Determinístico, testeable, gratis y reproducible. El LLM se usa donde aporta: leer texto libre y juzgar encaje. | Que el LLM filtre todo: más caro, no reproducible, imposible de testear. |
| Una llamada al modelo por oferta | Si una falla, no arruina las demás. El modelo no mezcla ofertas. | Mandar las 27 juntas: un error rompe todo y el contexto se contamina. |
| `pydantic` para modelos | El mismo modelo `Evaluacion` genera el JSON Schema que recibe el SDK y valida la respuesta. Una sola fuente de verdad. | Schema escrito a mano en un dict: se desincroniza del código. |
| Validar la respuesta aunque el SDK ya valide | Defensa en profundidad: si cambia el SDK o el schema, el error aparece acá y no más adelante. | Confiar a ciegas en `structured_output`. |
| `tools=[]` | Desactiva todas las herramientas: el evaluador no las necesita. | `allowed_tools=[]`: **no desactiva nada**, solo dice cuáles se aprueban sin preguntar. Error del prototipo TS, corregido acá. |
| Saltear ofertas ya evaluadas | Correrlo cada semana solo gasta cupo en ofertas nuevas. `--reevaluar` fuerza todo. | Reevaluar siempre: gasta cupo de más. |
| Guardar después de cada evaluación | Si se corta a la mitad, no se pierde lo hecho. | Guardar al final. |
| Agent SDK en vez de la API directa | Permite usar el plan Pro (login de claude.ai) sin pagar por uso. | API directa (más simple para una sola respuesta sin herramientas), pero se paga por token. |
| `uv` como gestor | Rápido, maneja el entorno virtual solo, lockfile reproducible. | `pip` + `venv` a mano. |
| Tolerancia de ±2 h en zona horaria | Una oferta de costa este de EE.UU. (`[-5, -4]`) es trabajable desde Argentina (UTC-3). Sin tolerancia se descartaba el 63% de las ofertas. | Coincidencia exacta. |

### Cómo autentica el SDK

- Sin `ANTHROPIC_API_KEY` en el entorno, usa el login de Claude Code → consume del cupo del plan Pro.
- El mensaje de inicio trae `apiKeySource`: `"none"` = login de claude.ai; `"ANTHROPIC_API_KEY"` = se cobra a la key.
- Para que corra solo (CI, servidor) hace falta API key: el plan Pro no se puede usar ahí.

### Tests (`tests/`)

17 tests con casos reales que aparecieron en la API: salario por hora de micro1, salario nulo de DECODE, restricción "solo Alemania", HTML doblemente escapado de Arbeitnow, "Internal" que no debe confundirse con "Intern".

Correr: `uv run pytest`

### Preguntas de entrevista sobre esta fase

- **¿Por qué no dejaste que el LLM hiciera todo?** Porque lo determinístico es más barato, reproducible y testeable. El LLM va donde hace falta criterio o leer texto libre.
- **¿Cómo garantizás que el LLM devuelva JSON válido?** Structured outputs con JSON Schema generado desde pydantic; el SDK reintenta si no cumple, y además valido con pydantic.
- **¿Qué pasa si la API devuelve datos incorrectos?** El filtro por código usa los campos estructurados; el LLM tiene una regla explícita: si el texto contradice a los campos, manda el texto.
- **¿Cómo controlás el costo?** Filtro antes del LLM (178 → 27), recorte de descripción a 8000 caracteres, caché de evaluadas, y se registra `total_cost_usd` por oferta.
- **¿Qué mejorarías?** Ver fases siguientes: agente con herramientas, evals, RAG.

### Ajustes después de la primera corrida real

- **Residencia mixta (campo `situacion` en criterios).** Hay perfiles que reparten el año entre países. Un filtro por país no alcanza para eso: los países permitidos pasan por código (`paisesResidencia`) y el matiz ("exige residencia fija todo el año") lo decide el LLM leyendo `situacion`. Es el mismo patrón de siempre: código para lo binario, LLM para lo ambiguo.
- **Bug: `aclose(): asynchronous generator is already running`.** El evaluador hacía `return` dentro del `async for` sobre `query()`. Eso deja el generador async a medio consumir y, al cerrarlo, Python 3.14 tira el error. Solución: consumir el stream completo y procesar el `ResultMessage` después del loop. Hay un test de regresión que lo cubre.
  - *Pregunta de entrevista:* "¿Qué pasa si cortás un async generator a mitad?" → queda pendiente de cerrar; su `finally` corre más tarde, en otro contexto, y puede fallar. Se evita consumiéndolo completo o usando `contextlib.aclosing`.
- **Costo medido:** 3 evaluaciones = USD 0,264 estimados (~USD 0,09 por oferta). Evaluar 56 candidatas equivaldría a ~USD 5 si se pagara por API. Con el plan Pro sale del cupo.
- **Agregadores duplican ofertas:** "RemoteJobsOne" republica la oferta de micro1 sin nombrar a la empresa. El LLM lo marcó como sospechoso. Pendiente: deduplicar por título + salario entre fuentes.

---

## Fase 2 — Agente con herramientas (`src/job_agent/agente.py`)

**Qué cambia:** en la Fase 1 el código decidía los pasos (buscar → filtrar → evaluar todo). Ahora el modelo recibe un objetivo ("encontrá 5 ofertas para aplicar") y **decide él** qué consultas hacer, qué ofertas leer, cuáles evaluar y cuándo parar. Eso es un agente; lo anterior era un workflow.

```
pedido + objetivo + presupuesto
          │
          ▼
     ┌─ Claude (loop) ─────────────────────────────┐
     │  decide → llama herramienta → lee resultado │
     └────┬──────────┬──────────┬──────────┬───────┘
          ▼          ▼          ▼          ▼
   buscar_ofertas ver_oferta evaluar_oferta guardar_en_tracker
   (API + filtros) (barata)  (otro LLM, cara) (private/tracker.json)
          │
          ▼
   informe final con JSON Schema (ranking + resumen)
```

**Herramientas** (servidor MCP en proceso, `create_sdk_mcp_server` + `@tool`):

| Herramienta | Qué hace | Por qué existe |
|---|---|---|
| `buscar_ofertas` | API de Himalayas + los mismos filtros de la Fase 1. Devuelve una lista corta, sin descripciones. | Ahorrar contexto: 20 descripciones completas llenarían la ventana del modelo. |
| `ver_oferta` | Muestra la descripción recortada a 3000 caracteres. | Paso barato para descartar antes de gastar una evaluación. |
| `evaluar_oferta` | Llama al evaluador de la Fase 1, que es otro LLM con salida estructurada. | Reutiliza código testeado. Es la herramienta cara y tiene presupuesto. |
| `guardar_en_tracker` | Agrega la oferta a `private/tracker.json`. | Acción con efecto: solo acepta veredicto "aplicar" y no duplica. |

**Decisiones y trade-offs**

| Decisión | Por qué |
|---|---|
| IDs cortos (`o1`, `o2`) en vez de URLs | Menos tokens y menos errores al copiar. Una misma oferta en dos búsquedas mantiene su id. |
| Presupuesto de evaluaciones en el **código**, no solo en el prompt | El prompt pide cuidar el presupuesto, pero la herramienta lo hace cumplir: devuelve error al pasarse. Nunca confiar en que el modelo respete un límite solo porque se lo pediste. |
| Validaciones dentro de las herramientas (tracker solo "aplicar", id inexistente = error) | Las herramientas son la frontera de seguridad del agente. Los errores vuelven al modelo con `is_error` para que se corrija. |
| `tools=[]` + `allowed_tools` con solo las 4 herramientas | El agente no puede usar Bash, leer archivos ni navegar: superficie mínima. |
| `max_turns=40` | Corta un loop infinito si el modelo se traba. |
| Hook `PostToolUse` → `private/logs/agente-FECHA.jsonl` | Traza de cada llamada (herramienta, input, duración). Base de la observabilidad. |
| Informe final con `output_format` | Structured outputs también funciona después de usar herramientas. |
| Herramientas como closures sobre una `Sesion` | Se testean llamando al handler directo, sin modelo ni red (`tests/test_agente.py`). |

**Costo:** el informe separa el costo del agente (sus turnos) del costo de las evaluaciones, porque son llamadas distintas al modelo.

**Preguntas de entrevista**
- **¿Qué diferencia hay entre un workflow y un agente?** En el workflow, el código fija el camino. En el agente, el modelo elige las acciones en un loop. Conviene un workflow cuando los pasos son fijos: es más predecible y más barato. Conviene un agente cuando el camino depende de lo que va encontrando.
- **¿Cómo evitás que un agente gaste de más o haga algo peligroso?** Con límites en el código (presupuesto, `max_turns`), herramientas mínimas y validaciones dentro de cada herramienta. El prompt solo no alcanza.
- **¿Cómo testeás un agente?** Las herramientas, con tests unitarios sin modelo. El comportamiento del agente completo, con evals (Fase 3).
- **¿Por qué la evaluación es una herramienta y no la hace el agente mismo?** Porque devuelve un schema fijo y testeado, se puede cachear y ponerle presupuesto, y mantiene el contexto del agente chico.

---

## Fase 3 — Evals (`src/job_agent/evals.py`)

**Por qué:** sin evals no se puede saber si un cambio de prompt, de modelo o de CV mejora o empeora el agente. "Me parece que anda mejor" no es una métrica.

**Cómo funciona**
1. `job-agent evals preparar --n 25`: elige 25 ofertas ya evaluadas en una **muestra estratificada** (un tercio de cada veredicto del modelo) y las escribe en `private/evals/etiquetas.csv`, **sin mostrar lo que dijo el modelo**.
2. La candidata completa `tu_veredicto` (aplicar / dudoso / descartar). Ese es el *golden set*.
3. `job-agent evals correr --repeticiones 2`: evalúa cada oferta N veces y compara.

**Métricas**

| Métrica | Qué mide | Por qué importa |
|---|---|---|
| Acuerdo exacto | % de evaluaciones con el mismo veredicto que el humano | Calidad general |
| Errores graves | % aplicar ↔ descartar | El error caro: perder una buena oferta o perder tiempo en una mala |
| Consistencia | % de ofertas con el mismo veredicto en todas las repeticiones | Los LLM no son determinísticos; si cambia de opinión, no es confiable |
| Desvío del encaje | Cuánto varía el puntaje entre repeticiones | Dice si una diferencia de 5 puntos es real o ruido |
| Matriz de confusión | Dónde se equivoca | Si confunde "dudoso" con "descartar", el ajuste del prompt es distinto que si confunde extremos |

**Decisiones**
- **Etiquetado ciego:** si ves el veredicto del modelo antes de decidir, tendés a coincidir (sesgo de anclaje) y la métrica sale inflada.
- **Muestra estratificada:** la mayoría de las ofertas son "dudoso"; con una muestra al azar casi no habría extremos para medir.
- **Repeticiones:** sin repetir, no se puede separar "el modelo empeoró" de "salió distinto por azar".
- **Semilla fija (42):** la muestra es reproducible.
- **Métricas como funciones puras con tests:** el número que va al README tiene que ser confiable.

**Preguntas de entrevista**
- **¿Cómo evaluás un sistema con LLM?** Con un golden set etiquetado por una persona, métricas definidas antes de mirar los resultados, repeticiones para medir varianza, y foco en los errores caros, no solo en el acierto promedio.
- **¿Qué hacés si el acuerdo es bajo?** Miro la matriz de confusión y los casos fallidos, ajusto el prompt o el schema y vuelvo a correr las evals sobre el mismo set. Nunca ajusto mirando los mismos casos con los que después reporto: para eso se separa un set de validación.
- **¿Por qué no usar otro LLM como juez?** Para un veredicto subjetivo ("¿me conviene?") la referencia tiene que ser la persona. LLM-as-judge sirve para criterios objetivos, como evaluar la calidad de la carta de presentación (Fase 5).

---

## Fase 4 — Índice vectorial y búsqueda semántica (`vectores.py`, `embeddings.py`)

**Qué agrega:** las ofertas (del feed general de Himalayas, 20 por página, más las búsquedas por rol) se guardan en Postgres con un **embedding**: un vector que representa el significado del texto. Así se puede buscar por significado ("agentes que llamen APIs para atención al cliente") y encontrar ofertas que no dicen "LLM engineer" en el título.

```
Himalayas (roles + feed) → filtros → texto (título + empresa + descripción)
                                        │
                                  model2vec (local)
                                        ▼
                     Postgres + pgvector: tabla `ofertas` (vector + índice HNSW)
                                        │
       rag buscar "..."  ·  rag similares <link>  ·  herramienta del agente buscar_semantico
```

**¿Esto es RAG?** Es la mitad *retrieval*. En RAG completo, lo recuperado alimenta una generación. Acá lo usa el agente para decidir qué evaluar, que es *agentic retrieval*. La generación con contexto recuperado llega en la Fase 5, con la carta de presentación. En una entrevista conviene decirlo con precisión: es mejor que vender una búsqueda vectorial como si fuera RAG.

**Decisiones y trade-offs**

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| pgvector en Postgres | Un solo sistema para datos y vectores, SQL normal y transacciones. Para miles o cientos de miles de vectores alcanza de sobra. | Base vectorial dedicada (Pinecone, Qdrant, Weaviate): un servicio más que operar, y no hace falta a esta escala. |
| model2vec (`potion-base-8M`) | Embeddings estáticos: corre en CPU en milisegundos, sin PyTorch (que no publica versiones para Mac Intel), y es gratis. | `sentence-transformers` (mejor calidad, pero pesado y sin wheels para Intel) o una API (Voyage, OpenAI): mejor calidad, pero se paga y es una dependencia externa. |
| `Embedder` como Protocol | Cambiar de modelo es una clase nueva, no un refactor. Los tests usan un embedder falso que no descarga nada. | Llamar a model2vec directo en todos lados. |
| Vectores normalizados + `vector_cosine_ops` | La similitud coseno es la estándar para texto. Normalizar hace que coseno y producto punto coincidan. | Distancia euclídea. |
| Índice HNSW | Búsqueda aproximada rápida, sin tener que reentrenar el índice al agregar datos. | IVFFlat: necesita datos previos para entrenar las listas. |
| Guardar también las ofertas que **no** pasan los filtros, con el motivo | Sirve para analizar el mercado ("¿cuántas piden residencia fija?"); `--todas` las muestra. | Indexar solo las filtradas. |
| Control de dimensión al crear el esquema | Si se cambia de modelo, los vectores viejos no son comparables: avisa y pide `--recrear` en vez de fallar raro. | No validar. |
| Herramienta del agente que falla con elegancia | Si Docker está apagado, devuelve `is_error` y el agente sigue con la búsqueda por palabra clave. | Que el agente se caiga. |
| Puerto 5433 y solo `127.0.0.1` | No choca con otro Postgres y no queda expuesto en la red. | 5432 en todas las interfaces. |

**Tests:** los de `test_vectores.py` corren contra un **Postgres real con pgvector** (no un mock), con un embedder falso de bolsa de palabras. Se saltean si no está `DATABASE_URL_TEST`.

**Preguntas de entrevista**
- **¿Cuándo usás búsqueda semántica y cuándo por palabra clave?** Palabra clave para términos exactos (un framework, un título); semántica para intención y sinónimos. Lo mejor suele ser combinarlas (búsqueda híbrida), que es lo que hace el agente con sus dos herramientas.
- **¿Por qué pgvector y no Pinecone?** Por escala y operación: a esta escala, Postgres alcanza y evita sumar otro servicio. Cambiaría si hubiera decenas de millones de vectores o necesitara filtros y latencias que Postgres no da.
- **¿Qué pasa si cambiás el modelo de embeddings?** Hay que reindexar todo, porque los vectores de modelos distintos no son comparables. Por eso se guarda el nombre del modelo en cada fila y se valida la dimensión.
- **¿Cómo medirías la calidad del retrieval?** Con un set de consultas y las ofertas que deberían aparecer, midiendo recall@k. Es una extensión natural de las evals de la Fase 3.

---

## Fase 5 — Carta de presentación con RAG y verificación (`carta.py`)

**Ahora sí es RAG completo:** lo recuperado (fragmentos de tu experiencia) alimenta la generación (la carta). Y se agrega un paso que casi nadie muestra: **verificar que la carta no invente**.

```
private/experiencia.md → fragmentos (1 por bullet: E1, E2, ...)
                               │ embeddings (mismo Embedder)
oferta ──────────────► top-10 fragmentos más parecidos
                               │
                      REDACTOR (LLM): carta + lista de afirmaciones con sus fuentes [E3, E7]
                               │
              chequeo en código: ¿cita fragmentos que existen?  ──no──┐
                               │ sí                                    │
                      VERIFICADOR (otro LLM): ¿cada afirmación está    │
                      respaldada por sus fragmentos? ¿exagera?         │
                               │                                       │
                 respaldada ── sí → private/cartas/empresa--puesto.md  │
                               │ no                                    │
                     feedback con los problemas ◄──────────────────────┘
                     → reescribir (máximo 2 intentos)
```

**Decisiones y trade-offs**

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| Base de experiencia escrita por la candidata, un hecho por bullet | El modelo solo puede afirmar lo que está escrito. La calidad de la carta depende de esta fuente, no del prompt. | Generar desde el CV solo: cartas genéricas. |
| Retrieval **en memoria** (numpy), no en pgvector | Son ~30 fragmentos: calcular 30 similitudes es instantáneo. Llevarlos a la base sería complejidad sin beneficio. | pgvector: correcto para miles de ofertas, exagerado para 30 fragmentos. |
| La carta trae sus afirmaciones con fuentes | Hace que la verificación sea concreta y auditable: se ve de qué fragmento sale cada frase. | Texto libre: imposible de verificar sistemáticamente. |
| Chequeo determinístico antes del verificador | Si cita un fragmento inexistente, se rechaza sin gastar una llamada. Lo barato y seguro primero, igual que con los filtros. | Mandar todo al verificador. |
| Verificador que lee la carta completa | El redactor podría afirmar algo y no listarlo. | Revisar solo la lista de afirmaciones. |
| Máximo 2 intentos y marca "CON PROBLEMAS" | Un loop sin límite gasta sin garantía de converger. Si falla, la persona revisa. | Reintentar hasta que pase. |
| Se guardan los fragmentos recuperados junto a la carta | Para depurar: si la carta es mala, ¿fue el retrieval o la generación? | Guardar solo la carta. |

**Relación con la experiencia en Quantic Core:** es el mismo patrón que el verificador anti-alucinación del agente de turnos (un segundo modelo contrasta lo que dice el primero contra una fuente de verdad). Allá la fuente de verdad era el log de herramientas; acá, los fragmentos de experiencia. Es una muy buena historia para contar: aplicaste el mismo patrón en dos dominios.

**Preguntas de entrevista**
- **¿Cómo evitás alucinaciones en RAG?** Restringiendo la generación al contexto recuperado, pidiendo citas por afirmación, validando las citas en código y usando un verificador independiente con un límite de reintentos.
- **¿Por qué un segundo modelo y no el mismo?** Con un prompt distinto y sin el objetivo de "escribir algo convincente", el verificador tiene incentivos distintos. Igual no es infalible: por eso además se guardan las fuentes para que una persona revise.
- **¿Qué medirías?** El porcentaje de cartas verificadas al primer intento, los problemas más comunes y, a mano, una muestra de cartas para estimar falsos negativos del verificador (cosas inventadas que dejó pasar).

### Ajuste: base de experiencia chica = sin retrieval

La primera carta real (Appsilon) salió verificada, pero **dejó afuera lo más fuerte**: el verificador anti-alucinación y las herramientas del agente de turnos. El retrieval elegía 10 de 28 fragmentos por similitud con la oferta, y las líneas del proyecto personal compartían más palabras con el aviso ("agent", "tools", "SDK").

Arreglo: si la base tiene 60 fragmentos o menos, se pasan **todos**, y el prompt pide priorizar el trabajo en producción por sobre los proyectos personales.

*Lección para entrevistas:* RAG no siempre mejora. Si todo el contexto entra en la ventana del modelo, filtrar puede empeorar el resultado. El retrieval es para cuando no entra o cuando es caro. Esta decisión se tomó mirando una salida real, no por intuición.

---

## Fase 6 — API (`api.py`, FastAPI)

**Qué es:** la misma lógica de la CLI, expuesta por HTTP para la UI. `uv run job-agent api` → http://127.0.0.1:8000, con documentación automática en `/docs`.

| Endpoint | Qué hace |
|---|---|
| `GET /api/resumen` | Totales por veredicto, costo acumulado, tracker por estado |
| `GET /api/ofertas` · `GET /api/ofertas/{id}` | Ofertas evaluadas (filtros) y detalle con evaluación y carta guardada |
| `POST /api/buscar` | Busca en Himalayas y filtra |
| `GET /api/evaluar/stream` · `GET /api/agente/stream` | **Server-Sent Events**: progreso en vivo de la evaluación y de cada herramienta que usa el agente |
| `POST /api/ofertas/{id}/carta` | Carta con RAG y verificación |
| `GET/POST/PATCH /api/tracker` | Postulaciones y sus estados |
| `GET /api/rag/buscar` | Búsqueda semántica (503 si Docker está apagado) |
| `GET /api/evals` | Métricas del último eval |

**Decisiones y trade-offs**

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| SSE para el agente y la evaluación | Son tareas de 30 s a varios minutos. SSE es HTTP normal, unidireccional y el navegador lo soporta nativo (`EventSource`). | WebSockets: bidireccional, más complejo y no hace falta. Polling: más requests y más latencia. |
| El agente emite **eventos** (`agente.eventos`) y la CLI y la API los consumen | Una sola implementación, dos interfaces. Refactor hecho para la Fase 6. | Duplicar el loop en la API. |
| Ids estables = hash del link sin query string | El mismo aviso con distinto `utm_source` es la misma oferta. | Índices de array: cambian al reordenar. |
| Escritura atómica (archivo temporal + `replace`) y `asyncio.Lock` | Nunca queda un JSON a medio escribir si el proceso se corta, y la UI puede disparar dos cambios a la vez. | Escribir directo. |
| JSON en disco y no una base para ofertas y tracker | Un solo usuario y cientos de registros. Postgres ya está, pero migrar es un cambio acotado cuando haga falta. | Meter todo en Postgres ahora. |
| `127.0.0.1` y **sin autenticación** | Es una herramienta personal: cada request con LLM gasta cupo o dinero. Exponerla sin auth sería un agujero. | Escuchar en 0.0.0.0. |
| La API sirve la UI compilada | Un solo proceso y un solo puerto. | Dos servidores en producción. |

**Docker (`Dockerfile`, perfil `app` en `docker-compose.yml`):** build en dos etapas, Node compila la UI y Python la sirve. En un contenedor no hay login de Claude: necesita `ANTHROPIC_API_KEY` y **se paga por uso**. Localmente no hace falta. `private/` se monta como volumen y nunca entra en la imagen.

**Tests (`tests/test_api.py`):** `TestClient` con archivos en un directorio temporal: filtros, 404, tracker (alta, duplicado, cambio, estado inválido = 422), stream SSE con el evaluador falso, y 503 cuando no hay base vectorial.

**Preguntas de entrevista**
- **¿Cómo mostrás el progreso de una tarea larga de un LLM?** Con streaming: SSE desde un generador async que emite un evento por paso. El cliente lo renderiza a medida que llega.
- **¿Qué falta para producción?** Auth, rate limiting y presupuesto por usuario, una cola de trabajos (que las tareas largas no dependan de una conexión HTTP abierta) y una base de datos en lugar de JSON.

---

## Fase 7 — UI en Vue (`web/`)

**Stack:** Vue 3 + TypeScript + Vite + vue-router. En desarrollo, Vite (puerto 5173) reenvía `/api` a Python (8000). En producción, la API sirve `web/dist`.

**Pantallas**
- **Ofertas:** lista ordenada por encaje, filtro por veredicto y texto, y botones para buscar ofertas nuevas y evaluar 5 más (con progreso en vivo).
- **Detalle:** evaluación (cumple, falta, alertas), alta en postulaciones y carta con verificación, con las fuentes de cada afirmación.
- **Agente:** formulario con objetivo y presupuesto, y la **bitácora en vivo** de cada herramienta que usa.
- **Postulaciones:** tablero por estado con notas. Los cambios son optimistas y se revierten si la API falla.
- **Búsqueda por significado:** consulta en lenguaje natural con la similitud dibujada como barra.

**Diseño (v3, el actual):** partí de un mockup propio (barra lateral verde solo con íconos, acento rosa) y lo llevé a 7 pantallas:
- **Inicio:** una caja tipo prompt ("¿Qué tipo de trabajo querés encontrar?") que abre el agente y lo arranca solo (`/agente?pedido=…&auto=1`), la última ejecución y 4 métricas.
- **Ofertas:** 3 columnas: filtros (encaje mínimo, tipo de puesto, ubicación, salario), lista con pestañas por veredicto y vista previa. En móvil los filtros se pliegan para que la lista se vea primero.
- **Detalle:** pestañas Análisis / Descripción / Requisitos / Carta, anillo de encaje y una "próxima acción" calculada según el estado.
- **Postulaciones:** lista o kanban, y un **seguimiento** por etapas (Evaluada → Guardada → Aplicada → Entrevista → Oferta) con la fecha de cada paso. Para eso la API guarda un `historial` y solo lo extiende cuando el estado cambia de verdad.
- **Agente:** objetivo + presupuesto a la izquierda, timeline en vivo a la derecha, ranking y costo al terminar. La API guarda la última ejecución (`/api/agente/ultima`) para mostrarla en Inicio.
- **Búsqueda semántica** y **Evals:** la matriz de confusión pinta en verde los aciertos y en rojo los errores graves (decir "aplicar" cuando era "descartar").
- Tipografía: Fredoka (redondeada, más juvenil) para títulos y números grandes; Plus Jakarta Sans para el texto. Verde en degradé para la barra lateral y los botones principales; rosa pastel para rellenos y un rosa más oscuro para texto e íconos, porque el pastel sobre blanco no tiene contraste suficiente. Íconos Lucide. El color nunca va solo: siempre con texto o ícono.

*Lecciones:* (1) la v1 (señales de pistas de esquí) era original pero exigía aprender un código visual; en una herramienta de trabajo gana lo intuitivo. (2) Antes de rediseñar conviene tener un mockup: la v3 salió en una iteración porque el objetivo estaba dibujado.

**Calidad:** TypeScript estricto (`vue-tsc` en el build), cliente de API tipado, foco visible, `prefers-reduced-motion`, diseño responsive y estados vacíos y de error con instrucciones concretas ("¿Está corriendo `uv run job-agent api`?").

**Preguntas de entrevista**
- **¿Por qué una UI en un proyecto de AI Engineer?** Porque el valor de un agente se ve cuando alguien lo usa: la bitácora en vivo hace visible el razonamiento y el costo. Y porque el puesto suele ser full stack.
- **¿Cómo manejás estados de carga largos?** Con eventos incrementales (SSE), botones deshabilitados mientras trabaja, opción de detener y mensajes de progreso concretos.

---

## Fase 8 — Publicar el repo

**Qué se hizo:**
- **README en inglés** (lo leen reclutadores de cualquier país): qué hace, arquitectura, decisiones de diseño, cómo correrlo y estado. Las capturas usan empresas inventadas para no atribuirle puntajes falsos a empresas reales.
- **Dependencias al día:** vite 8, vue-tsc 3, `@vitejs/plugin-vue` 6 y `@lucide/vue` (el paquete `lucide-vue-next` quedó deprecado). `npm audit` pasó de 5 vulnerabilidades a 0. Eran de herramientas de desarrollo, pero GitHub las marca apenas subís el repo, y un repo de portfolio con alertas rojas da mala impresión. Al actualizar, vue-tsc 3 encontró un error de tipos que la versión 2 dejaba pasar (el informe del agente estaba tipado como `any`).
- **Revisión de privacidad antes de publicar:** nada de `private/` en git, la firma de las cartas sale de `criterios.json` (campo `nombre`) en vez de estar escrita en el código, y la documentación no dice dónde vive la candidata.
- **Se borró el prototipo en TypeScript** (`v1-typescript/` y el `package.json` de la raíz). Sigue en el historial de git, que cuenta la migración a Python.

**Lección:** antes de hacer público un repo, buscá en todo el código y el historial datos personales, claves y nombres de clientes. Lo que se sube a un repo público hay que darlo por copiado, aunque después lo borres.

**Preguntas de entrevista**
- **¿Cómo actualizás una dependencia con cambios incompatibles?** Una por vez o en grupo chico, con el build y los tests como red, y revisando la app (acá, capturas de cada pantalla) porque los tests no ven todo.

**Etiquetado a ciegas en la UI.** Etiquetar en un CSV era incómodo (Excel en español lo abre todo en una columna) y fácil de sesgar: la pantalla de Ofertas muestra el veredicto del agente. Se agregó `/evals/etiquetar`:
- Una oferta por vez con su descripción, y tres botones (atajos 1/2/3). Guarda al instante y salta a la próxima sin etiquetar.
- **El veredicto del modelo nunca llega al navegador** mientras etiquetás: `para_etiquetar()` arma la respuesta solo con datos de la oferta, y un test verifica que no aparezca. Ocultarlo con CSS no alcanza, porque se vería en las herramientas del navegador.
- El CSV sigue siendo la fuente de verdad (escritura atómica), así que la CLI y la UI son intercambiables. Además, el lector ahora acepta CSV guardados por Excel (BOM y `;`).
- `evals correr` pasó a ser un generador de eventos: la CLI los imprime y la API los manda por SSE, con progreso en vivo. Es el mismo patrón que el agente: un núcleo y dos interfaces.

*Pregunta de entrevista:* "¿Cómo evitás sesgar tus etiquetas?" → Etiquetado a ciegas, muestra estratificada, orden aleatorio, y la información del modelo fuera de la respuesta de la API, no solo fuera de la vista.
