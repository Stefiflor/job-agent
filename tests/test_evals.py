from job_agent.evals import informe_markdown, metricas, muestra_estratificada
from job_agent.models import Evaluacion
from tests.test_agente import EVAL_APLICAR


class E:  # evaluada mínima para la muestra
    def __init__(self, v):
        self.evaluacion = Evaluacion(**(EVAL_APLICAR | {"veredicto": v}))


def test_metricas_acuerdo_graves_y_consistencia():
    humano = {"a": "aplicar", "b": "descartar", "c": "dudoso"}
    modelo = {"a": ["aplicar", "aplicar"], "b": ["aplicar", "descartar"], "c": ["dudoso", "dudoso"]}
    encajes = {"a": [80, 80], "b": [70, 30], "c": [50, 50]}
    m = metricas(humano, modelo, encajes)
    assert m["evaluaciones"] == 6
    assert round(m["acuerdo_exacto"], 3) == round(5 / 6, 3)
    assert round(m["errores_graves"], 3) == round(1 / 6, 3)  # b: descartar→aplicar
    assert round(m["consistencia"], 3) == round(2 / 3, 3)
    assert m["desvio_encaje_promedio"] == 20 / 3  # solo b varía (pstdev 20)


def test_oferta_sin_respuesta_del_modelo_no_cuenta():
    m = metricas({"a": "aplicar", "b": "dudoso"}, {"a": ["aplicar"]}, {"a": [80]})
    assert m["ofertas"] == 1 and m["acuerdo_exacto"] == 1


def test_muestra_estratificada_balancea():
    evaluadas = [E("dudoso")] * 20 + [E("aplicar")] * 5 + [E("descartar")] * 5
    elegidas = muestra_estratificada(evaluadas, 9)
    conteo = {v: sum(e.evaluacion.veredicto == v for e in elegidas) for v in ["aplicar", "dudoso", "descartar"]}
    assert conteo == {"aplicar": 3, "dudoso": 3, "descartar": 3}


def test_informe_tiene_tabla():
    m = metricas({"a": "aplicar"}, {"a": ["dudoso"]}, {"a": [60]})
    md = informe_markdown(m, 1)
    assert "| Acuerdo exacto con humano | 0% |" in md
    assert "| aplicar | 0 | 1 | 0 |" in md
