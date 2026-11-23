<template>
  <section>
    <div class="cab">
      <div><h1>Postulaciones</h1><p class="texto-2 sub">Gestioná tus postulaciones y su seguimiento.</p></div>
      <div class="toggle" role="tablist" aria-label="Vista">
        <button role="tab" :aria-selected="vista === 'lista'" :class="{ activo: vista === 'lista' }" @click="vista = 'lista'"><LayoutGrid aria-hidden="true" />Lista</button>
        <button role="tab" :aria-selected="vista === 'kanban'" :class="{ activo: vista === 'kanban' }" @click="vista = 'kanban'"><SquareKanban aria-hidden="true" />Kanban</button>
      </div>
    </div>
    <p v-if="error" class="error-caja"><TriangleAlert aria-hidden="true" />{{ error }}</p>

    <div v-if="!cargando && !items.length" class="tarjeta vacio">
      <Bookmark aria-hidden="true" /><strong>Todavía no guardaste ofertas</strong>
      <span>Guardalas desde Ofertas con el ícono de marcador, o dejá que el agente las guarde.</span>
      <RouterLink to="/ofertas" class="btn btn-primario">Ver ofertas</RouterLink>
    </div>

    <template v-else-if="vista === 'lista'">
      <div class="filtros">
        <label class="buscar"><Search aria-hidden="true" /><span class="solo-lector">Buscar</span><input v-model="texto" type="search" placeholder="Buscar por puesto o empresa…" /></label>
        <select v-model="etapa" aria-label="Etapa"><option value="">Todas las etapas</option><option v-for="e in ESTADOS" :key="e" :value="e">{{ nombreEtapa[e] }}</option></select>
        <select v-model="orden" aria-label="Orden"><option value="reciente">Más recientes</option><option value="encaje">Mayor encaje</option></select>
      </div>

      <div class="tarjeta tabla-env">
        <table>
          <thead><tr><th>Puesto</th><th>Empresa</th><th>Encaje</th><th>Etapa</th><th>Última acción</th><th>Próximo paso</th></tr></thead>
          <tbody>
            <tr v-for="t in filas" :key="t.id" :class="{ elegida: sel?.id === t.id }" tabindex="0" @click="selId = t.id" @keydown.enter="selId = t.id">
              <td><strong>{{ t.titulo }}</strong></td>
              <td class="texto-2">{{ t.empresa }}</td>
              <td><ScorePill v-if="t.encaje != null" :encaje="t.encaje" /><span v-else class="texto-3">—</span></td>
              <td><Etapa :estado="t.estado" /></td>
              <td class="texto-2">{{ formatoFecha(ultimaFecha(t)) }}</td>
              <td>{{ proximoPaso[t.estado] }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!filas.length" class="vacio chico">Ninguna postulación coincide con el filtro.</p>
      </div>

      <div v-if="sel" class="tarjeta seguimiento">
        <div class="seg-cab">
          <div><h2>Seguimiento</h2><p class="texto-2">{{ sel.titulo }} · {{ sel.empresa }}</p></div>
          <div class="acciones">
            <RouterLink :to="`/oferta/${sel.id}`" class="btn btn-secundario">Ver oferta</RouterLink>
            <button v-if="sel.estado !== 'descartada'" class="btn btn-secundario" @click="mover(sel, 'descartada')"><X aria-hidden="true" />Descartar</button>
            <button v-else class="btn btn-secundario" @click="mover(sel, 'para aplicar')"><RotateCcw aria-hidden="true" />Reactivar</button>
          </div>
        </div>
        <ol class="pasos">
          <li v-for="(p, i) in pasos" :key="p.id" :class="estadoPaso(i)">
            <button class="circulo" :disabled="!p.estado || sel.estado === 'descartada'" :aria-label="p.estado ? `Mover a ${p.texto}` : p.texto" @click="p.estado && mover(sel, p.estado)">
              <Check v-if="estadoPaso(i) === 'hecho'" aria-hidden="true" />
            </button>
            <strong>{{ p.texto }}</strong>
            <span class="texto-3">{{ fechaPaso(p) }}</span>
          </li>
        </ol>
        <p v-if="sel.estado === 'descartada'" class="texto-2 aviso">Esta postulación está descartada.</p>
        <label class="campo notas">Notas
          <textarea rows="2" :value="sel.notas ?? ''" placeholder="Ej.: mandé CV y carta; el contacto es…" @change="anotar(sel, ($event.target as HTMLTextAreaElement).value)"></textarea>
        </label>
      </div>
    </template>

    <div v-else class="kanban">
      <section v-for="e in ESTADOS" :key="e" class="columna" :aria-label="nombreEtapa[e]">
        <h2><Etapa :estado="e" /><span class="cuenta">{{ items.filter((t) => t.estado === e).length }}</span></h2>
        <article v-for="t in items.filter((x) => x.estado === e)" :key="t.id" class="tarjeta k-tarjeta">
          <div class="k-arriba"><Avatar :nombre="t.empresa" /><div class="k-nombres"><RouterLink :to="`/oferta/${t.id}`">{{ t.titulo }}</RouterLink><span class="texto-2">{{ t.empresa }}</span></div></div>
          <div class="k-pie"><ScorePill v-if="t.encaje != null" :encaje="t.encaje" />
            <select :value="t.estado" aria-label="Etapa" @change="mover(t, ($event.target as HTMLSelectElement).value as Estado)">
              <option v-for="x in ESTADOS" :key="x" :value="x">{{ nombreEtapa[x] }}</option>
            </select>
          </div>
        </article>
        <div v-if="!items.some((t) => t.estado === e)" class="hueco">Sin postulaciones</div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Bookmark, Check, LayoutGrid, RotateCcw, Search, SquareKanban, TriangleAlert, X } from "lucide-vue-next";
import { api, ESTADOS, formatoFecha, type Estado, type ItemTracker } from "../api";
import Avatar from "../components/Avatar.vue";
import Etapa from "../components/Etapa.vue";
import ScorePill from "../components/ScorePill.vue";

const items = ref<ItemTracker[]>([]);
const cargando = ref(true);
const error = ref("");
const vista = ref<"lista" | "kanban">("lista");
const texto = ref("");
const etapa = ref<Estado | "">("");
const orden = ref<"reciente" | "encaje">("reciente");
const selId = ref<string | null>(null);

const nombreEtapa: Record<Estado, string> = { "para aplicar": "Para aplicar", aplicada: "Aplicada", entrevista: "Entrevista", oferta: "Oferta", descartada: "Descartada" };
const proximoPaso: Record<Estado, string> = { "para aplicar": "Enviar postulación", aplicada: "Esperar respuesta", entrevista: "Preparar entrevista", oferta: "Revisar la oferta", descartada: "—" };
const ultimaFecha = (t: ItemTracker) => t.historial?.at(-1)?.fecha ?? t.fecha;

const filas = computed(() => {
  const q = texto.value.toLowerCase();
  const l = items.value.filter((t) => (!etapa.value || t.estado === etapa.value) && (!q || t.titulo.toLowerCase().includes(q) || t.empresa.toLowerCase().includes(q)));
  return l.sort((a, b) => (orden.value === "encaje" ? (b.encaje ?? -1) - (a.encaje ?? -1) : ultimaFecha(b).localeCompare(ultimaFecha(a))));
});
const sel = computed(() => items.value.find((t) => t.id === selId.value) ?? filas.value[0] ?? null);

// Seguimiento: "Evaluada" siempre está hecha (solo se guardan ofertas evaluadas); el resto sale del historial.
const pasos: { id: string; texto: string; estado: Estado | null }[] = [
  { id: "evaluada", texto: "Evaluada", estado: null },
  { id: "guardada", texto: "Guardada", estado: "para aplicar" },
  { id: "aplicada", texto: "Aplicada", estado: "aplicada" },
  { id: "entrevista", texto: "Entrevista", estado: "entrevista" },
  { id: "oferta", texto: "Oferta", estado: "oferta" },
];
const indiceActual = computed(() => {
  if (!sel.value) return 0;
  const i = pasos.findIndex((p) => p.estado === sel.value!.estado);
  return i === -1 ? ultimoAlcanzado.value : i;
});
const ultimoAlcanzado = computed(() => {
  const h = sel.value?.historial?.map((x) => x.estado).filter((e) => e !== "descartada") ?? [];
  return Math.max(1, ...h.map((e) => pasos.findIndex((p) => p.estado === e)));
});
const estadoPaso = (i: number) => (i < indiceActual.value || (i === indiceActual.value && i === 0) ? "hecho" : i === indiceActual.value ? (sel.value?.estado === "descartada" ? "hecho" : "actual") : "pendiente");
const fechaPaso = (p: (typeof pasos)[number]) => {
  if (!p.estado || !sel.value) return "";
  const h = [...(sel.value.historial ?? [{ estado: "para aplicar" as Estado, fecha: sel.value.fecha }])].reverse().find((x) => x.estado === p.estado);
  return h ? formatoFecha(h.fecha) : "";
};

async function guardar(t: ItemTracker, cambio: { estado?: Estado; notas?: string }) {
  const antes = { ...t, historial: [...(t.historial ?? [])] };
  try {
    const nuevo = await api.cambiarTracker(t.id, cambio);
    Object.assign(t, nuevo);
  } catch (e) { Object.assign(t, antes); error.value = `No se guardó el cambio: ${(e as Error).message}`; }
}
const mover = (t: ItemTracker, estado: Estado) => guardar(t, { estado });
const anotar = (t: ItemTracker, notas: string) => guardar(t, { notas });

onMounted(async () => {
  try { items.value = await api.tracker(); } catch (e) { error.value = (e as Error).message; }
  finally { cargando.value = false; }
});
</script>

<style scoped>
.cab { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1.6rem; flex-wrap: wrap; }
.sub { margin-top: .25rem; }
.toggle { display: flex; background: var(--superficie); border: 1px solid var(--borde); border-radius: 12px; padding: .25rem; box-shadow: var(--sombra); }
.toggle button { display: inline-flex; align-items: center; gap: .45rem; border: 0; background: none; padding: .5rem .95rem; border-radius: 9px; font-weight: 650; font-size: .88rem; cursor: pointer; color: var(--texto-2); }
.toggle button svg { width: 1rem; height: 1rem; }
.toggle button.activo { background: var(--grad-verde); color: #fff; }
.filtros { display: grid; grid-template-columns: 1fr 200px 200px; gap: .7rem; margin-bottom: 1rem; }
.buscar { position: relative; }
.buscar svg { position: absolute; left: .8rem; top: 50%; transform: translateY(-50%); width: 1rem; height: 1rem; color: var(--texto-3); }
.buscar input { padding-left: 2.3rem; }
.tabla-env { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th { text-align: left; font-weight: 700; padding: 1rem 1.2rem; border-bottom: 1px solid var(--borde); white-space: nowrap; }
td { padding: .85rem 1.2rem; border-bottom: 1px solid var(--borde); white-space: nowrap; }
tbody tr { cursor: pointer; }
tbody tr:hover { background: var(--superficie-2); }
tbody tr.elegida { background: var(--rosa-50); }
tbody tr:last-child td { border-bottom: 0; }
.chico { padding: 1.5rem; }
.seguimiento { margin-top: 1.2rem; padding: 1.4rem; display: flex; flex-direction: column; gap: 1.4rem; }
.seg-cab { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
.seg-cab p { font-size: .9rem; margin-top: .2rem; }
.acciones { display: flex; gap: .5rem; flex-wrap: wrap; }
.pasos { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(5, 1fr); }
.pasos li { position: relative; display: flex; flex-direction: column; align-items: center; gap: .35rem; text-align: center; }
.pasos li:not(:last-child)::after { content: ""; position: absolute; top: 1.05rem; left: calc(50% + 1.4rem); right: calc(-50% + 1.4rem); height: 2px; background: var(--borde-fuerte); }
.pasos li.hecho:not(:last-child)::after { background: var(--verde-700); }
.circulo { width: 2.2rem; height: 2.2rem; border-radius: 50%; border: 2px solid var(--borde-fuerte); background: var(--superficie); display: grid; place-items: center; cursor: pointer; color: #fff; }
.circulo:disabled { cursor: default; }
.circulo svg { width: 1.1rem; height: 1.1rem; }
.hecho .circulo { background: var(--verde-700); border-color: var(--verde-700); }
.actual .circulo { border-color: var(--rosa-600); border-width: 3px; box-shadow: 0 0 0 4px var(--rosa-50); }
.pendiente .circulo:not(:disabled):hover { border-color: var(--rosa); }
.pasos strong { font-size: .9rem; }
.pendiente strong { color: var(--texto-3); font-weight: 600; }
.pasos .texto-3 { font-size: .8rem; min-height: 1.2em; }
.aviso { font-size: .88rem; }
.notas { max-width: 640px; }
.kanban { display: grid; grid-template-columns: repeat(5, minmax(200px, 1fr)); gap: 1rem; overflow-x: auto; align-items: start; }
.columna { background: #f5edf0; border-radius: var(--r-l); padding: .8rem; display: flex; flex-direction: column; gap: .7rem; min-height: 180px; }
.columna h2 { display: flex; justify-content: space-between; align-items: center; font-size: .9rem; }
.cuenta { font-size: .78rem; background: var(--superficie); border-radius: 999px; padding: .05rem .5rem; color: var(--texto-2); }
.k-tarjeta { padding: .9rem; display: flex; flex-direction: column; gap: .7rem; }
.k-arriba { display: flex; gap: .6rem; }
.k-nombres { display: flex; flex-direction: column; min-width: 0; font-size: .85rem; }
.k-nombres a { color: var(--texto); font-weight: 700; font-size: .92rem; }
.k-pie { display: flex; gap: .5rem; align-items: center; }
.k-pie select { padding: .35rem .5rem; font-size: .82rem; }
.hueco { border: 2px dashed var(--borde-fuerte); border-radius: var(--r); padding: 1rem; text-align: center; color: var(--texto-3); font-size: .85rem; }
@media (max-width: 760px) { .filtros { grid-template-columns: 1fr; } .pasos { grid-template-columns: repeat(5, minmax(60px, 1fr)); font-size: .8rem; } }
</style>
