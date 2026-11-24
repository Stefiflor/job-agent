<template>
  <section>
    <Topbar>
      <h1>Calidad del evaluador</h1>
      <p class="texto-2 sub">Cuánto coincide el agente con tu criterio, medido sobre ofertas que etiquetaste a mano.</p>
    </Topbar>

    <div v-if="cargando" class="vacio"><Loader2 class="girando" aria-hidden="true" />Cargando…</div>

    <template v-else>
      <!-- Los tres pasos del eval, con su estado. Siempre visibles: re-etiquetar o re-correr es parte del uso normal. -->
      <ol class="pasos">
        <li class="tarjeta paso" :class="{ hecho: total > 0 }">
          <span class="n" aria-hidden="true"><Check v-if="total > 0" /><template v-else>1</template></span>
          <div><strong>Elegir ofertas</strong><span class="texto-2">{{ total ? `${total} ofertas, repartidas entre los tres veredictos` : "25 ofertas ya evaluadas" }}</span></div>
        </li>
        <li class="tarjeta paso" :class="{ hecho: total > 0 && etiquetadas === total }">
          <span class="n" aria-hidden="true"><Check v-if="total > 0 && etiquetadas === total" /><template v-else>2</template></span>
          <div><strong>Etiquetar a ciegas</strong><span class="texto-2">{{ total ? `${etiquetadas} de ${total} etiquetadas` : "Vos decidís sin ver al agente" }}</span></div>
          <RouterLink to="/evals/etiquetar" class="btn btn-secundario">{{ total ? (etiquetadas ? "Seguir" : "Empezar") : "Preparar" }}</RouterLink>
        </li>
        <li class="tarjeta paso" :class="{ hecho: !!r && !corriendo }">
          <span class="n" aria-hidden="true">3</span>
          <div><strong>Correr los evals</strong><span class="texto-2">{{ etiquetadas ? `${etiquetadas * repeticiones} evaluaciones · ~US$ ${(etiquetadas * repeticiones * 0.07).toFixed(2)} de tu cupo` : "El agente evalúa las mismas ofertas" }}</span></div>
          <button v-if="!corriendo" class="btn btn-primario" :disabled="!etiquetadas" @click="correr"><Play aria-hidden="true" />Correr</button>
          <button v-else class="btn btn-secundario" @click="cortar?.()"><Square aria-hidden="true" />Detener</button>
        </li>
      </ol>

      <div v-if="corriendo || lineas.length" class="tarjeta corrida" aria-live="polite">
        <div class="c-cab">
          <strong>{{ corriendo ? "Evaluando…" : "Última corrida" }}</strong>
          <span class="texto-2">{{ progreso.n }} / {{ progreso.total }}</span>
        </div>
        <div class="barra"><span :style="{ width: progreso.total ? `${(progreso.n / progreso.total) * 100}%` : '0%' }"></span></div>
        <ul class="lineas">
          <li v-for="(l, i) in lineas.slice(-6).reverse()" :key="i">
            <component :is="l.modelo === l.humano ? CircleCheck : CircleX" :class="l.modelo === l.humano ? 'ok' : 'mal'" aria-hidden="true" />
            <span class="t">{{ l.titulo }}</span>
            <span class="texto-2">vos: {{ l.humano }} · agente: {{ l.modelo ?? "error" }}{{ l.encaje != null ? ` (${l.encaje})` : "" }}</span>
          </li>
        </ul>
      </div>
      <p v-if="error" class="error-caja"><TriangleAlert aria-hidden="true" />{{ error }}</p>

      <div v-if="!r" class="tarjeta vacio"><ChartNoAxesColumn aria-hidden="true" /><strong>Todavía no hay resultados</strong><span>Aparecen acá cuando termine la primera corrida.</span></div>
    </template>

    <template v-if="r && !cargando">
      <div class="stats">
        <div class="tarjeta stat"><span class="texto-2">Acuerdo con tu criterio</span><strong>{{ pct(r.metricas.acuerdo_exacto) }}</strong><div class="barra"><span :style="{ width: pct(r.metricas.acuerdo_exacto) }"></span></div></div>
        <div class="tarjeta stat"><span class="texto-2">Errores graves</span><strong :class="{ malo: r.metricas.errores_graves > .05 }">{{ pct(r.metricas.errores_graves) }}</strong><span class="texto-3 ayuda">Dice “aplicar” y era “descartar”, o al revés</span></div>
        <div class="tarjeta stat"><span class="texto-2">Consistencia</span><strong>{{ pct(r.metricas.consistencia) }}</strong><span class="texto-3 ayuda">Mismo veredicto en las {{ r.repeticiones }} corridas</span></div>
        <div class="tarjeta stat"><span class="texto-2">Variación del puntaje</span><strong>± {{ r.metricas.desvio_encaje_promedio.toFixed(1) }}</strong><span class="texto-3 ayuda">Puntos entre corridas de la misma oferta</span></div>
      </div>

      <div class="tarjeta matriz">
        <h2>Dónde se equivoca</h2>
        <p class="texto-2">Filas: tu veredicto. Columnas: lo que dijo el agente. La diagonal son los aciertos.</p>
        <table>
          <thead><tr><th></th><th v-for="v in V" :key="v">{{ v }}</th></tr></thead>
          <tbody>
            <tr v-for="h in V" :key="h">
              <th>{{ h }}</th>
              <td v-for="m in V" :key="m" :class="{ acierto: h === m, grave: grave(h, m) }" :style="{ '--a': intensidad(h, m) }">{{ r.metricas.confusion[`${h}→${m}`] ?? 0 }}</td>
            </tr>
          </tbody>
        </table>
        <p class="texto-3 pie">{{ r.metricas.ofertas }} ofertas · {{ r.metricas.evaluaciones }} evaluaciones · {{ r.archivo }}{{ r.costo_usd != null ? ` · US$ ${r.costo_usd.toFixed(2)}` : "" }}</p>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ChartNoAxesColumn, Check, CircleCheck, CircleX, Loader2, Play, Square, TriangleAlert } from "@lucide/vue";
import { api, escuchar, type ResultadoEvals } from "../api";
import Topbar from "../components/Topbar.vue";

const V = ["aplicar", "dudoso", "descartar"];
const repeticiones = 2;
const r = ref<ResultadoEvals | null>(null);
const cargando = ref(true);
const total = ref(0);
const etiquetadas = ref(0);
const corriendo = ref(false);
const progreso = ref({ n: 0, total: 0 });
const lineas = ref<{ titulo: string; humano: string; modelo: string | null; encaje: number | null }[]>([]);
const error = ref("");
let cortar: (() => void) | null = null;

const pct = (x: number) => `${Math.round(x * 100)}%`;
const grave = (h: string, m: string) => (h === "aplicar" && m === "descartar") || (h === "descartar" && m === "aplicar");
const maximo = computed(() => Math.max(1, ...Object.values(r.value?.metricas.confusion ?? {})));
const intensidad = (h: string, m: string) => (r.value?.metricas.confusion[`${h}→${m}`] ?? 0) / maximo.value;

async function cargar() {
  const [res, ets] = await Promise.allSettled([api.evals(), api.etiquetas()]);
  if (res.status === "fulfilled") r.value = res.value;
  if (ets.status === "fulfilled") { total.value = ets.value.length; etiquetadas.value = ets.value.filter((e) => e.tu_veredicto).length; }
}

function correr() {
  corriendo.value = true; lineas.value = []; error.value = "";
  progreso.value = { n: 0, total: etiquetadas.value * repeticiones };
  cortar = escuchar(`/evals/correr/stream?repeticiones=${repeticiones}`, (e) => {
    if (e.tipo === "progreso") { progreso.value = { n: e.n, total: e.total }; lineas.value.push(e); }
    if (e.tipo === "resultado") r.value = { archivo: e.archivo, metricas: e.metricas, repeticiones: e.repeticiones, costo_usd: e.costo_usd };
    if (e.tipo === "error") error.value = e.texto;
  }, () => { corriendo.value = false; });
}

onMounted(async () => { try { await cargar(); } finally { cargando.value = false; } });
</script>
<style scoped>
.pasos { list-style: none; margin: 0 0 1.1rem; padding: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }
.paso { display: flex; align-items: center; gap: .8rem; padding: 1rem 1.1rem; flex-wrap: wrap; }
.paso > div { flex: 1; min-width: 140px; display: flex; flex-direction: column; }
.paso .texto-2 { font-size: .84rem; }
.paso .n { width: 2rem; height: 2rem; border-radius: 50%; display: grid; place-items: center; flex: none; font-family: var(--f-titulo); font-weight: 600; background: var(--rosa-50); color: var(--rosa-600); }
.paso.hecho .n { background: var(--verde-50); color: var(--verde-700); }
.paso .n svg { width: 1rem; height: 1rem; }
.corrida { padding: 1.1rem 1.3rem; margin-bottom: 1.1rem; display: flex; flex-direction: column; gap: .7rem; }
.c-cab { display: flex; justify-content: space-between; }
.lineas { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .35rem; font-size: .88rem; }
.lineas li { display: flex; align-items: center; gap: .55rem; min-width: 0; }
.lineas svg { width: 1rem; height: 1rem; flex: none; }
.lineas .ok { color: var(--verde-700); }
.lineas .mal { color: var(--rojo); }
.lineas .t { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 40ch; }
@media (max-width: 1000px) { .pasos { grid-template-columns: 1fr; } }
.sub { margin-top: .25rem; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; margin-bottom: 1.1rem; }
.stat { padding: 1.1rem 1.2rem; display: flex; flex-direction: column; gap: .3rem; }
.stat strong { font-size: 1.8rem; font-family: var(--f-titulo); font-weight: 600; letter-spacing: 0; }
.stat strong.malo { color: var(--rojo); }
.ayuda { font-size: .8rem; }
.barra { height: .4rem; background: var(--verde-50); border-radius: 999px; overflow: hidden; }
.barra span { display: block; height: 100%; background: var(--verde-700); }
.matriz { padding: 1.4rem; }
.matriz p { font-size: .9rem; margin: .3rem 0 1rem; }
table { border-collapse: separate; border-spacing: 6px; }
th { font-weight: 700; font-size: .85rem; padding: .4rem .7rem; text-align: center; text-transform: capitalize; }
tbody th { text-align: right; }
td { width: 92px; height: 56px; text-align: center; font-family: var(--f-titulo); font-weight: 600; font-size: 1.1rem; border-radius: 12px; background: color-mix(in srgb, var(--naranja) calc(var(--a) * 35%), var(--superficie-2)); }
td.acierto { background: color-mix(in srgb, var(--verde-700) calc(var(--a) * 70% + 8%), var(--superficie-2)); color: var(--texto); }
td.grave { background: color-mix(in srgb, var(--rojo) calc(var(--a) * 60% + 6%), var(--superficie-2)); }
.pie { font-size: .82rem; margin-top: .8rem !important; }
@media (max-width: 900px) { .stats { grid-template-columns: 1fr 1fr; } }
</style>
