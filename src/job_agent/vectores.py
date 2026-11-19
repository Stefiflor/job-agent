"""Fase 4: índice vectorial de ofertas en Postgres + pgvector (búsqueda semántica)."""

import json
import os
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector

from job_agent.config import Criterios
from job_agent.embeddings import Embedder
from job_agent.filtros import a_candidata_desde_job, limpiar_html, motivo_descarte
from job_agent.models import Candidata, Job

URL_DEFAULT = "postgresql://jobagent:jobagent@localhost:5433/jobagent"
MAX_CHARS_EMBED = 4000


def url_db() -> str:
    return os.environ.get("DATABASE_URL", URL_DEFAULT)


def conectar(url: str | None = None) -> psycopg.Connection:
    conn = psycopg.connect(url or url_db(), autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def crear_esquema(conn: psycopg.Connection, dim: int, recrear: bool = False) -> None:
    if recrear:
        conn.execute("DROP TABLE IF EXISTS ofertas")
    actual = conn.execute(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid = to_regclass('ofertas') AND attname = 'embedding'"
    ).fetchone()
    if actual and actual[0] != dim:
        raise SystemExit(
            f"El índice tiene vectores de {actual[0]} dimensiones y el modelo genera {dim}. "
            "Cambiaste de modelo: corré `rag indexar --recrear`."
        )
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS ofertas (
            link         text PRIMARY KEY,
            titulo       text NOT NULL,
            empresa      text NOT NULL,
            texto        text NOT NULL,
            pasa_filtros boolean NOT NULL,
            motivo       text,
            candidata    jsonb,
            modelo       text NOT NULL,
            embedding    vector({dim}) NOT NULL,
            actualizado  timestamptz NOT NULL DEFAULT now()
        )""")
    # HNSW: búsqueda aproximada rápida. vector_cosine_ops porque comparamos por coseno.
    conn.execute("CREATE INDEX IF NOT EXISTS ofertas_embedding_idx ON ofertas USING hnsw (embedding vector_cosine_ops)")


def texto_para_embedding(job: Job) -> str:
    return f"{job.title}\n{job.company_name}\n{limpiar_html(job.description)[:MAX_CHARS_EMBED]}"


def indexar(conn, jobs: list[Job], embedder: Embedder, criterios: Criterios, ahora: float) -> dict[str, int]:
    """Upsert por link. Reindexa si la oferta ya estaba (puede haber cambiado el texto o los criterios)."""
    unicos = list({j.application_link: j for j in jobs}.values())
    if not unicos:
        return {"indexadas": 0, "pasan_filtros": 0}
    vectores = embedder.encode([texto_para_embedding(j) for j in unicos])
    pasan = 0
    with conn.cursor() as cur:
        for job, vec in zip(unicos, vectores):
            motivo = motivo_descarte(job, criterios, ahora)
            cand = None if motivo else a_candidata_desde_job(job, criterios).model_dump(mode="json")
            pasan += motivo is None
            cur.execute(
                """INSERT INTO ofertas (link, titulo, empresa, texto, pasa_filtros, motivo, candidata, modelo, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (link) DO UPDATE SET
                     titulo = EXCLUDED.titulo, empresa = EXCLUDED.empresa, texto = EXCLUDED.texto,
                     pasa_filtros = EXCLUDED.pasa_filtros, motivo = EXCLUDED.motivo,
                     candidata = EXCLUDED.candidata, modelo = EXCLUDED.modelo,
                     embedding = EXCLUDED.embedding, actualizado = now()""",
                (job.application_link, job.title, job.company_name, limpiar_html(job.description),
                 motivo is None, motivo, json.dumps(cand) if cand else None, embedder.nombre, vec),
            )
    return {"indexadas": len(unicos), "pasan_filtros": pasan}


@dataclass
class Resultado:
    link: str
    titulo: str
    empresa: str
    similitud: float
    pasa_filtros: bool
    motivo: str | None
    candidata: Candidata | None


def _filas(rows) -> list[Resultado]:
    return [
        Resultado(link=r[0], titulo=r[1], empresa=r[2], similitud=float(r[3]), pasa_filtros=r[4],
                  motivo=r[5], candidata=Candidata.model_validate(r[6]) if r[6] else None)
        for r in rows
    ]


def buscar(conn, embedder: Embedder, consulta: str, k: int = 10, solo_filtradas: bool = True) -> list[Resultado]:
    q = embedder.encode([consulta])[0]
    # <=> es distancia coseno en pgvector; similitud = 1 - distancia.
    rows = conn.execute(
        f"""SELECT link, titulo, empresa, 1 - (embedding <=> %s) AS sim, pasa_filtros, motivo, candidata
            FROM ofertas {"WHERE pasa_filtros" if solo_filtradas else ""}
            ORDER BY embedding <=> %s LIMIT %s""",
        (q, q, k),
    ).fetchall()
    return _filas(rows)


def similares(conn, link: str, k: int = 10, solo_filtradas: bool = True) -> list[Resultado]:
    rows = conn.execute(
        f"""SELECT o.link, o.titulo, o.empresa, 1 - (o.embedding <=> ref.embedding), o.pasa_filtros, o.motivo, o.candidata
            FROM ofertas o, (SELECT embedding FROM ofertas WHERE link = %s) ref
            WHERE o.link <> %s {"AND o.pasa_filtros" if solo_filtradas else ""}
            ORDER BY o.embedding <=> ref.embedding LIMIT %s""",
        (link, link, k),
    ).fetchall()
    return _filas(rows)


def contar(conn) -> tuple[int, int]:
    r = conn.execute("SELECT count(*), count(*) FILTER (WHERE pasa_filtros) FROM ofertas").fetchone()
    return int(r[0]), int(r[1])
