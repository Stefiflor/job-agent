<template>
  <section>
    <Topbar>
      <nav class="migas" aria-label="Ruta"><RouterLink to="/evals"><ArrowLeft aria-hidden="true" />Calidad</RouterLink><span>/</span><span>Etiquetar</span></nav>
      <h1>Etiquetá a ciegas</h1>
      <p class="texto-2 sub">Decidí como si te fueras a postular. No ves lo que dijo el agente, así tu criterio no se contamina.</p>
    </Topbar>

    <div v-if="cargando" class="vacio"><Loader2 class="girando" aria-hidden="true" />Cargando…</div>

    <div v-else-if="sinPreparar" class="tarjeta vacio">
      <Tags aria-hidden="true" />
      <strong>Todavía no hay ofertas para etiquetar</strong>
      <span>Se eligen 25 ofertas ya evaluadas, repartidas entre los tres veredictos.</span>
      <button class="btn btn-primario" :disabled="preparando" @click="preparar">
        <Loader2 v-if="preparando" class="girando" aria-hidden="true" />Preparar 25 ofertas
      </button>
      <p v-if="error" class="error-caja"><TriangleAlert aria-hidden="true" />{{ error }}</p>
    </div>

    <template v-else-if="actual">
      <div class="progreso">
        <div class="prog-txt"><strong>{{ etiquetadas }} de {{ items.length }}</strong><span class="texto-2">etiquetadas</span></div>
        <ol class="puntos" aria-label="Ofertas">
          <li v-for="(it, i) in items" :key="it.id">
            <button :class="[it.tu_veredicto || 'vacia', { actual: i === indice }]" :aria-label="`Oferta ${i + 1}: ${it.tu_veredicto || 'sin etiquetar'}`" :aria-current="i === indice" @click="ir(i)"></button>
          </li>
        </ol>
      </div>

      <div v-if="pendientes === 0" class="info-caja listo">
        <CircleCheck aria-hidden="true" />
        <span>Terminaste. Ahora el agente evalúa las mismas ofertas y se comparan los resultados.</span>
        <RouterLink to="/evals" class="btn btn-primario">Ir a correr los evals<ArrowRight aria-hidden="true" /></RouterLink>
      </div>

      <article class="tarjeta oferta">
        <header class="cab">
          <Avatar :nombre="actual.empresa" tam="grande" />
          <div class="nombres">
            <span class="texto-3 num">Oferta {{ indice + 1 }} de {{ items.length }}</span>
            <h2>{{ actual.titulo }}</h2>
            <span class="texto-2">{{ actual.empresa }}</span>
          </div>
          <a :href="actual.link" target="_blank" rel="noopener" class="btn btn-secundario">Aviso original<ExternalLink aria-hidden="true" /></a>
        </header>
        <div class="chips">
          <span class="chip"><Wallet aria-hidden="true" />{{ formatoSalario(actual.salario, actual.por_hora) }}</span>
          <span class="chip"><Globe aria-hidden="true" />{{ ubicacionCorta(actual.paises) }}</span>
          <span v-if="actual.publicada" class="chip"><CalendarDays aria-hidden="true" />{{ formatoFecha(actual.publicada) }}</span>
        </div>
        <div class="desc" tabindex="0" aria-label="Descripción de la oferta">{{ actual.descripcion || "Sin descripción: abrí el aviso original." }}</div>

        <footer class="decision">
          <p class="pregunta">¿Te postularías?</p>
          <div class="opciones" role="radiogroup" aria-label="Tu veredicto">
            <button v-for="(o, i) in opciones" :key="o.valor" role="radio" :aria-checked="actual.tu_veredicto === o.valor"
              class="opcion" :class="[o.valor, { elegida: actual.tu_veredicto === o.valor }]" :disabled="guardando" @click="elegir(o.valor)">
              <component :is="o.icono" aria-hidden="true" />
              <span><strong>{{ o.texto }}</strong><small>{{ o.ayuda }}</small></span>
              <kbd aria-hidden="true">{{ i + 1 }}</kbd>
            </button>
          </div>
          <label class="campo nota">Por qué (opcional)
            <input v-model="nota" type="text" placeholder="Ej.: pide 5 años de AWS · solo contrata en EE.UU." @change="guardarNota" />
          </label>
          <div class="nav">
            <button class="btn btn-secundario" :disabled="indice === 0" @click="ir(indice - 1)"><ArrowLeft aria-hidden="true" />Anterior</button>
            <button class="btn btn-secundario" title="Si el aviso venció o no se puede leer" @click="saltear">Saltear</button>
            <button class="btn btn-secundario" :disabled="indice === items.length - 1" @click="ir(indice + 1)">Siguiente<ArrowRight aria-hidden="true" /></button>
          </div>
          <p v-if="error" class="error-caja"><TriangleAlert aria-hidden="true" />{{ error }}</p>
        </footer>
      </article>
      <p class="atajos texto-3">Atajos: <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> para elegir · <kbd>←</kbd> <kbd>→</kbd> para moverte</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  ArrowLeft, ArrowRight, CalendarDays, CircleCheck, CircleHelp, CircleX, ExternalLink, Globe, Loader2, Tags,
  TriangleAlert, Wallet,
} from "@lucide/vue";
import { ApiError, api, formatoFecha, formatoSalario, ubicacionCorta, type ItemEtiqueta, type Veredicto } from "../api";
import Avatar from "../components/Avatar.vue";
import Topbar from "../components/Topbar.vue";

const opciones: { valor: Veredicto; texto: string; ayuda: string; icono: unknown }[] = [
  { valor: "aplicar", texto: "Aplicar", ayuda: "Me postulo hoy", icono: CircleCheck },
  { valor: "dudoso", texto: "Dudoso", ayuda: "Me interesa, pero algo no cierra", icono: CircleHelp },
  { valor: "descartar", texto: "Descartar", ayuda: "No me postularía", icono: CircleX },
];

const items = ref<ItemEtiqueta[]>([]);
const indice = ref(0);
const nota = ref("");
const cargando = ref(true);
const sinPreparar = ref(false);
const preparando = ref(false);
const guardando = ref(false);
const error = ref("");

const actual = computed(() => items.value[indice.value]);
const etiquetadas = computed(() => items.value.filter((i) => i.tu_veredicto).length);
const pendientes = computed(() => items.value.length - etiquetadas.value);
watch(actual, (a) => { nota.value = a?.tu_nota ?? ""; });

async function cargar() {
  cargando.value = true;
  try {
    items.value = await api.etiquetas();
    sinPreparar.value = false;
    const primera = items.value.findIndex((i) => !i.tu_veredicto);
    indice.value = primera === -1 ? 0 : primera;
    nota.value = actual.value?.tu_nota ?? "";
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) sinPreparar.value = true;
    else error.value = (e as Error).message;
  } finally { cargando.value = false; }
}

async function preparar() {
  preparando.value = true; error.value = "";
  try { await api.prepararEvals(25); await cargar(); }
  catch (e) { error.value = (e as Error).message; }
  finally { preparando.value = false; }
}

async function guardar(veredicto: Veredicto | "") {
  const it = actual.value;
  if (!it) return false;
  const antes = { v: it.tu_veredicto, n: it.tu_nota };
  it.tu_veredicto = veredicto; it.tu_nota = nota.value.trim(); // optimista: la UI no espera a la red
  guardando.value = true; error.value = "";
  try { await api.etiquetar(it.id, veredicto, it.tu_nota); return true; }
  catch (e) { it.tu_veredicto = antes.v; it.tu_nota = antes.n; error.value = `No se guardó: ${(e as Error).message}`; return false; }
  finally { guardando.value = false; }
}

/** Después de elegir, salta a la próxima sin etiquetar (o a la siguiente si ya no quedan). */
function avanzar() {
  const n = items.value.length;
  for (let k = 1; k <= n; k++) {
    const j = (indice.value + k) % n;
    if (!items.value[j].tu_veredicto) { indice.value = j; return; }
  }
  if (indice.value < n - 1) indice.value++;
}

async function elegir(v: Veredicto) { if (await guardar(v)) setTimeout(avanzar, 180); }
async function saltear() { if (await guardar("")) ir(Math.min(indice.value + 1, items.value.length - 1)); }
function guardarNota() { if (actual.value?.tu_veredicto) guardar(actual.value.tu_veredicto); }
function ir(i: number) { if (i >= 0 && i < items.value.length) indice.value = i; }

function teclas(e: KeyboardEvent) {
  const t = e.target as HTMLElement;
  if (t.closest("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey || guardando.value || !actual.value) return;
  const n = Number(e.key);
  if (n >= 1 && n <= 3) { e.preventDefault(); elegir(opciones[n - 1].valor); }
  else if (e.key === "ArrowRight") ir(indice.value + 1);
  else if (e.key === "ArrowLeft") ir(indice.value - 1);
}

onMounted(() => { cargar(); window.addEventListener("keydown", teclas); });
onBeforeUnmount(() => window.removeEventListener("keydown", teclas));
</script>

<style scoped>
.migas { display: flex; align-items: center; gap: .5rem; color: var(--texto-2); font-weight: 600; font-size: .88rem; margin-bottom: .6rem; }
.migas a { display: inline-flex; align-items: center; gap: .35rem; color: var(--texto-2); }
.migas svg { width: 1rem; height: 1rem; }
.sub { margin-top: .25rem; }
.vacio .btn { margin-top: .6rem; }
.vacio span { font-size: .9rem; max-width: 46ch; }

.progreso { display: flex; align-items: center; gap: 1.2rem; margin-bottom: 1rem; flex-wrap: wrap; }
.prog-txt { display: flex; align-items: baseline; gap: .4rem; }
.prog-txt strong { font-family: var(--f-titulo); font-weight: 600; font-size: 1.25rem; }
.puntos { list-style: none; display: flex; flex-wrap: wrap; gap: .35rem; margin: 0; padding: 0; }
.puntos button { width: 1.05rem; height: 1.05rem; border-radius: 50%; border: 2px solid var(--borde-fuerte); background: var(--superficie); cursor: pointer; padding: 0; }
.puntos .aplicar { background: var(--verde-700); border-color: var(--verde-700); }
.puntos .dudoso { background: var(--naranja); border-color: var(--naranja); }
.puntos .descartar { background: var(--rojo); border-color: var(--rojo); }
.puntos .actual { outline: 2px solid var(--rosa-600); outline-offset: 2px; }

.listo { margin-bottom: 1rem; flex-wrap: wrap; }
.listo span { flex: 1; min-width: 220px; }

.oferta { max-width: 920px; display: flex; flex-direction: column; }
.cab { display: flex; gap: 1rem; align-items: flex-start; padding: 1.4rem 1.4rem .8rem; }
.nombres { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: .15rem; }
.nombres h2 { font-size: 1.45rem; }
.num { font-size: .8rem; font-weight: 600; }
.chips { display: flex; flex-wrap: wrap; gap: .45rem; padding: 0 1.4rem 1rem; }
.chip svg { width: .9rem; height: .9rem; }
.desc { margin: 0 1.4rem; padding: 1rem 1.1rem; max-height: 38vh; overflow: auto; background: var(--superficie-2); border: 1px solid var(--borde); border-radius: var(--r); white-space: pre-line; font-size: .92rem; line-height: 1.65; color: var(--texto-2); }

.decision { padding: 1.2rem 1.4rem 1.4rem; display: flex; flex-direction: column; gap: .9rem; }
.pregunta { margin: 0; font-family: var(--f-titulo); font-weight: 600; font-size: 1.1rem; }
.opciones { display: grid; grid-template-columns: repeat(3, 1fr); gap: .7rem; }
.opcion { display: flex; align-items: center; gap: .7rem; text-align: left; padding: .9rem 1rem; border-radius: var(--r); border: 2px solid var(--borde-fuerte); background: var(--superficie); cursor: pointer; font: inherit; color: var(--texto); transition: border-color .15s, background .15s; }
.opcion > svg { width: 1.5rem; height: 1.5rem; flex: none; }
.opcion span { display: flex; flex-direction: column; flex: 1; }
.opcion small { color: var(--texto-2); font-size: .8rem; }
.opcion kbd { font-size: .75rem; color: var(--texto-3); border: 1px solid var(--borde-fuerte); border-radius: 6px; padding: .05rem .4rem; }
.opcion.aplicar > svg { color: var(--verde-700); }
.opcion.dudoso > svg { color: var(--naranja); }
.opcion.descartar > svg { color: var(--rojo); }
.opcion.aplicar:hover, .opcion.aplicar.elegida { border-color: var(--verde-700); background: var(--verde-50); }
.opcion.dudoso:hover, .opcion.dudoso.elegida { border-color: var(--naranja); background: var(--naranja-100); }
.opcion.descartar:hover, .opcion.descartar.elegida { border-color: var(--rojo); background: var(--rojo-100); }
.nota { max-width: 560px; }
.nav { display: flex; justify-content: space-between; gap: .6rem; }
.atajos { font-size: .82rem; margin-top: .8rem; }
.atajos kbd { font-family: var(--f); font-size: .75rem; border: 1px solid var(--borde-fuerte); border-radius: 6px; padding: 0 .35rem; background: var(--superficie); }
@media (max-width: 760px) {
  .opciones { grid-template-columns: 1fr; }
  .cab { flex-wrap: wrap; }
  .cab > .btn { flex-basis: 100%; justify-content: center; }
  .nav .btn { flex: 1; padding-inline: .5rem; justify-content: center; }
  .opcion kbd, .atajos { display: none; }
}
@media (prefers-reduced-motion: reduce) { .opcion { transition: none; } }
</style>
