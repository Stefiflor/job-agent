// Cliente tipado de la API de Python. Los tipos reflejan los modelos de api.py.

export type Veredicto = "aplicar" | "dudoso" | "descartar";
export type Estado = "para aplicar" | "aplicada" | "entrevista" | "oferta" | "descartada";
export const ESTADOS: Estado[] = ["para aplicar", "aplicada", "entrevista", "oferta", "descartada"];

export interface Oferta {
  id: string;
  titulo: string;
  empresa: string;
  link: string;
  salario: { min: number; max: number } | null;
  por_hora: boolean;
  paises: string[];
  publicada: string | null;
  encaje: number;
  veredicto: Veredicto;
  tipo_puesto: string;
  elegible_ubicacion: string;
  resumen: string;
  red_flags: string[];
}

export interface Evaluacion {
  encaje: number;
  veredicto: Veredicto;
  tipo_puesto: string;
  elegible_ubicacion: string;
  salario_detectado: string;
  cumple: string[];
  falta: string[];
  red_flags: string[];
  resumen: string;
}

export interface DetalleOferta {
  id: string;
  candidata: { titulo: string; empresa: string; link: string; descripcion: string; tipo: string | null;
    salario_original: string; salario_usd_mes: { min: number; max: number } | null; por_hora: boolean;
    paises_validos: string[]; publicada: string | null };
  evaluacion: Evaluacion | null;
  en_tracker: boolean;
  carta_md: string | null;
}

export interface ItemTracker {
  id: string; fecha: string; estado: Estado; titulo: string; empresa: string;
  encaje: number | null; link: string; motivo: string; notas?: string;
  historial?: { estado: Estado; fecha: string }[];
}

export interface UltimaEjecucion { fecha: string; pedido: string; ofertas_analizadas: number; evaluaciones: number; costo_usd: number }

export interface ResultadoEvals {
  archivo: string; repeticiones: number; costo_usd: number | null;
  metricas: { ofertas: number; evaluaciones: number; acuerdo_exacto: number; errores_graves: number;
    consistencia: number; desvio_encaje_promedio: number; confusion: Record<string, number> };
}

export interface ItemEtiqueta {
  id: string; titulo: string; empresa: string; link: string;
  salario: { min: number; max: number } | null; por_hora: boolean; paises: string[]; publicada: string | null;
  descripcion: string; tu_veredicto: Veredicto | ""; tu_nota: string;
}

export interface Resumen {
  candidatas: number; evaluadas: number; por_veredicto: Partial<Record<Veredicto, number>>;
  costo_evaluaciones_usd: number; tracker: Record<Estado, number>;
}

export interface ResultadoCarta {
  verificada: boolean; intentos: number; costo_usd: number; carta: string | null;
  afirmaciones: { texto: string; fuentes: string[] }[];
  problemas: { afirmacion: string; motivo: string }[];
}

export interface ResultadoSemantico {
  id: string; titulo: string; empresa: string; link: string; similitud: number;
  pasa_filtros: boolean; motivo: string | null;
}

export function formatoFecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("es-AR", { day: "numeric", month: "short", year: "numeric" }).replace(".", "");
}

export function ubicacionCorta(paises: string[]): string {
  if (!paises.length || paises.includes("cualquiera")) return "Global";
  return paises.length > 2 ? `${paises.slice(0, 2).join(", ")} +${paises.length - 2}` : paises.join(", ");
}

export function formatoSalario(s: { min: number; max: number } | null | undefined, porHora = false): string {
  if (!s) return "sin salario";
  const k = (n: number) => `${(n / 1000).toFixed(1)}k`;
  return `US$ ${k(s.min)} – ${k(s.max)}/mes${porHora ? " (por hora)" : ""}`;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${ruta}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) {
    let detalle = r.statusText;
    try { detalle = (await r.json()).detail ?? detalle; } catch { /* respuesta sin JSON */ }
    throw new ApiError(r.status, typeof detalle === "string" ? detalle : JSON.stringify(detalle));
  }
  return r.json() as Promise<T>;
}

export const api = {
  resumen: () => pedir<Resumen>("/resumen"),
  ofertas: (p: { veredicto?: Veredicto; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v) as [string, string][]);
    return pedir<Oferta[]>(`/ofertas?${qs}`);
  },
  oferta: (id: string) => pedir<DetalleOferta>(`/ofertas/${id}`),
  buscar: () => pedir<{ encontradas: number; candidatas: number; descartes: Record<string, number> }>("/buscar", { method: "POST" }),
  carta: (id: string, idioma: "English" | "Spanish") =>
    pedir<ResultadoCarta>(`/ofertas/${id}/carta`, { method: "POST", body: JSON.stringify({ idioma }) }),
  tracker: () => pedir<ItemTracker[]>("/tracker"),
  agregarAlTracker: (id: string, motivo = "") =>
    pedir<ItemTracker>("/tracker", { method: "POST", body: JSON.stringify({ id, motivo }) }),
  cambiarTracker: (id: string, cambio: { estado?: Estado; notas?: string }) =>
    pedir<ItemTracker>(`/tracker/${id}`, { method: "PATCH", body: JSON.stringify(cambio) }),
  ultimaEjecucion: () => pedir<UltimaEjecucion | null>("/agente/ultima"),
  evals: () => pedir<ResultadoEvals | null>("/evals"),
  etiquetas: () => pedir<ItemEtiqueta[]>("/evals/etiquetas"),
  etiquetar: (id: string, veredicto: Veredicto | "", nota = "") =>
    pedir<unknown>(`/evals/etiquetas/${id}`, { method: "PUT", body: JSON.stringify({ veredicto, nota }) }),
  prepararEvals: (n = 25) => pedir<{ ofertas: number }>(`/evals/preparar?n=${n}`, { method: "POST" }),
  semantico: (q: string, todas = false) =>
    pedir<ResultadoSemantico[]>(`/rag/buscar?${new URLSearchParams({ q, todas: String(todas) })}`),
};

/** Abre un stream SSE. Devuelve una función para cortarlo. */
export function escuchar(ruta: string, alEvento: (e: any) => void, alTerminar: () => void): () => void {
  const fuente = new EventSource(`/api${ruta}`);
  fuente.onmessage = (m) => {
    const e = JSON.parse(m.data);
    alEvento(e);
    if (e.tipo === "fin" || e.tipo === "error") { fuente.close(); alTerminar(); }
  };
  // EventSource reintenta solo al cortarse; acá un corte significa que el servidor terminó o falló.
  fuente.onerror = () => { fuente.close(); alTerminar(); };
  return () => { fuente.close(); alTerminar(); };
}
