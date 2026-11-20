import asyncio

from job_agent import carta
from job_agent.carta import Afirmacion, Borrador, Problema, Verificacion, fragmentar, recuperar
from job_agent.filtros import a_candidata_desde_job
from tests.test_filtros import CRITERIOS, job
from tests.test_vectores import EmbedderFalso

MD = """# Experience
## Agent
- Built a booking agent with tool calling.
- Built an anti-hallucination verifier.
## Frontend
- Built Vue.js interfaces.
"""
CANDIDATA = a_candidata_desde_job(job(title="LLM agent engineer"), CRITERIOS)


def test_fragmentar_un_fragmento_por_bullet_con_seccion():
    f = fragmentar(MD)
    assert [(x.id, x.seccion) for x in f] == [("E1", "Agent"), ("E2", "Agent"), ("E3", "Frontend")]


def test_recuperar_prioriza_lo_parecido():
    r = recuperar(fragmentar(MD), "tool calling booking agent", EmbedderFalso(), k=1)
    assert r[0].id == "E1"


def _generar_con(respuestas, monkeypatch):
    llamadas = []

    async def falso(prompt, system, modelo):
        llamadas.append(modelo.__name__)
        return respuestas.pop(0), 0.01

    monkeypatch.setattr(carta, "_estructurado", falso)
    r = asyncio.run(carta.generar(CANDIDATA, fragmentar(MD), EmbedderFalso()))
    return r, llamadas


def test_reescribe_si_el_verificador_rechaza(monkeypatch):
    malo = Borrador(carta="I led a team of 20.", afirmaciones=[Afirmacion(texto="led a team of 20", fuentes=["E1"])])
    bueno = Borrador(carta="I built a booking agent.", afirmaciones=[Afirmacion(texto="built a booking agent", fuentes=["E1"])])
    r, llamadas = _generar_con([
        malo, Verificacion(respaldada=False, problemas=[Problema(afirmacion="led a team of 20", motivo="not in fragments")]),
        bueno, Verificacion(respaldada=True, problemas=[]),
    ], monkeypatch)
    assert r.intentos == 2 and r.borrador.carta == "I built a booking agent."
    assert llamadas == ["Borrador", "Verificacion", "Borrador", "Verificacion"]


def test_fuente_inexistente_se_rechaza_sin_llamar_al_verificador(monkeypatch):
    inventa = Borrador(carta="x", afirmaciones=[Afirmacion(texto="x", fuentes=["E99"])])
    bueno = Borrador(carta="ok", afirmaciones=[Afirmacion(texto="ok", fuentes=["E2"])])
    r, llamadas = _generar_con([inventa, bueno, Verificacion(respaldada=True, problemas=[])], monkeypatch)
    assert llamadas == ["Borrador", "Borrador", "Verificacion"]
    assert r.verificacion.respaldada


def test_se_rinde_tras_max_intentos(monkeypatch):
    malo = Borrador(carta="x", afirmaciones=[Afirmacion(texto="x", fuentes=["E1"])])
    rechazo = Verificacion(respaldada=False, problemas=[Problema(afirmacion="x", motivo="no")])
    r, _ = _generar_con([malo, rechazo, malo, rechazo], monkeypatch)
    assert r.intentos == carta.MAX_INTENTOS and not r.verificacion.respaldada
