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

- **Residencia mixta (campo `situacion` en criterios).** La candidata vive medio año en Argentina y medio en Europa. Un filtro por país no alcanza para eso: los países pasan por código (Argentina + UE) y el matiz ("exige residencia fija todo el año") lo decide el LLM leyendo `situacion`. Es el mismo patrón de siempre: código para lo binario, LLM para lo ambiguo.
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
