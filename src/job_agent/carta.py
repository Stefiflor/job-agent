"""Fase 5: carta de presentación con RAG + verificación de groundedness.

  1. Retrieval: fragmentos de la base de experiencia más parecidos a la oferta.
  2. Generación: la carta solo puede afirmar lo que está en esos fragmentos, y cita cuáles usó.
  3. Verificación: otro modelo revisa cada afirmación contra los fragmentos.
     Si algo no está respaldado, se reescribe con ese feedback (máximo MAX_INTENTOS).
"""

import re
from dataclasses import dataclass

import numpy as np
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from pydantic import BaseModel, Field

from job_agent import config
from job_agent.embeddings import Embedder
from job_agent.models import Candidata

EXPERIENCIA = config.PRIVADO / "experiencia.md"
DIR_CARTAS = config.PRIVADO / "cartas"
K_FRAGMENTOS = 10
MAX_SIN_RETRIEVAL = 60  # con una base chica, pasar todo es mejor que filtrar
MAX_INTENTOS = 2


# --- Base de experiencia -----------------------------------------------------

@dataclass
class Fragmento:
    id: str
    seccion: str
    texto: str


def fragmentar(markdown: str) -> list[Fragmento]:
    """Un fragmento por bullet, con su sección como contexto."""
    fragmentos, seccion = [], ""
    for linea in markdown.splitlines():
        if linea.startswith("## "):
            seccion = linea[3:].strip()
        elif linea.startswith("- ") and seccion:
            fragmentos.append(Fragmento(f"E{len(fragmentos) + 1}", seccion, linea[2:].strip()))
    return fragmentos


def recuperar(fragmentos: list[Fragmento], consulta: str, embedder: Embedder, k: int = K_FRAGMENTOS) -> list[Fragmento]:
    """Retrieval en memoria: con ~40 fragmentos, pgvector no aporta nada y suma latencia.

    Si la base es chica, se devuelven todos: el filtro por similitud con la oferta dejaba
    afuera los logros más fuertes porque compartían menos palabras con el aviso.
    """
    if not fragmentos:
        return []
    if len(fragmentos) <= MAX_SIN_RETRIEVAL:
        return list(fragmentos)
    m = embedder.encode([f"{f.seccion}: {f.texto}" for f in fragmentos])
    q = embedder.encode([consulta])[0]
    orden = np.argsort(-(m @ q))[:k]
    return [fragmentos[i] for i in sorted(orden)]  # orden original: se lee mejor


def formatear(fragmentos: list[Fragmento]) -> str:
    return "\n".join(f"[{f.id}] ({f.seccion}) {f.texto}" for f in fragmentos)


# --- Modelos de salida ---------------------------------------------------------

class Afirmacion(BaseModel):
    texto: str
    fuentes: list[str] = Field(description="Ids de fragmentos que la respaldan, ej. ['E3']")


class Borrador(BaseModel):
    carta: str
    afirmaciones: list[Afirmacion]


class Problema(BaseModel):
    afirmacion: str
    motivo: str


class Verificacion(BaseModel):
    respaldada: bool
    problemas: list[Problema]


# --- Prompts -------------------------------------------------------------------

PROMPT_REDACTOR = """You write cover letters for a job candidate. Hard rules:
- Every factual claim about the candidate must come from the EXPERIENCE FRAGMENTS. Do not invent metrics, years, employers, titles or technologies.
- List every factual claim in "afirmaciones" with the fragment ids that support it.
- Connect her experience to the 2-3 most important requirements of the posting. Be specific, not generic.
- Lead with professional production work; use personal projects as supporting evidence, not as the main story.
- If a key requirement is missing from her experience, do not pretend; you may mention briefly that she is actively building it only if a fragment says so.
- 180-250 words, plain text, no placeholders, no subject line. {firma}
- Write in {idioma}."""

PROMPT_VERIFICADOR = """You check a cover letter for groundedness. You receive the experience fragments, the letter and its list of claims.
- Read the WHOLE letter, not only the claim list: any factual statement about the candidate counts.
- A claim is supported only if the cited fragments state it. Paraphrase is fine; exaggeration (bigger numbers, "led", "years of") is not.
- Statements about the company or the role, and expressions of interest, are not claims about the candidate.
- respaldada = true only if there are no problems."""


def _prompt_borrador(c: Candidata, frags: list[Fragmento], feedback: list[Problema]) -> str:
    extra = ""
    if feedback:
        extra = "\n\n## Previous draft had unsupported claims — fix them\n" + "\n".join(
            f"- {p.afirmacion}: {p.motivo}" for p in feedback
        )
    return f"""## EXPERIENCE FRAGMENTS
{formatear(frags)}

## JOB POSTING
Title: {c.titulo}
Company: {c.empresa}

{c.descripcion[:6000]}{extra}"""


def _prompt_verificacion(frags: list[Fragmento], b: Borrador) -> str:
    claims = "\n".join(f"- {a.texto} (sources: {', '.join(a.fuentes)})" for a in b.afirmaciones)
    return f"## EXPERIENCE FRAGMENTS\n{formatear(frags)}\n\n## LETTER\n{b.carta}\n\n## CLAIMS\n{claims}"


async def _estructurado(prompt: str, system: str, modelo: type[BaseModel]) -> tuple[BaseModel | None, float]:
    """Una llamada sin herramientas con salida estructurada; consume el stream completo."""
    resultado = None
    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=system,
            tools=[],
            output_format={"type": "json_schema", "schema": modelo.model_json_schema()},
        ),
    ):
        if isinstance(msg, ResultMessage):
            resultado = msg
    if resultado is None or resultado.subtype != "success" or resultado.structured_output is None:
        return None, 0.0
    return modelo.model_validate(resultado.structured_output), resultado.total_cost_usd or 0.0


# --- Orquestación ----------------------------------------------------------------

@dataclass
class ResultadoCarta:
    borrador: Borrador | None
    verificacion: Verificacion | None
    fragmentos: list[Fragmento]
    intentos: int
    costo_usd: float


async def generar(c: Candidata, fragmentos: list[Fragmento], embedder: Embedder, idioma: str = "English", firma: str = "") -> ResultadoCarta:
    firma = f'Sign as "{firma}".' if firma else "End with a sign-off, without a name."
    frags = recuperar(fragmentos, f"{c.titulo}\n{c.descripcion[:3000]}", embedder)
    ids_validos = {f.id for f in frags}
    feedback: list[Problema] = []
    borrador = verificacion = None
    costo = 0.0

    for intento in range(1, MAX_INTENTOS + 1):
        borrador, c1 = await _estructurado(_prompt_borrador(c, frags, feedback), PROMPT_REDACTOR.format(idioma=idioma, firma=firma), Borrador)
        costo += c1
        if borrador is None:
            return ResultadoCarta(None, None, frags, intento, costo)
        # Chequeo determinístico antes de gastar en el verificador: fuentes inexistentes.
        inventadas = [a for a in borrador.afirmaciones if not a.fuentes or set(a.fuentes) - ids_validos]
        if inventadas:
            verificacion = Verificacion(respaldada=False, problemas=[
                Problema(afirmacion=a.texto, motivo="cites no fragment or a fragment id that does not exist")
                for a in inventadas
            ])
        else:
            verificacion, c2 = await _estructurado(_prompt_verificacion(frags, borrador), PROMPT_VERIFICADOR, Verificacion)
            costo += c2
        if verificacion and verificacion.respaldada:
            return ResultadoCarta(borrador, verificacion, frags, intento, costo)
        feedback = verificacion.problemas if verificacion else []

    return ResultadoCarta(borrador, verificacion, frags, MAX_INTENTOS, costo)


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")[:60]


def guardar(c: Candidata, r: ResultadoCarta) -> str:
    DIR_CARTAS.mkdir(parents=True, exist_ok=True)
    ruta = DIR_CARTAS / f"{slug(c.empresa)}--{slug(c.titulo)}.md"
    estado = "verificada" if r.verificacion and r.verificacion.respaldada else "CON PROBLEMAS: revisar antes de enviar"
    partes = [f"# {c.titulo} — {c.empresa}", "", f"{c.link}", "", f"Estado: {estado} · intentos: {r.intentos}", ""]
    if r.borrador:
        partes += ["## Carta", "", r.borrador.carta, "", "## Afirmaciones y fuentes", ""]
        partes += [f"- {a.texto} → {', '.join(a.fuentes)}" for a in r.borrador.afirmaciones]
    if r.verificacion and r.verificacion.problemas:
        partes += ["", "## Problemas detectados", ""] + [f"- {p.afirmacion}: {p.motivo}" for p in r.verificacion.problemas]
    partes += ["", "## Fragmentos recuperados", "", formatear(r.fragmentos)]
    ruta.write_text("\n".join(partes) + "\n", encoding="utf-8")
    return str(ruta.relative_to(config.RAIZ))
