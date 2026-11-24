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
from typing import AsyncIterator

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


def preparar(n: int) -> int:
    """Arma el dataset y el CSV vacío. ValueError si ya existen o si no alcanzan las evaluadas."""
    if ETIQUETAS.exists():
        raise ValueError(f"Ya existe {ETIQUETAS.relative_to(config.RAIZ)}. Borralo si querés empezar de nuevo.")
    evaluadas = cargar_evaluadas(config.EVALUADAS) if config.EVALUADAS.exists() else []
    if len(evaluadas) < n:
        raise ValueError(f"Hay {len(evaluadas)} ofertas evaluadas y hacen falta {n}: evaluá más ofertas primero.")
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
    return len(dataset)


# --- Métricas (funciones puras, testeadas) -----------------------------------

COLUMNAS = ["id", "titulo", "empresa", "link", "tu_veredicto", "tu_nota"]


def leer_filas(ruta: Path | None = None) -> list[dict]:
    ruta = ruta or ETIQUETAS  # se resuelve al llamar, no al definir la función
    # utf-8-sig y delimitador detectado: Excel en español guarda con BOM y con ";".
    texto = ruta.read_text(encoding="utf-8-sig")
    dialecto = csv.Sniffer().sniff(texto.splitlines()[0], delimiters=",;\t")
    return list(csv.DictReader(texto.splitlines(), dialect=dialecto))


def leer_etiquetas(ruta: Path | None = None) -> dict[str, str]:
    etiquetas = {}
    for fila in leer_filas(ruta):
        v = (fila.get("tu_veredicto") or "").strip().lower()
        if v:
            if v not in ORDEN:
                raise ValueError(f"{fila['id']}: '{v}' no es válido. Usá aplicar / dudoso / descartar.")
            etiquetas[fila["id"]] = v
    return etiquetas


def guardar_etiqueta(oid: str, veredicto: str, nota: str = "", ruta: Path | None = None) -> dict:
    """Actualiza una fila del CSV. Veredicto vacío = sin etiquetar (por ej. oferta vencida)."""
    ruta = ruta or ETIQUETAS
    if veredicto and veredicto not in ORDEN:
        raise ValueError(f"'{veredicto}' no es válido.")
    filas = leer_filas(ruta)
    fila = next((f for f in filas if f["id"] == oid), None)
    if fila is None:
        raise KeyError(oid)
    fila["tu_veredicto"], fila["tu_nota"] = veredicto, nota.strip()
    tmp = ruta.with_suffix(".tmp")  # escritura atómica: un corte no deja el CSV a medias
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    tmp.replace(ruta)
    return fila


def para_etiquetar() -> list[dict]:
    """Las ofertas del dataset con tu etiqueta. Nunca incluye el veredicto del modelo:
    verlo antes de decidir sesga la etiqueta y el eval deja de medir algo."""
    filas = {f["id"]: f for f in leer_filas()}
    items = []
    for d in json.loads(DATASET.read_text(encoding="utf-8")):
        c, f = d["candidata"], filas.get(d["id"], {})
        items.append({
            "id": d["id"], "titulo": c["titulo"], "empresa": c["empresa"], "link": c["link"],
            "salario": c.get("salario_usd_mes"), "por_hora": c.get("por_hora", False),
            "paises": c.get("paises_validos", []), "publicada": c.get("publicada"),
            "descripcion": c.get("descripcion", ""),
            "tu_veredicto": (f.get("tu_veredicto") or "").strip().lower(), "tu_nota": f.get("tu_nota") or "",
        })
    return items


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

async def eventos_correr(repeticiones: int) -> AsyncIterator[dict]:
    """Evalúa cada oferta etiquetada N veces. Emite 'progreso' por evaluación, 'resultado' y 'fin'."""
    humano = leer_etiquetas()
    if not humano:
        raise ValueError("No hay etiquetas: etiquetá al menos una oferta.")
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
                yield {"tipo": "progreso", "n": n, "total": total, "id": oid, "titulo": dataset[oid].titulo,
                       "humano": humano[oid], "modelo": None, "encaje": None}
                continue
            modelo.setdefault(oid, []).append(r.evaluacion.veredicto)
            encajes.setdefault(oid, []).append(r.evaluacion.encaje)
            costo += r.costo_usd or 0
            yield {"tipo": "progreso", "n": n, "total": total, "id": oid, "titulo": dataset[oid].titulo,
                   "humano": humano[oid], "modelo": r.evaluacion.veredicto, "encaje": r.evaluacion.encaje}

    m = metricas(humano, modelo, encajes)
    sello = datetime.now().strftime("%Y-%m-%d_%H%M")
    salida = DIR_EVALS / f"resultado-{sello}.json"
    salida.write_text(
        json.dumps({"metricas": m, "repeticiones": repeticiones, "costo_usd": costo,
                    "modelo": modelo, "encajes": encajes, "humano": humano}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    yield {"tipo": "resultado", "metricas": m, "repeticiones": repeticiones, "costo_usd": costo, "archivo": salida.name}
    yield {"tipo": "fin"}


async def correr(repeticiones: int) -> None:
    async for e in eventos_correr(repeticiones):
        if e["tipo"] == "progreso":
            print(f"({e['n']}/{e['total']}) {e['id']}: vos={e['humano']} modelo={e['modelo']} ({e['encaje']})")
        elif e["tipo"] == "resultado":
            print("\n" + informe_markdown(e["metricas"], e["repeticiones"]))
            print(f"\nCosto estimado: ${e['costo_usd']:.3f} · detalle → private/evals/{e['archivo']}")
