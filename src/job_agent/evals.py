"""Fase 3: evals. ¿Cuánto coincide el evaluador con el criterio humano, y qué tan estable es?

Flujo:
  1. `evals preparar`  → muestra estratificada de ofertas en un CSV, SIN el veredicto del modelo
                         (para no sesgar a quien etiqueta).
  2. La persona completa la columna `tu_veredicto` (aplicar / dudoso / descartar).
  3. `evals correr`    → evalúa cada oferta N veces y compara con las etiquetas.
"""

import csv
import json
import random
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

from job_agent import config
from job_agent.evaluador import cargar_evaluadas, evaluar
from job_agent.models import Candidata

DIR_EVALS = config.PRIVADO / "evals"
DATASET = DIR_EVALS / "dataset.json"
ETIQUETAS = DIR_EVALS / "etiquetas.csv"
VEREDICTOS = ["aplicar", "dudoso", "descartar"]
ORDEN = {v: i for i, v in enumerate(VEREDICTOS)}


# --- Preparar ----------------------------------------------------------------

def muestra_estratificada(evaluadas: list, n: int, semilla: int = 42) -> list:
    """Reparte la muestra entre veredictos del modelo: si no, casi todo sería 'dudoso'
    y no mediríamos los extremos, que son los errores que más importan."""
    rng = random.Random(semilla)
    grupos = {v: [e for e in evaluadas if e.evaluacion.veredicto == v] for v in VEREDICTOS}
    for g in grupos.values():
        rng.shuffle(g)
    elegidas, i = [], 0
    while len(elegidas) < n and any(grupos.values()):
        g = grupos[VEREDICTOS[i % 3]]
        if g:
            elegidas.append(g.pop())
        i += 1
    rng.shuffle(elegidas)  # que el orden no delate el estrato
    return elegidas


def preparar(n: int) -> None:
    if ETIQUETAS.exists():
        raise SystemExit(f"Ya existe {ETIQUETAS.relative_to(config.RAIZ)}. Borralo si querés empezar de nuevo.")
    evaluadas = cargar_evaluadas(config.EVALUADAS)
    if len(evaluadas) < n:
        raise SystemExit(f"Hay {len(evaluadas)} ofertas evaluadas; corré `evaluar` primero o pedí menos.")
    elegidas = muestra_estratificada(evaluadas, n)

    DIR_EVALS.mkdir(parents=True, exist_ok=True)
    dataset = [{"id": f"e{i}", "candidata": e.candidata.model_dump(mode="json")} for i, e in enumerate(elegidas, 1)]
    DATASET.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    with ETIQUETAS.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "titulo", "empresa", "link", "tu_veredicto", "tu_nota"])
        for d in dataset:
            c = d["candidata"]
            w.writerow([d["id"], c["titulo"], c["empresa"], c["link"], "", ""])
    print(f"{n} ofertas → {ETIQUETAS.relative_to(config.RAIZ)}")
    print("Abrí cada link, decidí vos y completá tu_veredicto con: aplicar / dudoso / descartar.")


# --- Métricas (funciones puras, testeadas) -----------------------------------

def leer_etiquetas(ruta: Path = ETIQUETAS) -> dict[str, str]:
    with ruta.open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    etiquetas = {}
    for fila in filas:
        v = fila["tu_veredicto"].strip().lower()
        if v:
            if v not in ORDEN:
                raise SystemExit(f"{fila['id']}: '{v}' no es válido. Usá aplicar / dudoso / descartar.")
            etiquetas[fila["id"]] = v
    return etiquetas


def metricas(humano: dict[str, str], modelo: dict[str, list[str]], encajes: dict[str, list[int]]) -> dict:
    """humano: id → veredicto. modelo: id → veredictos de cada repetición."""
    ids = [i for i in humano if modelo.get(i)]
    pares = [(humano[i], r) for i in ids for r in modelo[i]]
    total = len(pares)
    exactos = sum(h == m for h, m in pares)
    # Error grave: el modelo dice "aplicar" y vos "descartar", o al revés.
    graves = sum(abs(ORDEN[h] - ORDEN[m]) == 2 for h, m in pares)
    # Consistencia: ¿repite el mismo veredicto en todas las corridas de la misma oferta?
    consistentes = sum(len(set(modelo[i])) == 1 for i in ids)
    desvios = [statistics.pstdev(encajes[i]) for i in ids if len(encajes.get(i, [])) > 1]
    confusion = Counter(pares)
    return {
        "ofertas": len(ids),
        "evaluaciones": total,
        "acuerdo_exacto": exactos / total if total else 0,
        "errores_graves": graves / total if total else 0,
        "consistencia": consistentes / len(ids) if ids else 0,
        "desvio_encaje_promedio": statistics.mean(desvios) if desvios else 0,
        "confusion": {f"{h}→{m}": n for (h, m), n in sorted(confusion.items())},
    }


def informe_markdown(m: dict, repeticiones: int) -> str:
    filas = "\n".join(
        f"| {h} | " + " | ".join(str(m["confusion"].get(f"{h}→{x}", 0)) for x in VEREDICTOS) + " |"
        for h in VEREDICTOS
    )
    return f"""| Métrica | Valor |
|---|---|
| Ofertas etiquetadas | {m['ofertas']} |
| Evaluaciones ({repeticiones} por oferta) | {m['evaluaciones']} |
| Acuerdo exacto con humano | {m['acuerdo_exacto']:.0%} |
| Errores graves (aplicar ↔ descartar) | {m['errores_graves']:.0%} |
| Consistencia entre corridas | {m['consistencia']:.0%} |
| Desvío promedio del encaje (puntos) | {m['desvio_encaje_promedio']:.1f} |

Matriz de confusión (filas = humano, columnas = modelo):

| humano \\ modelo | aplicar | dudoso | descartar |
|---|---|---|---|
{filas}"""


# --- Correr ------------------------------------------------------------------

async def correr(repeticiones: int) -> None:
    humano = leer_etiquetas()
    if not humano:
        raise SystemExit("No hay etiquetas: completá tu_veredicto en el CSV.")
    dataset = {d["id"]: Candidata.model_validate(d["candidata"]) for d in json.loads(DATASET.read_text(encoding="utf-8"))}
    criterios = config.cargar_criterios()
    cv = config.CV.read_text(encoding="utf-8")

    modelo: dict[str, list[str]] = {}
    encajes: dict[str, list[int]] = {}
    costo = 0.0
    total = len(humano) * repeticiones
    n = 0
    for oid in humano:
        for _ in range(repeticiones):
            n += 1
            r = await evaluar(dataset[oid], cv, criterios)
            if r is None:
                continue
            modelo.setdefault(oid, []).append(r.evaluacion.veredicto)
            encajes.setdefault(oid, []).append(r.evaluacion.encaje)
            costo += r.costo_usd or 0
            print(f"({n}/{total}) {oid}: vos={humano[oid]} modelo={r.evaluacion.veredicto} ({r.evaluacion.encaje})")

    m = metricas(humano, modelo, encajes)
    md = informe_markdown(m, repeticiones)
    sello = datetime.now().strftime("%Y-%m-%d_%H%M")
    salida = DIR_EVALS / f"resultado-{sello}.json"
    salida.write_text(
        json.dumps({"metricas": m, "repeticiones": repeticiones, "costo_usd": costo,
                    "modelo": modelo, "encajes": encajes, "humano": humano}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n" + md)
    print(f"\nCosto estimado: ${costo:.3f} · detalle → {salida.relative_to(config.RAIZ)}")
