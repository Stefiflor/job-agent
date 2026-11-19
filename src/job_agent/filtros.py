"""Filtros determinísticos: todo lo que se puede decidir con código, sin LLM.

Son funciones puras (sin red ni disco) para poder testearlas.
"""

import html
import re
from datetime import datetime, timezone

from job_agent.config import Criterios
from job_agent.models import Candidata, Job, RangoSalario

HORAS_MES = 160  # jornada completa; las ofertas por hora se marcan aparte
MIN_CHARS_DESC = 500  # menos que esto suele ser una descripción de plantilla
FACTOR_MENSUAL = {"annual": 1 / 12, "monthly": 1, "hourly": HORAS_MES}


def salario_usd_mes(job: Job) -> RangoSalario | None:
    """Normaliza el salario a USD por mes. None si no hay dato o no es USD."""
    if job.currency != "USD" or (job.min_salary is None and job.max_salary is None):
        return None
    factor = FACTOR_MENSUAL.get(job.salary_period or "")
    if factor is None:
        return None
    minimo = job.min_salary if job.min_salary is not None else job.max_salary
    maximo = job.max_salary if job.max_salary is not None else job.min_salary
    return RangoSalario(min=round(minimo * factor), max=round(maximo * factor))


def zona_ok(job: Job, criterios: Criterios) -> bool:
    """True si alguna zona horaria permitida cae en el rango de la candidata (+ tolerancia)."""
    if not job.timezone_restrictions:
        return True
    z = criterios.zona_horaria
    lo, hi = z.min_utc - z.tolerancia_horas, z.max_utc + z.tolerancia_horas
    return any(lo <= tz <= hi for tz in job.timezone_restrictions)


def paises_validos(job: Job, criterios: Criterios) -> list[str] | None:
    """Países de la candidata que la oferta acepta. Lista vacía en la API = cualquiera."""
    if not job.location_restrictions:
        return ["cualquiera"]
    ok = [p for p in job.location_restrictions if p in criterios.paises_residencia]
    return ok or None


def seniority_excluida(job: Job, criterios: Criterios) -> bool:
    if any(s in criterios.excluir_seniority for s in job.seniority):
        return True
    return re.search(r"\bintern(ship)?\b", job.title, re.IGNORECASE) is not None


def limpiar_html(texto: str) -> str:
    """Saca etiquetas y entidades. Desescapa dos veces: algunas APIs mandan &amp;lt;p&amp;gt;."""
    texto = html.unescape(html.unescape(texto))
    texto = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def a_candidata(job: Job, paises: list[str], salario: RangoSalario | None, texto: str) -> Candidata:
    publicada = (
        datetime.fromtimestamp(job.pub_date, tz=timezone.utc).date().isoformat()
        if job.pub_date
        else None
    )
    return Candidata(
        titulo=job.title,
        empresa=job.company_name,
        tipo=job.employment_type,
        seniority=job.seniority,
        salario_usd_mes=salario,
        salario_original=(
            f"{job.min_salary}-{job.max_salary} {job.currency}/{job.salary_period}"
            if salario
            else "sin dato"
        ),
        por_hora=job.salary_period == "hourly" and salario is not None,
        paises_validos=paises,
        publicada=publicada,
        link=job.application_link,
        descripcion=texto,
    )


def filtrar(
    jobs: list[Job], criterios: Criterios, ahora: float
) -> tuple[list[Candidata], dict[str, int]]:
    """Aplica los filtros en orden y cuenta por qué se descartó cada oferta."""
    descartes = dict.fromkeys(
        ["vencida", "zona_horaria", "pais", "seniority", "salario_bajo", "desc_vacia"], 0
    )
    candidatas: list[Candidata] = []

    for job in jobs:
        if job.expiry_date and job.expiry_date < ahora:
            descartes["vencida"] += 1
            continue
        if not zona_ok(job, criterios):
            descartes["zona_horaria"] += 1
            continue
        paises = paises_validos(job, criterios)
        if paises is None:
            descartes["pais"] += 1
            continue
        if seniority_excluida(job, criterios):
            descartes["seniority"] += 1
            continue
        salario = salario_usd_mes(job)
        if salario and salario.max < criterios.salario_minimo_usd_mes:
            descartes["salario_bajo"] += 1
            continue
        texto = limpiar_html(job.description)
        if len(texto) < MIN_CHARS_DESC:
            descartes["desc_vacia"] += 1
            continue
        candidatas.append(a_candidata(job, paises, salario, texto))

    # Salario más alto primero; las sin dato al final.
    candidatas.sort(key=lambda c: c.salario_usd_mes.max if c.salario_usd_mes else -1, reverse=True)
    return candidatas, descartes
