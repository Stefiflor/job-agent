<template>
  <section>
    <Topbar>
      <h1>Ofertas</h1>
      <p class="texto-2 sub">Oportunidades evaluadas y ordenadas por encaje.</p>
    </Topbar>

    <p v-if="error" class="error-caja"><TriangleAlert aria-hidden="true" />{{ error }}</p>

    <div class="grilla">
      <aside class="tarjeta filtros" :class="{ cerrado: !filtrosAbiertos }" aria-label="Filtros">
        <div class="fila-tit"><h2><button type="button" class="plegar" :aria-expanded="filtrosAbiertos" @click="filtrosAbiertos = !filtrosAbiertos">Filtrar<ChevronDown aria-hidden="true" /></button><span class="solo-escritorio">Filtrar</span></h2><button class="limpiar" @click="limpiar">Limpiar</button></div>

        <div class="grupo">
          <label class="etiqueta" for="minimo">Encaje mínimo</label>
          <div class="slider"><input id="minimo" v-model.number="minimo" type="range" min="0" max="100" step="5" /><strong>≥ {{ minimo }}%</strong></div>
        </div>

        <fieldset class="grupo">
          <legend class="etiqueta">Tipo de puesto</legend>
          <label v-for="t in tipos" :key="t" class="check"><input v-model="tiposElegidos" type="checkbox" :value="t" />{{ t }}</label>
        </fieldset>

        <div class="grupo">
          <label class="etiqueta" for="ubicacion">Ubicación</label>
          <select id="ubicacion" v-model="ubicacion">
            <option value="">Cualquier país</option>
            <option value="Global">Global (sin restricción)</option>
            <option v-for="p in paises" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>

        <div class="grupo">
          <label class="etiqueta" for="salario">Salario</label>
          <select id="salario" v-model="salario">
            <option value="">Cualquiera</option>
            <option value="publicado">Con salario publicado</option>
            <option value="3000">Desde US$ 3.000/mes</option>
            <option value="5000">Desde US$ 5.000/mes</option>
          </select>
        </div>

        <RouterLink to="/busqueda" class="mas">Buscar por significado<ChevronRight aria-hidden="true" /></RouterLink>

        <div class="acciones">
          <button class="btn btn-secundario" :disabled="ocupado" @click="buscarNuevas"><RefreshCw :class="{ girando: accion === 'buscar' }" aria-hidden="true" />Buscar nuevas</button>
          <button class="btn btn-primario" :disabled="ocupado" @click="evaluarMas"><Sparkles aria-hidden="true" />Evaluar 5 más</button>
          <p v-if="progreso" class="progreso" role="status"><Loader2 v-if="ocupado" class="girando" aria-hidden="true" />{{ progreso }}</p>
        </div>
      </aside>

      <div class="tarjeta lista-panel">
        <div class="lista-cab">
          <div role="tablist" class="tabs" aria-label="Veredicto">
            <button v-for="op in opciones" :key="op.texto" role="tab" :aria-selected="filtro === op.valor" :class="{ activo: filtro === op.valor }" @click="filtro = op.valor">
              {{ op.texto }}<span class="cuenta">{{ contar(op.valor) }}</span>
            </button>
          </div>
          <label class="orden"><ArrowUpDown aria-hidden="true" /><span class="solo-lector">Ordenar</span>
            <select v-model="orden"><option value="encaje">Más relevantes</option><option value="salario">Mayor salario</option><option value="fecha">Más recientes</option></select>
          </label>
        </div>
        <p v-if="q" class="filtro-q">Resultados para “{{ q }}” <button class="limpiar" @click="$router.replace({ query: {} })">Quitar</button></p>

        <div v-if="cargando" class="vacio"><Loader2 class="girando" aria-hidden="true" />Cargando ofertas…</div>
        <div v-else-if="!visibles.length" class="vacio">
          <Inbox aria-hidden="true" />
          <strong>{{ ofertas.length ? "Ninguna oferta coincide" : "Todavía no hay ofertas evaluadas" }}</strong>
          <span>{{ ofertas.length ? "Ajustá los filtros o tocá Limpiar." : "Buscá ofertas nuevas y evaluá algunas." }}</span>
        </div>
        <ul v-else class="lista" role="listbox" aria-label="Ofertas">
          <li v-for="o in visibles" :key="o.id" role="option" :aria-selected="sel?.id === o.id"
              :class="{ elegida: sel?.id === o.id }" tabindex="0" @click="selId = o.id" @keydown.enter="selId = o.id" @dblclick="$router.push(`/oferta/${o.id}`)">
            <Avatar :nombre="o.empresa" />
            <div class="nombres">
              <strong>{{ o.titulo }}</strong>
              <span class="texto-2">{{ o.empresa }} · {{ ubicacionCorta(o.paises) }}</span>
            </div>
            <ScorePill :encaje="o.encaje" />
          </li>
        </ul>
      </div>

      <aside v-if="sel" class="tarjeta preview" aria-label="Vista previa">
        <div class="emp"><Avatar :nombre="sel.empresa" /><span>{{ sel.empresa }}</span></div>
        <h2>{{ sel.titulo }}</h2>
        <div class="chips">
          <span class="chip verde">Remoto</span>
          <span class="chip"><Globe aria-hidden="true" />{{ ubicacionCorta(sel.paises) }}</span>
          <span v-if="sel.red_flags.length" class="chip rojo"><TriangleAlert aria-hidden="true" />{{ sel.red_flags.length }} {{ sel.red_flags.length === 1 ? "alerta" : "alertas" }}</span>
        </div>
        <div class="encaje">
          <div class="fila-tit"><span class="etiqueta">Encaje con tu perfil</span><strong>{{ sel.encaje }}%</strong></div>
          <div class="barra" :class="tono(sel.encaje)"><span :style="{ width: `${sel.encaje}%` }"></span></div>
        </div>
        <p class="resumen">{{ sel.resumen }}</p>
        <p class="sal texto-2"><Wallet aria-hidden="true" />{{ formatoSalario(sel.salario, sel.por_hora) }}</p>
        <RouterLink :to="`/oferta/${sel.id}`" class="btn btn-primario ancho">Ver detalle completo<ArrowRight aria-hidden="true" /></RouterLink>
        <div class="dos">
          <button class="btn btn-secundario btn-icono" :aria-label="guardadas.has(sel.id) ? 'Ya está en postulaciones' : 'Guardar en postulaciones'" :disabled="guardadas.has(sel.id)" @click="guardar(sel)">
            <BookmarkCheck v-if="guardadas.has(sel.id)" aria-hidden="true" /><Bookmark v-else aria-hidden="true" />
          </button>
          <a class="btn btn-secundario" :href="sel.link" target="_blank" rel="noopener"><Send aria-hidden="true" />Aplicar</a>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  ArrowRight, ArrowUpDown, Bookmark, BookmarkCheck, ChevronDown, ChevronRight, Globe, Inbox, Loader2, RefreshCw, Send,
  Sparkles, TriangleAlert, Wallet,
} from "lucide-vue-next";
import { api, escuchar, formatoSalario, ubicacionCorta, type Oferta, type Veredicto } from "../api";
import Avatar from "../components/Avatar.vue";
import ScorePill from "../components/ScorePill.vue";
import Topbar from "../components/Topbar.vue";

const route = useRoute();
const ofertas = ref<Oferta[]>([]);
const guardadas = ref(new Set<string>());
const cargando = ref(true);
const error = ref("");
const filtro = ref<Veredicto | undefined>(undefined);
const minimo = ref(0);
const tiposElegidos = ref<string[]>([]);
const ubicacion = ref("");
const salario = ref("");
const orden = ref<"encaje" | "salario" | "fecha">("encaje");
const selId = ref<string | null>(null);
const filtrosAbiertos = ref(false); // en móvil arrancan plegados para que la lista se vea primero
const accion = ref<"" | "buscar" | "evaluar">("");
const ocupado = computed(() => accion.value !== "");
const progreso = ref("");
const q = computed(() => String(route.query.q ?? "").trim());

const opciones: { valor: Veredicto | undefined; texto: string }[] = [
  { valor: undefined, texto: "Todas" }, { valor: "aplicar", texto: "Para aplicar" },
  { valor: "dudoso", texto: "Dudosas" }, { valor: "descartar", texto: "Descartadas" },
];
const tipos = computed(() => [...new Set(ofertas.value.map((o) => o.tipo_puesto))].sort());
const paises = computed(() => [...new Set(ofertas.value.flatMap((o) => o.paises).filter((p) => p !== "cualquiera"))].sort());
const tono = (n: number) => (n >= 65 ? "alto" : n >= 40 ? "medio" : "bajo");

// Todos los filtros menos el de veredicto: así las cuentas de las pestañas reflejan el resto de los filtros.
const base = computed(() => {
  const t = q.value.toLowerCase();
  return ofertas.value.filter((o) =>
    o.encaje >= minimo.value
    && (!tiposElegidos.value.length || tiposElegidos.value.includes(o.tipo_puesto))
    && (!ubicacion.value || (ubicacion.value === "Global" ? o.paises.includes("cualquiera") : o.paises.includes(ubicacion.value)))
    && (!salario.value || (salario.value === "publicado" ? !!o.salario : (o.salario?.max ?? 0) >= Number(salario.value)))
    && (!t || o.titulo.toLowerCase().includes(t) || o.empresa.toLowerCase().includes(t)));
});
const contar = (v?: Veredicto) => base.value.filter((o) => !v || o.veredicto === v).length;
const visibles = computed(() => {
  const l = base.value.filter((o) => !filtro.value || o.veredicto === filtro.value);
  const clave = { encaje: (o: Oferta) => o.encaje, salario: (o: Oferta) => o.salario?.max ?? -1, fecha: (o: Oferta) => Date.parse(o.publicada ?? "") || 0 }[orden.value];
  return [...l].sort((a, b) => clave(b) - clave(a));
});
const sel = computed(() => visibles.value.find((o) => o.id === selId.value) ?? visibles.value[0] ?? null);
watch(visibles, (v) => { if (v.length && !v.some((o) => o.id === selId.value)) selId.value = v[0].id; });

function limpiar() { minimo.value = 0; tiposElegidos.value = []; ubicacion.value = ""; salario.value = ""; filtro.value = undefined; }

async function guardar(o: Oferta) {
  try { await api.agregarAlTracker(o.id, o.resumen); guardadas.value = new Set([...guardadas.value, o.id]); }
  catch (e) { error.value = (e as Error).message; }
}

async function cargar() {
  try {
    const [l, t] = await Promise.all([api.ofertas(), api.tracker()]);
    ofertas.value = l; guardadas.value = new Set(t.map((x) => x.id));
  } catch (e) { error.value = `No se pudo conectar con la API (${(e as Error).message}). Levantala con "uv run job-agent api".`; }
  finally { cargando.value = false; }
}

async function buscarNuevas() {
  accion.value = "buscar"; progreso.value = "Buscando en Himalayas…";
  try { const r = await api.buscar(); progreso.value = `${r.encontradas} encontradas, ${r.candidatas} pasan tus filtros. Evaluá para verlas.`; }
  catch (e) { error.value = (e as Error).message; progreso.value = ""; }
  finally { accion.value = ""; }
}

function evaluarMas() {
  accion.value = "evaluar"; progreso.value = "Preparando…";
  escuchar("/evaluar/stream?limite=5", (e) => {
    if (e.tipo === "inicio") progreso.value = e.pendientes ? `Evaluando ${e.pendientes} ofertas…` : "No hay ofertas sin evaluar.";
    if (e.tipo === "evaluada") { progreso.value = `${e.n} de ${e.total}: ${e.oferta.titulo}`; ofertas.value = [...ofertas.value, e.oferta]; }
    if (e.tipo === "fin") progreso.value = `Listo · US$ ${e.costo_usd}`;
    if (e.tipo === "error") error.value = e.texto;
  }, () => { accion.value = ""; });
}

onMounted(cargar);
</script>

<style scoped>
.sub { margin-top: .25rem; }
.grilla { display: grid; grid-template-columns: 240px minmax(0, 1fr) 320px; gap: 1.1rem; align-items: start; }
.filtros { padding: 1.2rem; display: flex; flex-direction: column; gap: 1.3rem; position: sticky; top: 1rem; }
.fila-tit { display: flex; justify-content: space-between; align-items: center; }
.limpiar { border: 0; background: none; color: var(--texto-2); font-weight: 600; font-size: .85rem; cursor: pointer; }
.limpiar:hover { color: var(--rosa-600); }
.grupo { display: flex; flex-direction: column; gap: .55rem; border: 0; padding: 0; margin: 0; }
.etiqueta { font-weight: 700; font-size: .88rem; color: var(--texto); }
.slider { display: flex; align-items: center; gap: .7rem; }
.slider strong { font-size: .85rem; white-space: nowrap; }
.check { display: flex; align-items: center; gap: .55rem; font-size: .88rem; font-weight: 500; cursor: pointer; }
.mas { display: flex; justify-content: space-between; align-items: center; font-weight: 700; font-size: .88rem; color: var(--texto); }
.mas svg { width: 1rem; height: 1rem; }
.mas:hover { color: var(--rosa-600); }
.acciones { display: flex; flex-direction: column; gap: .5rem; border-top: 1px solid var(--borde); padding-top: 1.1rem; }
.progreso { display: flex; gap: .4rem; align-items: center; font-size: .82rem; color: var(--verde-700); font-weight: 600; }
.progreso svg { width: .95rem; height: .95rem; flex: none; }
.lista-panel { overflow: hidden; }
.lista-cab { display: flex; justify-content: space-between; align-items: center; gap: .8rem; padding: 1rem 1.1rem; flex-wrap: wrap; border-bottom: 1px solid var(--borde); }
.tabs { display: flex; gap: .3rem; flex-wrap: wrap; }
.tabs button { border: 1px solid var(--borde-fuerte); background: var(--superficie); border-radius: 999px; padding: .35rem .75rem; font-weight: 650; font-size: .82rem; cursor: pointer; display: inline-flex; gap: .35rem; align-items: center; color: var(--texto-2); }
.tabs button.activo { background: var(--grad-verde); border-color: var(--verde-800); color: #fff; }
.cuenta { font-size: .72rem; background: var(--superficie-2); color: var(--texto-2); border-radius: 999px; padding: 0 .4rem; }
.activo .cuenta { background: rgba(255, 255, 255, .2); color: #fff; }
.orden { display: flex; align-items: center; gap: .3rem; color: var(--texto-2); }
.orden svg { width: .95rem; height: .95rem; }
.orden select { border: 0; padding: .3rem; font-weight: 650; font-size: .85rem; width: auto; background: transparent; box-shadow: none !important; }
.filtro-q { padding: .6rem 1.1rem; background: var(--rosa-50); font-size: .88rem; font-weight: 600; display: flex; justify-content: space-between; }
.lista { list-style: none; margin: 0; padding: .4rem; }
.lista li { display: flex; align-items: center; gap: .9rem; padding: .95rem .9rem; border-radius: var(--r); cursor: pointer; }
.lista li + li { margin-top: .15rem; }
.lista li:hover { background: var(--superficie-2); }
.lista li.elegida { background: var(--rosa-50); box-shadow: inset 0 0 0 1px var(--rosa-100); }
.nombres { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.nombres strong { font-size: .95rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nombres span { font-size: .84rem; }
.vacio span { font-size: .9rem; }
.preview { padding: 1.3rem; display: flex; flex-direction: column; gap: .9rem; position: sticky; top: 1rem; }
.emp { display: flex; align-items: center; gap: .7rem; font-weight: 600; color: var(--texto-2); }
.preview h2 { font-size: 1.4rem; font-family: var(--f-titulo); font-weight: 600; letter-spacing: 0; }
.chips { display: flex; gap: .35rem; flex-wrap: wrap; }
.encaje { display: flex; flex-direction: column; gap: .5rem; }
.barra { height: .4rem; background: var(--verde-50); border-radius: 999px; overflow: hidden; }
.barra span { display: block; height: 100%; border-radius: 999px; background: var(--verde-700); transition: width .5s; }
.barra.medio span { background: var(--naranja); } .barra.bajo span { background: var(--rojo); }
.resumen { font-size: .88rem; color: var(--texto-2); }
.sal { display: flex; gap: .4rem; align-items: center; font-size: .85rem; font-weight: 600; }
.sal svg { width: 1rem; height: 1rem; }
.ancho { width: 100%; }
.dos { display: grid; grid-template-columns: auto 1fr; gap: .5rem; }
@media (max-width: 1180px) { .grilla { grid-template-columns: 220px minmax(0, 1fr); } .preview { grid-column: 1 / -1; position: static; } }
@media (max-width: 760px) { .grilla { grid-template-columns: 1fr; } .filtros { position: static; } .filtros.cerrado > :not(.fila-tit) { display: none; } .plegar { display: inline-flex !important; } .solo-escritorio { display: none; } }
.plegar { display: none; align-items: center; gap: .4rem; background: none; border: 0; padding: 0; font: inherit; color: inherit; cursor: pointer; }
.plegar svg { width: 1.1rem; height: 1.1rem; transition: transform .2s; }
.plegar[aria-expanded="true"] svg { transform: rotate(180deg); }
</style>
