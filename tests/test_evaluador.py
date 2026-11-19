from job_agent.evaluador import opciones
from job_agent.models import Evaluacion


def test_schema_exige_todos_los_campos():
    schema = Evaluacion.model_json_schema()
    assert set(schema["required"]) == set(Evaluacion.model_fields)


def test_sin_herramientas():
    assert opciones().tools == []


def test_consume_todo_el_stream_y_usa_el_ultimo_resultado(monkeypatch):
    """Regresión: no cortar el generador de query() a mitad (error aclose en Python 3.14)."""
    import asyncio

    from claude_agent_sdk import ResultMessage

    from job_agent import evaluador
    from tests.test_filtros import CRITERIOS
    from job_agent.models import Candidata

    consumidos = []
    salida = {
        "encaje": 70, "veredicto": "aplicar", "tipo_puesto": "full stack / frontend",
        "elegible_ubicacion": "sí", "salario_detectado": "sin dato",
        "cumple": [], "falta": [], "red_flags": [], "resumen": "ok",
    }

    async def query_falso(prompt, options):
        for i in range(3):
            consumidos.append(i)
            if i == 1:
                yield ResultMessage(subtype="success", duration_ms=5, duration_api_ms=5,
                                    is_error=False, num_turns=1, session_id="s",
                                    total_cost_usd=0.01, structured_output=salida)
            else:
                yield object()

    monkeypatch.setattr(evaluador, "query", query_falso)
    c = Candidata(titulo="t", empresa="e", tipo=None, seniority=[], salario_usd_mes=None,
                  salario_original="sin dato", por_hora=False, paises_validos=["cualquiera"],
                  publicada=None, link="https://x", descripcion="d")
    r = asyncio.run(evaluador.evaluar(c, "cv", CRITERIOS))
    assert consumidos == [0, 1, 2]
    assert r.evaluacion.encaje == 70
