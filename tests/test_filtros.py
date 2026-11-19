"""Tests de los filtros con casos reales que aparecieron en la API de Himalayas."""

from job_agent.config import Criterios
from job_agent.filtros import (
    filtrar,
    limpiar_html,
    paises_validos,
    salario_usd_mes,
    seniority_excluida,
    zona_ok,
)
from job_agent.models import Job

CRITERIOS = Criterios.model_validate(
    {
        "roles": ["AI Engineer"],
        "zonaHoraria": {"minUTC": -3, "maxUTC": 2, "toleranciaHoras": 2},
        "paisesResidencia": ["Argentina"],
        "excluirSeniority": ["Intern", "Entry-level"],
        "salarioMinimoUSDMes": 2500,
    }
)
DESC_LARGA = "<p>" + "Build LLM agents with tools. " * 30 + "</p>"


def job(**over) -> Job:
    base = {
        "guid": "g1",
        "title": "AI Engineer",
        "companyName": "Acme",
        "applicationLink": "https://example.com/1",
        "description": DESC_LARGA,
    }
    return Job.model_validate(base | over)


# --- salario ---------------------------------------------------------------

def test_salario_anual_a_mensual():
    s = salario_usd_mes(job(minSalary=30000, maxSalary=60000, salaryPeriod="annual", currency="USD"))
    assert (s.min, s.max) == (2500, 5000)


def test_salario_por_hora_asume_jornada_completa():
    # micro1: USD 60-120/h → 160 h/mes
    s = salario_usd_mes(job(minSalary=60, maxSalary=120, salaryPeriod="hourly", currency="USD"))
    assert (s.min, s.max) == (9600, 19200)


def test_salario_nulo_aunque_periodo_diga_annual():
    # DECODE: salary null pero salaryPeriod "annual"
    assert salario_usd_mes(job(salaryPeriod="annual", currency=None)) is None


def test_salario_en_otra_moneda_no_se_convierte():
    assert salario_usd_mes(job(minSalary=50000, maxSalary=60000, salaryPeriod="annual", currency="EUR")) is None


def test_salario_con_un_solo_extremo():
    s = salario_usd_mes(job(maxSalary=36000, salaryPeriod="annual", currency="USD"))
    assert (s.min, s.max) == (3000, 3000)


# --- zona horaria ----------------------------------------------------------

def test_sin_restriccion_horaria_pasa():
    assert zona_ok(job(), CRITERIOS)


def test_costa_este_eeuu_entra_por_tolerancia():
    # [-5, -4] no incluye -3, pero con ±2 h sí: desde Argentina son 1-2 h de diferencia
    assert zona_ok(job(timezoneRestrictions=[-5, -4]), CRITERIOS)


def test_pacifico_queda_afuera():
    assert not zona_ok(job(timezoneRestrictions=[-8, -7]), CRITERIOS)


# --- países ----------------------------------------------------------------

def test_lista_vacia_es_cualquier_pais():
    assert paises_validos(job(), CRITERIOS) == ["cualquiera"]


def test_pais_de_la_candidata_incluido():
    assert paises_validos(job(locationRestrictions=["Mexico", "Argentina"]), CRITERIOS) == ["Argentina"]


def test_pais_no_incluido():
    # DECODE: solo Alemania
    assert paises_validos(job(locationRestrictions=["Germany"]), CRITERIOS) is None


# --- seniority -------------------------------------------------------------

def test_pasantia_por_titulo():
    assert seniority_excluida(job(title="AI & Engineering Intern"), CRITERIOS)


def test_internal_no_es_intern():
    assert not seniority_excluida(job(title="Internal Tools Engineer"), CRITERIOS)


# --- html ------------------------------------------------------------------

def test_html_doblemente_escapado():
    # Arbeitnow manda &lt;p&gt; en vez de <p>
    assert limpiar_html("&lt;p&gt;Hola &amp;amp; chau&lt;/p&gt;") == "Hola & chau"


# --- pipeline --------------------------------------------------------------

def test_filtrar_cuenta_motivos_y_ordena_por_salario():
    jobs = [
        job(guid="a", locationRestrictions=["Germany"]),
        job(guid="b", description="<p>Just one more step.</p>"),
        job(guid="c", minSalary=1000, maxSalary=2000, salaryPeriod="monthly", currency="USD"),
        job(guid="d", minSalary=3000, maxSalary=4000, salaryPeriod="monthly", currency="USD"),
        job(guid="e"),
    ]
    candidatas, descartes = filtrar(jobs, CRITERIOS, ahora=0)
    assert descartes["pais"] == 1
    assert descartes["desc_vacia"] == 1
    assert descartes["salario_bajo"] == 1
    assert [c.salario_usd_mes.max if c.salario_usd_mes else None for c in candidatas] == [4000, None]
