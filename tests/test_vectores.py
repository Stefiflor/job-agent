"""Tests del índice vectorial contra un Postgres real con pgvector.

Se saltean si no hay DATABASE_URL_TEST. Para correrlos:
  docker compose up -d
  DATABASE_URL_TEST=postgresql://jobagent:jobagent@localhost:5433/jobagent uv run pytest tests/test_vectores.py
"""

import hashlib
import os
import re

import numpy as np
import pytest

from job_agent.embeddings import normalizar
from tests.test_filtros import CRITERIOS, DESC_LARGA, job

URL = os.environ.get("DATABASE_URL_TEST")
pytestmark = pytest.mark.skipif(not URL, reason="sin DATABASE_URL_TEST")


class EmbedderFalso:
    """Bolsa de palabras con hashing: determinístico y sin descargar modelos."""

    nombre = "falso-64"
    dim = 64

    def encode(self, textos):
        m = np.zeros((len(textos), self.dim), dtype=np.float32)
        for i, t in enumerate(textos):
            for w in re.findall(r"[a-z]+", t.lower()):
                m[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1
        return normalizar(m)


@pytest.fixture
def conn():
    from job_agent import vectores

    c = vectores.conectar(URL)
    vectores.crear_esquema(c, EmbedderFalso.dim, recrear=True)
    yield c
    c.execute("DROP TABLE IF EXISTS ofertas")
    c.close()


def jobs_de_prueba():
    return [
        job(guid="1", title="LLM agents engineer", applicationLink="https://x/1",
            description="<p>" + "Build LLM agents with tool calling and evals. " * 20 + "</p>"),
        job(guid="2", title="React frontend developer", applicationLink="https://x/2",
            description="<p>" + "React components, CSS, accessibility, design systems. " * 20 + "</p>"),
        job(guid="3", title="LLM agents engineer Germany", applicationLink="https://x/3",
            locationRestrictions=["Germany"],
            description="<p>" + "Build LLM agents with tool calling. " * 20 + "</p>"),
    ]


def test_indexar_y_buscar_semantico(conn):
    from job_agent import vectores

    stats = vectores.indexar(conn, jobs_de_prueba(), EmbedderFalso(), CRITERIOS, ahora=0)
    assert stats == {"indexadas": 3, "pasan_filtros": 2}
    r = vectores.buscar(conn, EmbedderFalso(), "agents with tool calling", k=5)
    assert r[0].link == "https://x/1"
    assert all(x.pasa_filtros for x in r)  # la de Alemania no aparece
    todas = vectores.buscar(conn, EmbedderFalso(), "agents with tool calling", k=5, solo_filtradas=False)
    assert {x.link for x in todas} == {"https://x/1", "https://x/2", "https://x/3"}
    assert next(x for x in todas if x.link == "https://x/3").motivo == "pais"


def test_upsert_no_duplica(conn):
    from job_agent import vectores

    vectores.indexar(conn, jobs_de_prueba(), EmbedderFalso(), CRITERIOS, ahora=0)
    vectores.indexar(conn, jobs_de_prueba(), EmbedderFalso(), CRITERIOS, ahora=0)
    assert vectores.contar(conn) == (3, 2)


def test_similares_excluye_la_propia(conn):
    from job_agent import vectores

    vectores.indexar(conn, jobs_de_prueba(), EmbedderFalso(), CRITERIOS, ahora=0)
    r = vectores.similares(conn, "https://x/1", k=5, solo_filtradas=False)
    assert r[0].link == "https://x/3"  # misma descripción casi
    assert "https://x/1" not in {x.link for x in r}


def test_cambio_de_dimension_avisa(conn):
    from job_agent import vectores

    with pytest.raises(SystemExit, match="recrear"):
        vectores.crear_esquema(conn, 128)
