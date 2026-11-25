"""Fase 2: agente con herramientas propias.

Diferencia con `evaluar`: ahí el código decide los pasos (workflow). Acá el modelo
decide qué buscar, qué mirar, qué evaluar y cuándo parar; el código solo ofrece
herramientas y pone límites (presupuesto de evaluaciones, máximo de turnos).
"""

import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import httpx
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)
from pydantic import BaseModel

from job_agent import config
from job_agent.config import Criterios
from job_agent.evaluador import cargar_evaluadas, evaluar, guardar_evaluadas
from job_agent.filtros import clave_oferta, filtrar
from job_agent.models import Candidata, CandidataEvaluada
from job_agent.sources import himalayas

SERVIDOR = "jobs"
MAX_PAGINAS = 3
MAX_CHARS_VER = 3000


# --- Estado de una corrida ---------------------------------------------------

@dataclass
class Sesion:
    """Lo que el agente va acumulando. Las herramientas leen y escriben acá."""

    criterios: Criterios
    cv: str
    max_evaluaciones: int
    ofertas: dict[str, Candidata] = field(default_factory=dict)  # id corto → oferta
    por_link: dict[str, str] = field(default_factory=dict)  # link → id corto
    evaluadas: list[CandidataEvaluada] = field(default_factory=list)
    evaluaciones_hechas: int = 0
    costo_usd: float = 0.0
    ruta_evaluadas: Path = config.EVALUADAS
    ruta_tracker: Path = config.PRIVADO / "tracker.json"
    _indice: Any = None  # (conexión, embedder), se abre la primera vez que se usa

    def indice(self):
        if self._indice is None:
            from job_agent import vectores
            from job_agent.embeddings import Model2VecEmbedder

            self._indice = (vectores.conectar(), Model2VecEmbedder())
        return self._indice

    def registrar(self, c: Candidata) -> str:
        """IDs cortos (o1, o2...) para que el modelo no tenga que repetir URLs largas."""
        if c.link not in self.por_link:
            oid = f"o{len(self.por_link) + 1}"
            self.por_link[c.link] = oid
            self.ofertas[oid] = c
        return self.por_link[c.link]

    def evaluacion_previa(self, c: Candidata) -> CandidataEvaluada | None:
        k = clave_oferta(c.titulo, c.empresa)  # la misma oferta puede venir con otro link
        return next((e for e in self.evaluadas
                     if e.candidata.link == c.link or clave_oferta(e.candidata.titulo, e.candidata.empresa) == k), None)


def _texto(t: str, error: bool = False) -> dict[str, Any]:
    r: dict[str, Any] = {"content": [{"type": "text", "text": t}]}
    if error:
        r["is_error"] = True
    return r


def _salario(c: Candidata) -> str:
    if not c.salario_usd_mes:
        return "sin salario"
    return f"${c.salario_usd_mes.min}-{c.salario_usd_mes.max}/mes" + (" (por hora)" if c.por_hora else "")


# --- Herramientas ------------------------------------------------------------

def crear_herramientas(s: Sesion) -> list:
    """Las herramientas son closures sobre la sesión: así se testean sin el modelo."""

    @tool(
        "buscar_ofertas",
        "Busca ofertas remotas en Himalayas por palabra clave y aplica los filtros de la "
        "candidata (zona horaria, país, salario mínimo, seniority). Devuelve una lista corta "
        "con id, título, empresa, salario y países. No incluye la descripción.",
        {
            "consulta": Annotated[str, "Palabras clave, en inglés. Ej: 'LLM engineer', 'AI agents'"],
            "paginas": Annotated[int, f"Páginas de 20 resultados, 1 a {MAX_PAGINAS}"],
        },
    )
    async def buscar_ofertas(args: dict) -> dict:
        paginas = max(1, min(int(args.get("paginas", 1)), MAX_PAGINAS))
        async with httpx.AsyncClient(timeout=30) as client:
            jobs = await himalayas.buscar(client, args["consulta"], paginas)
        candidatas, descartes = filtrar(jobs, s.criterios, ahora=time.time())
        lineas = []
        for c in candidatas:
            oid = s.registrar(c)
            previa = s.evaluacion_previa(c)
            ya = f" | YA EVALUADA: {previa.evaluacion.veredicto} {previa.evaluacion.encaje}" if previa else ""
            paises = ", ".join(c.paises_validos[:3]) + ("..." if len(c.paises_validos) > 3 else "")
            lineas.append(f"{oid} | {c.titulo} | {c.empresa} | {_salario(c)} | {paises}{ya}")
        cabecera = f"{len(jobs)} resultados, {len(candidatas)} pasan los filtros. Descartes: {descartes}"
        return _texto(cabecera + "\n" + "\n".join(lineas))

    @tool(
        "ver_oferta",
        "Muestra la descripción de una oferta (recortada). Usala para decidir si vale la pena "
        "evaluarla: es mucho más barata que evaluar_oferta.",
        {"id": Annotated[str, "Id corto de la oferta, ej. 'o3'"]},
    )
    async def ver_oferta(args: dict) -> dict:
        c = s.ofertas.get(args["id"])
        if c is None:
            return _texto(f"No existe la oferta {args['id']}. Usá un id de buscar_ofertas.", error=True)
        return _texto(
            f"{c.titulo} — {c.empresa}\nTipo: {c.tipo} | Seniority: {', '.join(c.seniority)} | "
            f"Salario: {c.salario_original}\n\n{c.descripcion[:MAX_CHARS_VER]}"
        )

    @tool(
        "evaluar_oferta",
        "Evalúa en profundidad el encaje de una oferta con el CV de la candidata (otro modelo, "
        "salida estructurada). Es cara y tiene presupuesto limitado: evaluá solo ofertas "
        "prometedoras. Si ya fue evaluada antes, devuelve el resultado guardado sin gastar presupuesto.",
        {"id": Annotated[str, "Id corto de la oferta, ej. 'o3'"]},
    )
    async def evaluar_oferta(args: dict) -> dict:
        c = s.ofertas.get(args["id"])
        if c is None:
            return _texto(f"No existe la oferta {args['id']}.", error=True)
        previa = s.evaluacion_previa(c)
        if previa:
            return _texto("(guardada) " + previa.evaluacion.model_dump_json())
        if s.evaluaciones_hechas >= s.max_evaluaciones:
            return _texto(
                f"Presupuesto agotado ({s.max_evaluaciones} evaluaciones). "
                "Terminá con lo que ya tenés.",
                error=True,
            )
        s.evaluaciones_hechas += 1
        r = await evaluar(c, s.cv, s.criterios)
        if r is None:
            return _texto("La evaluación falló. Probá con otra oferta.", error=True)
        s.costo_usd += r.costo_usd or 0
        s.evaluadas.append(r)
        guardar_evaluadas(s.ruta_evaluadas, s.evaluadas)
        restantes = s.max_evaluaciones - s.evaluaciones_hechas
        return _texto(f"{r.evaluacion.model_dump_json()}\n(quedan {restantes} evaluaciones)")

    @tool(
        "guardar_en_tracker",
        "Guarda una oferta en el tracker de postulaciones de la candidata. Usalo solo para "
        "ofertas evaluadas con veredicto 'aplicar'.",
        {
            "id": Annotated[str, "Id corto de la oferta"],
            "motivo": Annotated[str, "Una oración: por qué vale la pena y qué confirmar al aplicar"],
        },
    )
    async def guardar_en_tracker(args: dict) -> dict:
        c = s.ofertas.get(args["id"])
        if c is None:
            return _texto(f"No existe la oferta {args['id']}.", error=True)
        previa = s.evaluacion_previa(c)
        if previa is None or previa.evaluacion.veredicto != "aplicar":
            return _texto("Solo se guardan ofertas evaluadas con veredicto 'aplicar'.", error=True)
        tracker = json.loads(s.ruta_tracker.read_text(encoding="utf-8")) if s.ruta_tracker.exists() else []
        if any(t["link"] == c.link for t in tracker):
            return _texto("Ya estaba en el tracker.")
        tracker.append({
            "fecha": date.today().isoformat(),
            "estado": "para aplicar",
            "titulo": c.titulo,
            "empresa": c.empresa,
            "encaje": previa.evaluacion.encaje,
            "link": c.link,
            "motivo": args["motivo"],
        })
        s.ruta_tracker.write_text(json.dumps(tracker, ensure_ascii=False, indent=2), encoding="utf-8")
        return _texto(f"Guardada en el tracker ({len(tracker)} en total).")

    @tool(
        "buscar_semantico",
        "Búsqueda por significado en el índice local de ofertas (pgvector), en lenguaje natural. "
        "Encuentra ofertas que una búsqueda por palabra clave no ve (ej. 'construir agentes que "
        "llamen APIs para atención al cliente'). Solo devuelve ofertas que pasan los filtros.",
        {
            "consulta": Annotated[str, "Descripción en lenguaje natural del trabajo buscado"],
            "k": Annotated[int, "Cantidad de resultados, 1 a 20"],
        },
    )
    async def buscar_semantico(args: dict) -> dict:
        from job_agent import vectores

        try:
            conn, emb = s.indice()
            resultados = vectores.buscar(conn, emb, args["consulta"], max(1, min(int(args.get("k", 10)), 20)))
        except Exception as e:  # sin Docker o sin índice: el agente sigue con buscar_ofertas
            return _texto(f"Índice semántico no disponible ({type(e).__name__}). Usá buscar_ofertas.", error=True)
        lineas = []
        for r in resultados:
            if r.candidata is None:
                continue
            oid = s.registrar(r.candidata)
            previa = s.evaluacion_previa(r.candidata)
            ya = f" | YA EVALUADA: {previa.evaluacion.veredicto} {previa.evaluacion.encaje}" if previa else ""
            lineas.append(f"{oid} | sim {r.similitud:.2f} | {r.titulo} | {r.empresa} | {_salario(r.candidata)}{ya}")
        return _texto(f"{len(lineas)} resultados por similitud:\n" + "\n".join(lineas))

    return [buscar_ofertas, buscar_semantico, ver_oferta, evaluar_oferta, guardar_en_tracker]


# --- Agente ------------------------------------------------------------------

class ItemRanking(BaseModel):
    id: str
    titulo: str
    empresa: str
    encaje: int
    por_que: str


class Informe(BaseModel):
    ranking: list[ItemRanking]
    resumen_busqueda: str


SYSTEM_PROMPT = """Sos un agente que busca trabajo remoto para una candidata. Tenés herramientas para buscar ofertas, leerlas, evaluarlas y guardarlas en su tracker.

Estrategia:
- Combiná buscar_ofertas (palabra clave, datos frescos de la API) con buscar_semantico (por significado, sobre el índice local). Si el índice no está disponible, seguí solo con palabra clave.
- Buscá con varias consultas distintas (sinónimos, roles cercanos). Las ofertas repetidas reciben el mismo id.
- Antes de evaluar, descartá por título o con ver_oferta lo que claramente no encaja (ventas, management, research de ML puro, idiomas que no habla). evaluar_oferta es cara y tiene presupuesto.
- Las marcadas "YA EVALUADA" no gastan presupuesto: tenelas en cuenta.
- Desconfiá de agregadores que republican ofertas de otras empresas.
- Guardá en el tracker solo las de veredicto "aplicar".
- Pará cuando tengas el objetivo cumplido o se acabe el presupuesto. No sigas buscando por buscar.

Al final devolvé el ranking de las mejores ofertas evaluadas (de mayor a menor encaje) y un resumen de la búsqueda: qué consultas usaste y qué patrón viste. En español."""


def nombres_herramientas(herramientas: list) -> list[str]:
    return [f"mcp__{SERVIDOR}__{h.name}" for h in herramientas]


async def _log_herramienta(input_data, tool_use_id, context):
    """Hook PostToolUse: deja traza de cada llamada (observabilidad)."""
    ruta = config.PRIVADO / "logs" / f"agente-{date.today().isoformat()}.jsonl"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = dict(input_data) if not isinstance(input_data, dict) else input_data
    registro = {
        "ts": time.time(),
        "herramienta": datos.get("tool_name"),
        "input": datos.get("tool_input"),
        "duracion_ms": datos.get("duration_ms"),
    }
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return {}


def opciones_agente(herramientas: list, max_turnos: int) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=config.MODELO_AGENTE,
        tools=[],  # sin herramientas de Claude Code (Bash, Read...): solo las nuestras
        mcp_servers={SERVIDOR: create_sdk_mcp_server(SERVIDOR, tools=herramientas)},
        allowed_tools=nombres_herramientas(herramientas),
        max_turns=max_turnos,
        output_format={"type": "json_schema", "schema": Informe.model_json_schema()},
        hooks={"PostToolUse": [HookMatcher(matcher=f"mcp__{SERVIDOR}__.*", hooks=[_log_herramienta])]},
    )


async def eventos(pedido: str, objetivo: int, max_evaluaciones: int, max_turnos: int = 40):
    """Corre el agente y emite eventos (dicts). Lo consumen la CLI y la API (SSE)."""
    s = Sesion(
        criterios=config.cargar_criterios(),
        cv=config.CV.read_text(encoding="utf-8"),
        max_evaluaciones=max_evaluaciones,
        evaluadas=cargar_evaluadas(config.EVALUADAS),
    )
    herramientas = crear_herramientas(s)
    prompt = (
        f"{pedido}\n\nObjetivo: encontrar {objetivo} ofertas con veredicto 'aplicar'. "
        f"Presupuesto: {max_evaluaciones} evaluaciones nuevas."
    )

    resultado: ResultMessage | None = None
    async for msg in query(prompt=prompt, options=opciones_agente(herramientas, max_turnos)):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, ToolUseBlock):
                    nombre = b.name.removeprefix(f"mcp__{SERVIDOR}__")
                    if nombre != "StructuredOutput":
                        yield {"tipo": "herramienta", "nombre": nombre, "input": b.input}
                elif isinstance(b, TextBlock) and b.text.strip():
                    yield {"tipo": "pensamiento", "texto": b.text.strip()[:500]}
        elif isinstance(msg, ResultMessage):
            resultado = msg

    if resultado is None or resultado.structured_output is None:
        yield {"tipo": "error", "texto": f"El agente no devolvió informe ({resultado.subtype if resultado else 'sin resultado'})."}
    else:
        informe = Informe.model_validate(resultado.structured_output)
        yield {
            "tipo": "informe",
            "ranking": [
                it.model_dump() | {"link": s.ofertas[it.id].link if it.id in s.ofertas else None}
                for it in informe.ranking
            ],
            "resumen": informe.resumen_busqueda,
        }
    yield {
        "tipo": "fin",
        "turnos": resultado.num_turns if resultado else 0,
        "evaluaciones_nuevas": s.evaluaciones_hechas,
        "max_evaluaciones": max_evaluaciones,
        "costo_agente_usd": (resultado.total_cost_usd or 0) if resultado else 0,
        "costo_evaluaciones_usd": s.costo_usd,
    }


async def correr(pedido: str, objetivo: int, max_evaluaciones: int, max_turnos: int = 40) -> None:
    """Versión CLI: imprime los eventos."""
    async for e in eventos(pedido, objetivo, max_evaluaciones, max_turnos):
        if e["tipo"] == "herramienta":
            print(f"  🔧 {e['nombre']}({json.dumps(e['input'], ensure_ascii=False)})")
        elif e["tipo"] == "pensamiento":
            print(f"  💭 {e['texto'][:300]}")
        elif e["tipo"] == "error":
            print(f"\n⚠ {e['texto']}")
        elif e["tipo"] == "informe":
            print("\nRANKING")
            for i, it in enumerate(e["ranking"], 1):
                print(f"{i}. {it['encaje']} | {it['titulo']} | {it['empresa']}\n   {it['por_que']}\n   {it['link'] or ''}")
            print(f"\n{e['resumen']}")
        elif e["tipo"] == "fin":
            print(
                f"\nTurnos: {e['turnos']} · evaluaciones nuevas: {e['evaluaciones_nuevas']}/{e['max_evaluaciones']} · "
                f"costo estimado: agente ${e['costo_agente_usd']:.3f} + evaluaciones ${e['costo_evaluaciones_usd']:.3f}"
            )
