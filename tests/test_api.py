"""Tests de la API con TestClient: archivos en un directorio temporal, sin modelo ni red."""

import json

import pytest
from fastapi.testclient import TestClient

from job_agent import api, config
from job_agent.models import CandidataEvaluada, Evaluacion
from tests.test_agente import EVAL_APLICAR
from tests.test_filtros import CRITERIOS, job
from job_agent.filtros import a_candidata_desde_job


def evaluada(link, veredicto="aplicar", encaje=80):
    c = a_candidata_desde_job(job(applicationLink=link, title=f"Rol {link[-1]}"), CRITERIOS)
    return CandidataEvaluada(candidata=c, evaluacion=Evaluacion(**(EVAL_APLICAR | {"veredicto": veredicto, "encaje": encaje})), costo_usd=0.05)


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EVALUADAS", tmp_path / "evaluadas.json")
    monkeypatch.setattr(config, "CANDIDATAS", tmp_path / "candidatas.json")
    monkeypatch.setattr(api, "TRACKER", tmp_path / "tracker.json")
    monkeypatch.setattr(api, "ULTIMA_EJECUCION", tmp_path / "ultima.json")
    evs = [evaluada("https://x/a"), evaluada("https://x/b", "descartar", 20)]
    config.EVALUADAS.write_text(json.dumps([e.model_dump(mode="json") for e in evs]))
    return TestClient(api.app)


def test_resumen(cliente):
    r = cliente.get("/api/resumen").json()
    assert r["evaluadas"] == 2 and r["por_veredicto"] == {"aplicar": 1, "descartar": 1}
    assert r["costo_evaluaciones_usd"] == 0.1


def test_ofertas_filtra(cliente):
    assert len(cliente.get("/api/ofertas").json()) == 2
    solo = cliente.get("/api/ofertas", params={"veredicto": "aplicar"}).json()
    assert [o["link"] for o in solo] == ["https://x/a"]
    assert cliente.get("/api/ofertas", params={"min_encaje": 50}).json()[0]["encaje"] == 80


def test_id_estable_ignora_query_string():
    assert api.oferta_id("https://x/a?utm=1") == api.oferta_id("https://x/a")


def test_detalle_y_404(cliente):
    oid = api.oferta_id("https://x/a")
    d = cliente.get(f"/api/ofertas/{oid}").json()
    assert d["evaluacion"]["veredicto"] == "aplicar" and d["en_tracker"] is False
    assert cliente.get("/api/ofertas/noexiste").status_code == 404


def test_tracker_alta_duplicado_y_cambio(cliente):
    oid = api.oferta_id("https://x/a")
    assert cliente.post("/api/tracker", json={"id": oid}).status_code == 201
    assert cliente.post("/api/tracker", json={"id": oid}).status_code == 409
    r = cliente.patch(f"/api/tracker/{oid}", json={"estado": "aplicada", "notas": "mandé CV"}).json()
    assert r["estado"] == "aplicada" and r["notas"] == "mandé CV"
    assert cliente.patch(f"/api/tracker/{oid}", json={"estado": "inventado"}).status_code == 422
    assert cliente.get("/api/resumen").json()["tracker"]["aplicada"] == 1


def test_evaluar_stream(cliente, monkeypatch):
    c = a_candidata_desde_job(job(applicationLink="https://x/c"), CRITERIOS)
    config.CANDIDATAS.write_text(json.dumps([c.model_dump(mode="json")]))
    monkeypatch.setattr(config, "CV", config.CANDIDATAS)  # cualquier archivo existente
    monkeypatch.setattr(config, "cargar_criterios", lambda: CRITERIOS)

    async def evaluar_falso(c, cv, criterios):
        return CandidataEvaluada(candidata=c, evaluacion=Evaluacion(**EVAL_APLICAR), costo_usd=0.02)

    monkeypatch.setattr(api, "evaluar", evaluar_falso)
    with cliente.stream("GET", "/api/evaluar/stream", params={"limite": 5}) as r:
        eventos = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ")]
    assert [e["tipo"] for e in eventos] == ["inicio", "evaluada", "fin"]
    assert eventos[0]["pendientes"] == 1
    assert len(json.loads(config.EVALUADAS.read_text())) == 3


def test_rag_sin_docker_da_503(cliente, monkeypatch):
    from job_agent import vectores

    def explota(*a, **k):
        raise ConnectionError("sin docker")

    monkeypatch.setattr(vectores, "conectar", explota)
    r = cliente.get("/api/rag/buscar", params={"q": "agentes"})
    assert r.status_code == 503 and "Docker" in r.json()["detail"]


def test_tracker_guarda_historial_de_etapas(cliente):
    oid = api.oferta_id("https://x/a")
    cliente.post("/api/tracker", json={"id": oid})
    cliente.patch(f"/api/tracker/{oid}", json={"estado": "aplicada"})
    cliente.patch(f"/api/tracker/{oid}", json={"estado": "aplicada"})  # repetir no duplica
    cliente.patch(f"/api/tracker/{oid}", json={"notas": "x"})
    hist = cliente.get("/api/tracker").json()[0]["historial"]
    assert [h["estado"] for h in hist] == ["para aplicar", "aplicada"]


def test_agente_guarda_ultima_ejecucion(cliente, monkeypatch):
    async def eventos_falsos(pedido, objetivo, max_ev):
        yield {"tipo": "herramienta", "nombre": "ver_oferta", "input": {"id": "o1"}}
        yield {"tipo": "herramienta", "nombre": "evaluar_oferta", "input": {"id": "o1"}}
        yield {"tipo": "fin", "turnos": 3, "evaluaciones_nuevas": 1, "max_evaluaciones": 2,
               "costo_agente_usd": 0.1, "costo_evaluaciones_usd": 0.05}

    monkeypatch.setattr(api.agente, "eventos", eventos_falsos)
    assert cliente.get("/api/agente/ultima").json() is None
    with cliente.stream("GET", "/api/agente/stream", params={"pedido": "AI"}) as r:
        list(r.iter_lines())
    u = cliente.get("/api/agente/ultima").json()
    assert u["ofertas_analizadas"] == 2 and u["evaluaciones"] == 1 and u["costo_usd"] == 0.15
