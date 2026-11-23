"""Línea de comandos:  uv run job-agent buscar | evaluar --limite 3 | agente "pedido" """

import argparse
import asyncio
import json
import time

from job_agent import agente, config, evals
from job_agent.sources import himalayas
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


async def cmd_rag_indexar(feed: int, recrear: bool) -> None:
    from job_agent import vectores
    from job_agent.embeddings import Model2VecEmbedder

    criterios = config.cargar_criterios()
    print("Buscando por roles...")
    jobs = await buscar_roles(criterios.roles, 2)
    if feed:
        print(f"Recorriendo el feed general ({feed} páginas)...")
        jobs += await himalayas.feed(feed)
    emb = Model2VecEmbedder()
    print(f"Calculando embeddings con {emb.nombre}...")
    with vectores.conectar() as conn:
        vectores.crear_esquema(conn, emb.dim, recrear)
        stats = vectores.indexar(conn, jobs, emb, criterios, ahora=time.time())
        total, pasan = vectores.contar(conn)
    print(f"Esta corrida: {stats}. En el índice: {total} ofertas, {pasan} pasan tus filtros.")


def _imprimir_resultados(resultados) -> None:
    for r in resultados:
        extra = "" if r.pasa_filtros else f"  [no pasa filtros: {r.motivo}]"
        print(f"{r.similitud:.2f} | {r.titulo} | {r.empresa}{extra}\n      {r.link}")


def cmd_rag_buscar(consulta: str, k: int, todas: bool) -> None:
    from job_agent import vectores
    from job_agent.embeddings import Model2VecEmbedder

    with vectores.conectar() as conn:
        _imprimir_resultados(vectores.buscar(conn, Model2VecEmbedder(), consulta, k, solo_filtradas=not todas))


def cmd_rag_similares(link: str, k: int, todas: bool) -> None:
    from job_agent import vectores

    with vectores.conectar() as conn:
        _imprimir_resultados(vectores.similares(conn, link, k, solo_filtradas=not todas))


def _buscar_candidata(link: str) -> Candidata | None:
    for ruta, clave in ((config.EVALUADAS, "candidata"), (config.CANDIDATAS, None)):
        if ruta.exists():
            for x in json.loads(ruta.read_text(encoding="utf-8")):
                c = x[clave] if clave else x
                if c["link"].split("?")[0] == link.split("?")[0]:
                    return Candidata.model_validate(c)
    return None


async def cmd_carta(link: str, idioma: str) -> None:
    from job_agent import carta
    from job_agent.embeddings import Model2VecEmbedder

    c = _buscar_candidata(link)
    if c is None:
        raise SystemExit("No encontré esa oferta en candidatas ni evaluadas. Corré `buscar` primero.")
    if not carta.EXPERIENCIA.exists():
        raise SystemExit(f"Falta {carta.EXPERIENCIA.relative_to(config.RAIZ)}: es la única fuente de la carta.")
    fragmentos = carta.fragmentar(carta.EXPERIENCIA.read_text(encoding="utf-8"))
    print(f"{c.titulo} | {c.empresa} · {len(fragmentos)} fragmentos de experiencia")
    r = await carta.generar(c, fragmentos, Model2VecEmbedder(), idioma, config.cargar_criterios().nombre)
    ruta = carta.guardar(c, r)
    if r.borrador:
        print("\n" + r.borrador.carta + "\n")
    ok = r.verificacion and r.verificacion.respaldada
    print(f"{'✓ verificada' if ok else '⚠ con problemas: revisala antes de enviar'} · intentos: {r.intentos} · costo ${r.costo_usd:.3f}")
    if not ok and r.verificacion:
        for p in r.verificacion.problemas:
            print(f"  - {p.afirmacion}: {p.motivo}")
    print(f"→ {ruta}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="job-agent")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_buscar = sub.add_parser("buscar", help="Busca en Himalayas y filtra")
    p_buscar.add_argument("--paginas", type=int, default=2)

    p_eval = sub.add_parser("evaluar", help="Evalúa las candidatas con Claude")
    p_eval.add_argument("--limite", type=int, default=3)
    p_eval.add_argument("--reevaluar", action="store_true", help="Ignora las ya evaluadas")

    p_agente = sub.add_parser("agente", help="El agente decide qué buscar y evaluar")
    p_agente.add_argument("pedido", nargs="?", default="Buscame trabajos remotos de AI Engineer o full stack con IA.")
    p_agente.add_argument("--objetivo", type=int, default=5, help="Ofertas 'aplicar' a encontrar")
    p_agente.add_argument("--max-evaluaciones", type=int, default=8, help="Presupuesto de evaluaciones nuevas")

    p_evals = sub.add_parser("evals", help="Mide el evaluador contra tus etiquetas")
    sub_evals = p_evals.add_subparsers(dest="accion", required=True)
    p_prep = sub_evals.add_parser("preparar", help="Arma el CSV para etiquetar")
    p_prep.add_argument("--n", type=int, default=25)
    p_corr = sub_evals.add_parser("correr", help="Evalúa y calcula métricas")
    p_corr.add_argument("--repeticiones", type=int, default=2)

    p_rag = sub.add_parser("rag", help="Índice semántico de ofertas (pgvector)")
    sub_rag = p_rag.add_subparsers(dest="accion_rag", required=True)
    p_idx = sub_rag.add_parser("indexar", help="Busca ofertas y las indexa")
    p_idx.add_argument("--feed", type=int, default=10, help="Páginas de 20 del feed general (la API no da más por página)")
    p_idx.add_argument("--recrear", action="store_true", help="Borra el índice (si cambiaste de modelo)")
    p_bus = sub_rag.add_parser("buscar", help="Búsqueda semántica en lenguaje natural")
    p_bus.add_argument("consulta")
    p_bus.add_argument("--k", type=int, default=10)
    p_bus.add_argument("--todas", action="store_true", help="Incluye las que no pasan tus filtros")
    p_sim = sub_rag.add_parser("similares", help="Ofertas parecidas a una (por link)")
    p_sim.add_argument("link")
    p_sim.add_argument("--k", type=int, default=10)
    p_sim.add_argument("--todas", action="store_true")

    p_api = sub.add_parser("api", help="Levanta la API + la UI en http://127.0.0.1:8000")
    p_api.add_argument("--port", type=int, default=8000)
    p_api.add_argument("--reload", action="store_true", help="Recarga al cambiar el código (desarrollo)")

    p_carta = sub.add_parser("carta", help="Carta de presentación con RAG y verificación")
    p_carta.add_argument("link", help="Link de la oferta (de evaluadas o candidatas)")
    p_carta.add_argument("--idioma", default="English", help="English o Spanish")

    args = parser.parse_args()
    if args.comando == "buscar":
        asyncio.run(cmd_buscar(args.paginas))
    elif args.comando == "evaluar":
        asyncio.run(cmd_evaluar(args.limite, args.reevaluar))
    elif args.comando == "agente":
        asyncio.run(agente.correr(args.pedido, args.objetivo, args.max_evaluaciones))
    elif args.comando == "api":
        import uvicorn

        # 127.0.0.1: solo accesible desde tu máquina (la API no tiene auth y gasta cupo).
        uvicorn.run("job_agent.api:app", host="127.0.0.1", port=args.port, reload=args.reload)
    elif args.comando == "carta":
        asyncio.run(cmd_carta(args.link, args.idioma))
    elif args.comando == "rag":
        if args.accion_rag == "indexar":
            asyncio.run(cmd_rag_indexar(args.feed, args.recrear))
        elif args.accion_rag == "buscar":
            cmd_rag_buscar(args.consulta, args.k, args.todas)
        else:
            cmd_rag_similares(args.link, args.k, args.todas)
    elif args.accion == "preparar":
        evals.preparar(args.n)
    else:
        asyncio.run(evals.correr(args.repeticiones))


if __name__ == "__main__":
    main()
