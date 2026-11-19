"""Cliente de la API pública de Himalayas (sin key). Búsqueda: 20 resultados por página."""

import asyncio

import httpx

from job_agent.models import Job

URL_BUSQUEDA = "https://himalayas.app/jobs/api/search"
POR_PAGINA = 20
PAUSA_SEG = 1.0  # cortesía con la API


async def buscar(client: httpx.AsyncClient, consulta: str, paginas: int = 2) -> list[Job]:
    jobs: list[Job] = []
    for pagina in range(1, paginas + 1):
        resp = await client.get(URL_BUSQUEDA, params={"q": consulta, "page": pagina})
        resp.raise_for_status()
        lote = [Job.model_validate(j) for j in resp.json().get("jobs", [])]
        jobs.extend(lote)
        print(f'  "{consulta}" página {pagina}: {len(lote)}')
        if len(lote) < POR_PAGINA:
            break
        await asyncio.sleep(PAUSA_SEG)
    return jobs


async def buscar_roles(roles: list[str], paginas: int = 2) -> list[Job]:
    """Busca cada rol y elimina duplicados por guid (una oferta aparece en varios roles)."""
    vistas: dict[str, Job] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        for rol in roles:
            for job in await buscar(client, rol, paginas):
                vistas[job.guid] = job
    return list(vistas.values())
