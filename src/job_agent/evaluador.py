"""Evaluación de cada candidata con Claude (Agent SDK) y salida estructurada."""

import json

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from pydantic import ValidationError

from job_agent import config
from job_agent.config import Criterios
from job_agent.filtros import aplicar_reglas, clave_oferta
from job_agent.models import Candidata, CandidataEvaluada, Evaluacion

MAX_CHARS_DESC = 8000  # recorta descripciones largas para no gastar cupo de más

SYSTEM_PROMPT = """Sos un asesor de carrera técnico y exigente. Evaluás si una oferta remota encaja con el CV y los criterios de una candidata.
Reglas:
- Usá solo el CV, los criterios y la oferta. No inventes requisitos ni datos.
- Sé estricto: 80+ solo si cumple la mayoría de los requisitos excluyentes.
- Su inglés es B2: marcá como red flag si la oferta exige inglés nativo o C2.
- Si es trabajo de entrenamiento/evaluación de modelos (anotación, RLHF, "AI tutor") y no un puesto de ingeniería, clasificalo como "entrenamiento de IA / gig".
- Leé "situacion" en los criterios: describe dónde vive la candidata y qué modalidad acepta. Aplicalo al decidir elegible_ubicacion.
- Los países permitidos de la API no siempre son confiables: si el texto restringe la ubicación, eso manda.
- Si el salario no está en los datos estructurados pero aparece en el texto, extraelo en salario_detectado; si no hay, poné "sin dato".
- "resumen": 1-2 oraciones. Todo en español."""


def construir_prompt(c: Candidata, cv: str, criterios: Criterios) -> str:
    aviso_hora = " (por hora: verificá horas semanales en el texto)" if c.por_hora else ""
    return f"""## CV
{cv}

## Criterios
{criterios.model_dump_json(by_alias=True, indent=2)}

## Oferta
Título: {c.titulo}
Empresa: {c.empresa}
Tipo: {c.tipo}
Seniority: {", ".join(c.seniority)}
Salario (datos estructurados): {c.salario_original}{aviso_hora}
Países permitidos que coinciden con la candidata: {", ".join(c.paises_validos)}

Descripción:
{c.descripcion[:MAX_CHARS_DESC]}"""


def opciones() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=config.MODELO_EVALUADOR,
        tools=[],  # sin herramientas: todo lo necesario va en el prompt
        output_format={"type": "json_schema", "schema": Evaluacion.model_json_schema()},
    )


async def evaluar(c: Candidata, cv: str, criterios: Criterios) -> CandidataEvaluada | None:
    """Una llamada por oferta: si una falla, no arrastra a las demás."""
    # Se consume el stream completo antes de procesar: cortarlo con return a mitad
    # deja el generador async abierto y Python 3.14 tira "aclose(): asynchronous
    # generator is already running" al cerrarlo.
    resultado: ResultMessage | None = None
    async for msg in query(prompt=construir_prompt(c, cv, criterios), options=opciones()):
        if isinstance(msg, ResultMessage):
            resultado = msg

    if resultado is None or resultado.subtype != "success" or resultado.structured_output is None:
        print(f"  ⚠ falló: {resultado.subtype if resultado else 'sin resultado'}")
        return None
    try:
        evaluacion = aplicar_reglas(Evaluacion.model_validate(resultado.structured_output))
    except ValidationError as e:  # el SDK valida el schema, pero no confiamos a ciegas
        print(f"  ⚠ salida inválida: {e.error_count()} errores")
        return None
    return CandidataEvaluada(
        candidata=c,
        evaluacion=evaluacion,
        costo_usd=resultado.total_cost_usd,
        duracion_ms=resultado.duration_ms,
        modelo=config.MODELO_EVALUADOR,
    )


def sin_evaluar(candidatas: list[Candidata], evaluadas: list[CandidataEvaluada]) -> list[Candidata]:
    """Candidatas que todavía no se evaluaron, ni con el mismo link ni como duplicado (empresa + título)."""
    ya = {e.candidata.link for e in evaluadas} | {clave_oferta(e.candidata.titulo, e.candidata.empresa) for e in evaluadas}
    return [c for c in candidatas if c.link not in ya and clave_oferta(c.titulo, c.empresa) not in ya]


def actualizar_vencimientos(evaluadas: list[CandidataEvaluada], candidatas: list[Candidata]) -> int:
    """Copia la fecha de vencimiento de una búsqueda nueva a las evaluaciones guardadas (mismo link).
    Así las evaluadas antes de que se guardara el vencimiento también se pueden ocultar al vencer."""
    vence = {c.link: c.vence for c in candidatas if c.vence}
    n = 0
    for i, e in enumerate(evaluadas):
        v = vence.get(e.candidata.link)
        if v and v != e.candidata.vence:
            evaluadas[i] = e.model_copy(update={"candidata": e.candidata.model_copy(update={"vence": v})})
            n += 1
    return n


def cargar_evaluadas(ruta) -> list[CandidataEvaluada]:
    if not ruta.exists():
        return []
    evaluadas = [CandidataEvaluada.model_validate(x) for x in json.loads(ruta.read_text(encoding="utf-8"))]
    # Las reglas se aplican también al leer: corrigen evaluaciones guardadas antes de que existieran.
    return [e.model_copy(update={"evaluacion": aplicar_reglas(e.evaluacion)}) for e in evaluadas]


def guardar_evaluadas(ruta, evaluadas: list[CandidataEvaluada]) -> None:
    evaluadas = sorted(evaluadas, key=lambda e: e.evaluacion.encaje, reverse=True)
    ruta.write_text(
        json.dumps([e.model_dump(mode="json") for e in evaluadas], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
