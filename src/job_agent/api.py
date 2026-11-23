"""Fase 6: API HTTP (FastAPI) sobre el mismo núcleo que la CLI.

Uso local:  uv run job-agent api   →  http://127.0.0.1:8000  (docs en /docs)

No tiene autenticación: está pensada para correr en tu máquina. Cada llamada a un
endpoint con LLM gasta cupo o dinero, así que no se expone a internet sin agregar auth.
"""

import asyncio
import hashlib
import json
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import AsyncIterator, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from job_agent import agente, carta, config, evals
from job_agent.evaluador import cargar_evaluadas, evaluar, guardar_evaluadas
from job_agent.filtros import filtrar
from job_agent.models import Candidata, CandidataEvaluada
from job_agent.sources.himalayas import buscar_roles

TRACKER = config.PRIVADO / "tracker.json"
ULTIMA_EJECUCION = config.PRIVADO / "ultima_ejecucion.json"
WEB_DIST = config.RAIZ / "web" / "dist"
ESTADOS = ["para aplicar", "aplicada", "entrevista", "oferta", "descartada"]
Estado = Literal["para aplicar", "aplicada", "entrevista", "oferta", "descartada"]

app = FastAPI(title="job-agent", version="0.1.0")
_lock_archivos = asyncio.Lock()  # un solo usuario, pero la UI puede disparar escrituras en paralelo


# --- Helpers -------------------------------------------------------------------

def oferta_id(link: str) -> str:
    """Id estable y corto derivado del link (sin query string)."""
    return hashlib.sha1(link.split("?")[0].encode()).hexdigest()[:10]


def _leer_json(ruta: Path, default):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else default


def _escribir_json(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ruta)  # escritura atómica: nunca queda un JSON a medio escribir


def _evaluadas() -> list[CandidataEvaluada]:
    return cargar_evaluadas(config.EVALUADAS)


def _buscar_por_id(oid: str) -> tuple[Candidata, CandidataEvaluada | None]:
    for e in _evaluadas():
        if oferta_id(e.candidata.link) == oid:
            return e.candidata, e
    for c in _leer_json(config.CANDIDATAS, []):
        if oferta_id(c["link"]) == oid:
            return Candidata.model_validate(c), None
    raise HTTPException(404, "Oferta no encontrada")


def _resumen_oferta(e: CandidataEvaluada) -> dict:
    c, ev = e.candidata, e.evaluacion
    return {
        "id": oferta_id(c.link),
        "titulo": c.titulo,
        "empresa": c.empresa,
        "link": c.link,
        "salario": c.salario_usd_mes.model_dump() if c.salario_usd_mes else None,
        "por_hora": c.por_hora,
        "paises": c.paises_validos,
        "publicada": c.publicada,
        "encaje": ev.encaje,
        "veredicto": ev.veredicto,
        "tipo_puesto": ev.tipo_puesto,
        "elegible_ubicacion": ev.elegible_ubicacion,
        "resumen": ev.resumen,
        "red_flags": ev.red_flags,
    }


async def _sse(eventos: AsyncIterator[dict]) -> AsyncIterator[str]:
    """Server-Sent Events: una línea `data:` por evento. Los errores también viajan como evento."""
    try:
        async for e in eventos:
            yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
    except Exception as ex:  # noqa: BLE001 — se informa al cliente en vez de cortar el stream en silencio
        yield f"data: {json.dumps({'tipo': 'error', 'texto': f'{type(ex).__name__}: {ex}'})}\n\n"


def _stream(eventos: AsyncIterator[dict]) -> StreamingResponse:
    return StreamingResponse(_sse(eventos), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- Estado y ofertas ------------------------------------------------------------

@app.get("/api/salud")
def salud() -> dict:
    return {"ok": True, "cv": config.CV.exists(), "criterios": config.CRITERIOS.exists(),
            "experiencia": carta.EXPERIENCIA.exists()}


@app.get("/api/resumen")
def resumen() -> dict:
    ev = _evaluadas()
    tracker = _leer_json(TRACKER, [])
    return {
        "candidatas": len(_leer_json(config.CANDIDATAS, [])),
        "evaluadas": len(ev),
        "por_veredicto": dict(Counter(e.evaluacion.veredicto for e in ev)),
        "costo_evaluaciones_usd": round(sum(e.costo_usd or 0 for e in ev), 3),
        "tracker": {estado: sum(t.get("estado") == estado for t in tracker) for estado in ESTADOS},
    }


@app.get("/api/ofertas")
def ofertas(
    veredicto: Literal["aplicar", "dudoso", "descartar"] | None = None,
    min_encaje: int = Query(0, ge=0, le=100),
    q: str | None = None,
) -> list[dict]:
    res = [_resumen_oferta(e) for e in _evaluadas()]
    if veredicto:
        res = [r for r in res if r["veredicto"] == veredicto]
    if q:
        ql = q.lower()
        res = [r for r in res if ql in r["titulo"].lower() or ql in r["empresa"].lower()]
    return [r for r in res if r["encaje"] >= min_encaje]


@app.get("/api/ofertas/{oid}")
def oferta(oid: str) -> dict:
    c, e = _buscar_por_id(oid)
    carta_md = carta.DIR_CARTAS / f"{carta.slug(c.empresa)}--{carta.slug(c.titulo)}.md"
    return {
        "id": oid,
        "candidata": c.model_dump(mode="json"),
        "evaluacion": e.evaluacion.model_dump() if e else None,
        "en_tracker": any(oferta_id(t["link"]) == oid for t in _leer_json(TRACKER, [])),
        "carta_md": carta_md.read_text(encoding="utf-8") if carta_md.exists() else None,
    }


# --- Acciones largas: streaming ----------------------------------------------------

@app.post("/api/buscar")
async def api_buscar(paginas: int = Query(2, ge=1, le=5)) -> dict:
    criterios = config.cargar_criterios()
    jobs = await buscar_roles(criterios.roles, paginas)
    candidatas, descartes = filtrar(jobs, criterios, ahora=time.time())
    async with _lock_archivos:
        _escribir_json(config.CANDIDATAS, [c.model_dump(mode="json") for c in candidatas])
    return {"encontradas": len(jobs), "candidatas": len(candidatas), "descartes": descartes}


async def _eventos_evaluar(limite: int) -> AsyncIterator[dict]:
    criterios = config.cargar_criterios()
    cv = config.CV.read_text(encoding="utf-8")
    candidatas = [Candidata.model_validate(x) for x in _leer_json(config.CANDIDATAS, [])]
    evaluadas = _evaluadas()
    ya = {e.candidata.link for e in evaluadas}
    pendientes = [c for c in candidatas if c.link not in ya][:limite]
    yield {"tipo": "inicio", "pendientes": len(pendientes), "ya_evaluadas": len(ya)}
    costo = 0.0
    for i, c in enumerate(pendientes, 1):
        r = await evaluar(c, cv, criterios)
        if r is None:
            yield {"tipo": "fallo", "n": i, "titulo": c.titulo}
            continue
        evaluadas.append(r)
        async with _lock_archivos:
            guardar_evaluadas(config.EVALUADAS, evaluadas)
        costo += r.costo_usd or 0
        yield {"tipo": "evaluada", "n": i, "total": len(pendientes), "oferta": _resumen_oferta(r)}
    yield {"tipo": "fin", "costo_usd": round(costo, 3)}


@app.get("/api/evaluar/stream")
def api_evaluar(limite: int = Query(5, ge=1, le=60)) -> StreamingResponse:
    return _stream(_eventos_evaluar(limite))


async def _eventos_agente(pedido: str, objetivo: int, max_evaluaciones: int) -> AsyncIterator[dict]:
    """Reenvía los eventos del agente y guarda un resumen de la corrida para la pantalla de inicio."""
    analizadas = 0
    async for e in agente.eventos(pedido, objetivo, max_evaluaciones):
        if e["tipo"] == "herramienta" and e["nombre"] in ("ver_oferta", "evaluar_oferta"):
            analizadas += 1
        if e["tipo"] == "fin":
            async with _lock_archivos:
                _escribir_json(ULTIMA_EJECUCION, {
                    "fecha": date.today().isoformat(), "pedido": pedido, "ofertas_analizadas": analizadas,
                    "evaluaciones": e["evaluaciones_nuevas"],
                    "costo_usd": round(e["costo_agente_usd"] + e["costo_evaluaciones_usd"], 3),
                })
        yield e


@app.get("/api/agente/stream")
def api_agente(
    pedido: str = "Buscame trabajos remotos de AI Engineer o full stack con IA.",
    objetivo: int = Query(3, ge=1, le=10),
    max_evaluaciones: int = Query(5, ge=0, le=20),
) -> StreamingResponse:
    return _stream(_eventos_agente(pedido, objetivo, max_evaluaciones))


@app.get("/api/agente/ultima")
def agente_ultima() -> dict | None:
    return _leer_json(ULTIMA_EJECUCION, None)


# --- Cartas --------------------------------------------------------------------

class PedidoCarta(BaseModel):
    idioma: Literal["English", "Spanish"] = "English"


@app.post("/api/ofertas/{oid}/carta")
async def api_carta(oid: str, pedido: PedidoCarta) -> dict:
    from job_agent.embeddings import Model2VecEmbedder

    c, _ = _buscar_por_id(oid)
    if not carta.EXPERIENCIA.exists():
        raise HTTPException(409, "Falta private/experiencia.md")
    frags = carta.fragmentar(carta.EXPERIENCIA.read_text(encoding="utf-8"))
    r = await carta.generar(c, frags, Model2VecEmbedder(), pedido.idioma)
    carta.guardar(c, r)
    return {
        "verificada": bool(r.verificacion and r.verificacion.respaldada),
        "intentos": r.intentos,
        "costo_usd": round(r.costo_usd, 3),
        "carta": r.borrador.carta if r.borrador else None,
        "afirmaciones": [a.model_dump() for a in r.borrador.afirmaciones] if r.borrador else [],
        "problemas": [p.model_dump() for p in r.verificacion.problemas] if r.verificacion else [],
    }


# --- Tracker -------------------------------------------------------------------

class AltaTracker(BaseModel):
    id: str
    motivo: str = ""


class CambioTracker(BaseModel):
    estado: Estado | None = None
    notas: str | None = None


@app.get("/api/tracker")
def tracker() -> list[dict]:
    return [t | {"id": oferta_id(t["link"])} for t in _leer_json(TRACKER, [])]


@app.post("/api/tracker", status_code=201)
async def tracker_alta(alta: AltaTracker) -> dict:
    c, e = _buscar_por_id(alta.id)
    async with _lock_archivos:
        items = _leer_json(TRACKER, [])
        if any(oferta_id(t["link"]) == alta.id for t in items):
            raise HTTPException(409, "Ya está en el tracker")
        hoy = date.today().isoformat()
        item = {"fecha": hoy, "estado": "para aplicar", "titulo": c.titulo,
                "empresa": c.empresa, "encaje": e.evaluacion.encaje if e else None,
                "link": c.link, "motivo": alta.motivo, "notas": "",
                "historial": [{"estado": "para aplicar", "fecha": hoy}]}
        items.append(item)
        _escribir_json(TRACKER, items)
    return item | {"id": alta.id}


@app.patch("/api/tracker/{oid}")
async def tracker_cambio(oid: str, cambio: CambioTracker) -> dict:
    async with _lock_archivos:
        items = _leer_json(TRACKER, [])
        for t in items:
            if oferta_id(t["link"]) == oid:
                if cambio.estado and cambio.estado != t.get("estado"):
                    t["estado"] = cambio.estado
                    # El historial alimenta el seguimiento de la UI (cuándo pasó a cada etapa).
                    t.setdefault("historial", [{"estado": "para aplicar", "fecha": t["fecha"]}])
                    t["historial"].append({"estado": cambio.estado, "fecha": date.today().isoformat()})
                if cambio.notas is not None:
                    t["notas"] = cambio.notas
                _escribir_json(TRACKER, items)
                return t | {"id": oid}
    raise HTTPException(404, "No está en el tracker")


# --- RAG y evals ------------------------------------------------------------------

@app.get("/api/rag/buscar")
def rag_buscar(q: str, k: int = Query(10, ge=1, le=50), todas: bool = False) -> list[dict]:
    from job_agent import vectores
    from job_agent.embeddings import Model2VecEmbedder

    try:
        with vectores.conectar() as conn:
            res = vectores.buscar(conn, Model2VecEmbedder(), q, k, solo_filtradas=not todas)
    except Exception as ex:  # noqa: BLE001
        raise HTTPException(503, f"Índice semántico no disponible ({type(ex).__name__}). ¿Docker apagado?") from ex
    return [{"id": oferta_id(r.link), "titulo": r.titulo, "empresa": r.empresa, "link": r.link,
             "similitud": round(r.similitud, 3), "pasa_filtros": r.pasa_filtros, "motivo": r.motivo}
            for r in res]


@app.get("/api/evals")
def ultimo_eval() -> dict | None:
    resultados = sorted(evals.DIR_EVALS.glob("resultado-*.json")) if evals.DIR_EVALS.exists() else []
    if not resultados:
        return None
    d = json.loads(resultados[-1].read_text(encoding="utf-8"))
    return {"archivo": resultados[-1].name, "metricas": d["metricas"],
            "repeticiones": d["repeticiones"], "costo_usd": d.get("costo_usd")}


# --- Frontend compilado (Fase 7) ------------------------------------------------------

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):  # cualquier ruta que no sea /api devuelve la app de Vue
        if ruta.startswith("api/"):
            raise HTTPException(404, "Endpoint inexistente")
        return FileResponse(WEB_DIST / "index.html")
