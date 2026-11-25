"""Filtros determinísticos: todo lo que se puede decidir con código, sin LLM.

Son funciones puras (sin red ni disco) para poder testearlas.
"""

import html
import re
from datetime import date, datetime, timezone

from job_agent.config import Criterios
from job_agent.models import Candidata, Evaluacion, Job, RangoSalario

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


def cobertura(paises: list[str], criterios: Criterios) -> str:
    """'total' si podés trabajar desde todos los lugares donde vivís durante el año; si no, 'parcial'.
    Sin zonas configuradas, todo es 'total' (alcanza con coincidir en un país)."""
    if "cualquiera" in paises or not criterios.zonas_residencia:
        return "total"
    return "total" if all(set(paises) & set(zona) for zona in criterios.zonas_residencia) else "parcial"


def seniority_excluida(job: Job, criterios: Criterios) -> bool:
    if any(s in criterios.excluir_seniority for s in job.seniority):
        return True
    return re.search(r"\bintern(ship)?\b", job.title, re.IGNORECASE) is not None


def limpiar_html(texto: str) -> str:
    """Saca etiquetas y entidades. Desescapa dos veces: algunas APIs mandan &amp;lt;p&amp;gt;."""
    texto = html.unescape(html.unescape(texto))
    texto = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _fecha(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else None


def clave_oferta(titulo: str, empresa: str) -> str:
    """Misma empresa + mismo título = misma oferta, aunque se publique en varios países con links distintos."""
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()  # noqa: E731
    return f"{norm(empresa)}|{norm(titulo)}"


def vencida(c: Candidata, hoy: date) -> bool:
    """Solo si la fuente informó la fecha: sin dato no se puede afirmar que venció."""
    return c.vence is not None and date.fromisoformat(c.vence) < hoy


def aplicar_reglas(ev: Evaluacion) -> Evaluacion:
    """Reglas duras sobre el veredicto del LLM. Hoy, una: si no está claro que puedas trabajar
    desde donde vivís, no es 'aplicar' (los evals mostraron que el modelo lo marca como riesgo
    y aun así recomienda aplicar). El puntaje de encaje no se toca: mide otra cosa."""
    if ev.veredicto == "aplicar" and ev.elegible_ubicacion != "sí":
        nota = "Bajado a 'dudoso': confirmá si contratan desde donde vivís antes de aplicar."
        return ev.model_copy(update={"veredicto": "dudoso", "red_flags": [nota, *ev.red_flags]})
    return ev


def a_candidata(job: Job, paises: list[str], salario: RangoSalario | None, texto: str) -> Candidata:
    publicada = _fecha(job.pub_date)
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
        vence=_fecha(job.expiry_date),
    )


def motivo_descarte(job: Job, criterios: Criterios, ahora: float) -> str | None:
    """Primer filtro que la oferta no pasa, o None si pasa todos."""
    if job.expiry_date and job.expiry_date < ahora:
        return "vencida"
    if not zona_ok(job, criterios):
        return "zona_horaria"
    paises = paises_validos(job, criterios)
    if paises is None:
        return "pais"
    if not criterios.incluir_parciales and cobertura(paises, criterios) == "parcial":
        return "cobertura_parcial"
    if seniority_excluida(job, criterios):
        return "seniority"
    salario = salario_usd_mes(job)
    if salario and salario.max < criterios.salario_minimo_usd_mes:
        return "salario_bajo"
    if len(limpiar_html(job.description)) < MIN_CHARS_DESC:
        return "desc_vacia"
    return None


def a_candidata_desde_job(job: Job, criterios: Criterios) -> Candidata:
    return a_candidata(job, paises_validos(job, criterios) or [], salario_usd_mes(job), limpiar_html(job.description))


def filtrar(
    jobs: list[Job], criterios: Criterios, ahora: float
) -> tuple[list[Candidata], dict[str, int]]:
    """Aplica los filtros en orden y cuenta por qué se descartó cada oferta."""
    descartes = dict.fromkeys(
        ["vencida", "zona_horaria", "pais", "cobertura_parcial", "seniority", "salario_bajo", "desc_vacia"], 0
    )
    descartes["duplicada"] = 0
    candidatas: list[Candidata] = []
    for job in jobs:
        motivo = motivo_descarte(job, criterios, ahora)
        if motivo:
            descartes[motivo] += 1
        else:
            candidatas.append(a_candidata_desde_job(job, criterios))

    # Salario más alto primero; las sin dato al final.
    candidatas.sort(key=lambda c: c.salario_usd_mes.max if c.salario_usd_mes else -1, reverse=True)
    # Una sola por empresa+título: la misma oferta publicada en varios países se evaluaría
    # (y se pagaría) varias veces. Se queda la primera, que es la de mejor salario.
    unicas: dict[str, Candidata] = {}
    for c in candidatas:
        k = clave_oferta(c.titulo, c.empresa)
        if k in unicas:
            descartes["duplicada"] += 1
        else:
            unicas[k] = c
    return list(unicas.values()), descartes
