"""Tests de las herramientas del agente sin llamar al modelo ni a la red."""

import asyncio
import json

import pytest

from job_agent import agente
from job_agent.agente import Sesion, crear_herramientas, nombres_herramientas, opciones_agente
from job_agent.models import CandidataEvaluada, Evaluacion
from tests.test_filtros import CRITERIOS, job

EVAL_APLICAR = {
    "encaje": 80, "veredicto": "aplicar", "tipo_puesto": "ingeniería AI/LLM",
    "elegible_ubicacion": "sí", "salario_detectado": "sin dato",
    "cumple": ["agentes"], "falta": [], "red_flags": [], "resumen": "ok",
}


@pytest.fixture
def sesion(tmp_path, monkeypatch):
    s = Sesion(criterios=CRITERIOS, cv="cv", max_evaluaciones=1,
               ruta_evaluadas=tmp_path / "evaluadas.json", ruta_tracker=tmp_path / "tracker.json")

    async def buscar_falso(client, consulta, paginas):
        return [job(guid="a", applicationLink="https://x/a"),
                job(guid="b", applicationLink="https://x/b", locationRestrictions=["Germany"])]

    llamadas = []

    async def evaluar_falso(c, cv, criterios):
        llamadas.append(c.link)
        return CandidataEvaluada(candidata=c, evaluacion=Evaluacion(**EVAL_APLICAR), costo_usd=0.05)

    monkeypatch.setattr(agente.himalayas, "buscar", buscar_falso)
    monkeypatch.setattr(agente, "evaluar", evaluar_falso)
    s.llamadas = llamadas
    return s


def herramienta(s, nombre):
    return next(h for h in crear_herramientas(s) if h.name == nombre).handler


def correr(coro):
    return asyncio.run(coro)


def texto(r):
    return r["content"][0]["text"]


def test_buscar_filtra_y_asigna_ids_cortos(sesion):
    r = texto(correr(herramienta(sesion, "buscar_ofertas")({"consulta": "ai", "paginas": 1})))
    assert "2 resultados, 1 pasan" in r
    assert r.splitlines()[1].startswith("o1 |")


def test_buscar_dos_veces_mantiene_el_mismo_id(sesion):
    buscar = herramienta(sesion, "buscar_ofertas")
    correr(buscar({"consulta": "ai", "paginas": 1}))
    correr(buscar({"consulta": "llm", "paginas": 1}))
    assert list(sesion.ofertas) == ["o1"]


def test_presupuesto_de_evaluaciones(sesion):
    correr(herramienta(sesion, "buscar_ofertas")({"consulta": "ai", "paginas": 1}))
    sesion.ofertas["o2"] = sesion.ofertas["o1"].model_copy(update={"link": "https://x/otra"})
    evaluar = herramienta(sesion, "evaluar_oferta")
    assert "quedan 0" in texto(correr(evaluar({"id": "o1"})))
    r = correr(evaluar({"id": "o2"}))
    assert r.get("is_error") and "Presupuesto agotado" in texto(r)


def test_reevaluar_usa_lo_guardado_sin_gastar(sesion):
    correr(herramienta(sesion, "buscar_ofertas")({"consulta": "ai", "paginas": 1}))
    evaluar = herramienta(sesion, "evaluar_oferta")
    correr(evaluar({"id": "o1"}))
    assert texto(correr(evaluar({"id": "o1"}))).startswith("(guardada)")
    assert len(sesion.llamadas) == 1


def test_tracker_solo_acepta_aplicar_y_no_duplica(sesion):
    correr(herramienta(sesion, "buscar_ofertas")({"consulta": "ai", "paginas": 1}))
    guardar = herramienta(sesion, "guardar_en_tracker")
    assert correr(guardar({"id": "o1", "motivo": "x"})).get("is_error")  # sin evaluar
    correr(herramienta(sesion, "evaluar_oferta")({"id": "o1"}))
    correr(guardar({"id": "o1", "motivo": "x"}))
    assert "Ya estaba" in texto(correr(guardar({"id": "o1", "motivo": "x"})))
    assert len(json.loads(sesion.ruta_tracker.read_text())) == 1


def test_id_inexistente_es_error(sesion):
    assert correr(herramienta(sesion, "ver_oferta")({"id": "o99"})).get("is_error")


def test_opciones_solo_nuestras_herramientas(sesion):
    hs = crear_herramientas(sesion)
    o = opciones_agente(hs, 10)
    assert o.tools == []
    assert set(o.allowed_tools) == set(nombres_herramientas(hs))
    assert all(n.startswith("mcp__jobs__") for n in o.allowed_tools)
