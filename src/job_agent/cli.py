"""Línea de comandos:  uv run job-agent buscar  |  uv run job-agent evaluar --limite 3"""

import argparse
import asyncio
import json
import time

from job_agent import config
from job_agent.evaluador import cargar_evaluadas, evaluar, guardar_evaluadas
from job_agent.filtros import filtrar
from job_agent.models import Candidata
from job_agent.sources.himalayas import buscar_roles


async def cmd_buscar(paginas: int) -> None:
    criterios = config.cargar_criterios()
    jobs = await buscar_roles(criterios.roles, paginas)
    candidatas, descartes = filtrar(jobs, criterios, ahora=time.time())

    config.CANDIDATAS.write_text(
        json.dumps([c.model_dump(mode="json") for c in candidatas], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nÚnicas encontradas: {len(jobs)}")
    print(f"Descartadas: {descartes}")
    print(f"Candidatas: {len(candidatas)} → {config.CANDIDATAS.relative_to(config.RAIZ)}\n")
    for c in candidatas[:15]:
        if c.salario_usd_mes:
            s = f"${c.salario_usd_mes.min}-{c.salario_usd_mes.max}/mes" + (" (por hora!)" if c.por_hora else "")
        else:
            s = "sin salario"
        paises = ", ".join(c.paises_validos[:3]) + (f" +{len(c.paises_validos) - 3}" if len(c.paises_validos) > 3 else "")
        print(f"- {c.titulo} | {c.empresa} | {s} | {paises}")


async def cmd_evaluar(limite: int, reevaluar: bool) -> None:
    criterios = config.cargar_criterios()
    cv = config.CV.read_text(encoding="utf-8")
    candidatas = [
        Candidata.model_validate(x)
        for x in json.loads(config.CANDIDATAS.read_text(encoding="utf-8"))
    ]

    evaluadas = [] if reevaluar else cargar_evaluadas(config.EVALUADAS)
    ya = {e.candidata.link for e in evaluadas}
    pendientes = [c for c in candidatas if c.link not in ya][:limite]
    print(f"{len(ya)} ya evaluadas (se saltean) · {len(pendientes)} por evaluar\n")

    costo_total = 0.0
    for i, c in enumerate(pendientes, 1):
        print(f"({i}/{len(pendientes)}) {c.titulo} | {c.empresa}")
        r = await evaluar(c, cv, criterios)
        if r is None:
            continue
        evaluadas.append(r)
        guardar_evaluadas(config.EVALUADAS, evaluadas)  # guarda después de cada una
        costo_total += r.costo_usd or 0
        e = r.evaluacion
        print(f"  → {e.veredicto} ({e.encaje}/100) · {e.tipo_puesto} · {e.resumen}")

    print(f"\nTotal evaluadas: {len(evaluadas)} → {config.EVALUADAS.relative_to(config.RAIZ)}")
    print(f"Costo estimado de esta corrida: ${costo_total:.3f} (con login de Claude sale del cupo Pro; con API key se cobra)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="job-agent")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_buscar = sub.add_parser("buscar", help="Busca en Himalayas y filtra")
    p_buscar.add_argument("--paginas", type=int, default=2)

    p_eval = sub.add_parser("evaluar", help="Evalúa las candidatas con Claude")
    p_eval.add_argument("--limite", type=int, default=3)
    p_eval.add_argument("--reevaluar", action="store_true", help="Ignora las ya evaluadas")

    args = parser.parse_args()
    if args.comando == "buscar":
        asyncio.run(cmd_buscar(args.paginas))
    else:
        asyncio.run(cmd_evaluar(args.limite, args.reevaluar))


if __name__ == "__main__":
    main()
