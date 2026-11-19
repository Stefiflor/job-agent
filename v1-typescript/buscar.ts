import { readFile, writeFile } from "node:fs/promises";

type Job = {
  title: string; companyName: string; employmentType: string;
  minSalary: number | null; maxSalary: number | null;
  salaryPeriod: string; currency: string | null; seniority: string[];
  locationRestrictions: string[]; timezoneRestrictions: number[];
  description: string; pubDate: number; expiryDate: number;
  applicationLink: string; guid: string;
};

const criterios = JSON.parse(await readFile("private/criterios.json", "utf8"));
const PAGINAS_POR_ROL = 2;
const HORAS_MES = 160;
const MIN_CHARS_DESC = 500;

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

function salarioUSDMes(j: Job) {
  if (j.currency !== "USD" || (j.minSalary == null && j.maxSalary == null)) return null;
  const factor = { annual: 1 / 12, monthly: 1, hourly: HORAS_MES }[j.salaryPeriod];
  if (factor == null) return null;
  const min = (j.minSalary ?? j.maxSalary!) * factor;
  const max = (j.maxSalary ?? j.minSalary!) * factor;
  return { min: Math.round(min), max: Math.round(max) };
}

function zonaOK(j: Job) {
  const tz = j.timezoneRestrictions ?? [];
  if (tz.length === 0) return true;
  const { minUTC, maxUTC, toleranciaHoras = 0 } = criterios.zonaHoraria;
  return tz.some(z => z >= minUTC - toleranciaHoras && z <= maxUTC + toleranciaHoras);
}

function paisesValidos(j: Job): string[] | null {
  const p = j.locationRestrictions ?? [];
  if (p.length === 0) return ["cualquiera"];
  const ok = p.filter(x => criterios.paisesResidencia.includes(x));
  return ok.length ? ok : null;
}

function seniorityExcluida(j: Job) {
  return (j.seniority ?? []).some(s => criterios.excluirSeniority.includes(s))
    || /\bintern(ship)?\b/i.test(j.title);
}

function limpiarHtml(html: string) {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">").replace(/&#39;/g, "'").replace(/&quot;/g, '"')
    .replace(/\s+/g, " ").trim();
}

// 1. Buscar
const vistas = new Map<string, Job>();
for (const rol of criterios.roles) {
  for (let page = 1; page <= PAGINAS_POR_ROL; page++) {
    const url = `https://himalayas.app/jobs/api/search?q=${encodeURIComponent(rol)}&page=${page}`;
    const res = await fetch(url);
    if (!res.ok) { console.warn(`HTTP ${res.status} en ${url}`); break; }
    const data = await res.json();
    const jobs: Job[] = data.jobs ?? [];
    for (const j of jobs) vistas.set(j.guid, j);
    console.log(`"${rol}" página ${page}: ${jobs.length}`);
    if (jobs.length < 20) break;
    await sleep(1000);
  }
}

// 2. Filtrar
const ahora = Date.now() / 1000;
const descartes = { vencida: 0, zonaHoraria: 0, pais: 0, seniority: 0, salarioBajo: 0, descVacia: 0 };
const candidatas = [];

for (const j of vistas.values()) {
  if (j.expiryDate && j.expiryDate < ahora) { descartes.vencida++; continue; }
  if (!zonaOK(j)) { descartes.zonaHoraria++; continue; }
  const paises = paisesValidos(j);
  if (!paises) { descartes.pais++; continue; }
  if (seniorityExcluida(j)) { descartes.seniority++; continue; }
  const sal = salarioUSDMes(j);
  if (sal && sal.max < criterios.salarioMinimoUSDMes) { descartes.salarioBajo++; continue; }
  const texto = limpiarHtml(j.description ?? "");
  if (texto.length < MIN_CHARS_DESC) { descartes.descVacia++; continue; }

  candidatas.push({
    titulo: j.title,
    empresa: j.companyName,
    tipo: j.employmentType,
    seniority: j.seniority,
    salarioUSDMes: sal,
    salarioOriginal: sal ? `${j.minSalary}-${j.maxSalary} ${j.currency}/${j.salaryPeriod}` : "sin dato",
    porHora: j.salaryPeriod === "hourly" && sal != null,
    paisesValidos: paises,
    publicada: new Date(j.pubDate * 1000).toISOString().slice(0, 10),
    link: j.applicationLink,
    descripcion: texto,
  });
}

// 3. Ordenar y guardar
candidatas.sort((a, b) => (b.salarioUSDMes?.max ?? -1) - (a.salarioUSDMes?.max ?? -1));
await writeFile("private/candidatas.json", JSON.stringify(candidatas, null, 2));

// 4. Resumen
console.log("\nÚnicas encontradas:", vistas.size);
console.log("Descartadas:", descartes);
console.log("Candidatas:", candidatas.length, "→ private/candidatas.json\n");
for (const c of candidatas.slice(0, 15)) {
  const s = c.salarioUSDMes ? `$${c.salarioUSDMes.min}-${c.salarioUSDMes.max}/mes${c.porHora ? " (por hora!)" : ""}` : "sin salario";
  console.log(`- ${c.titulo} | ${c.empresa} | ${s} | ${c.paisesValidos.join(", ")}`);
}
