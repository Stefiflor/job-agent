<template>
  <section>
    <Topbar>
      <h1>Calidad del evaluador</h1>
      <p class="texto-2 sub">Cuánto coincide el agente con tu criterio, medido sobre ofertas que etiquetaste a mano.</p>
    </Topbar>

    <div v-if="cargando" class="vacio"><Loader2 class="girando" aria-hidden="true" />Cargando…</div>
    <div v-else-if="!r" class="tarjeta vacio pasos-vacio">
      <ChartNoAxesColumn aria-hidden="true" />
      <strong>Todavía no hay resultados de evals</strong>
      <span>Así se generan, desde la terminal:</span>
      <ol>
        <li><code>uv run job-agent evals preparar --n 25</code></li>
        <li>Completá <code>tu_veredicto</code> en <code>private/evals/etiquetas.csv</code></li>
        <li><code>uv run job-agent evals correr --repeticiones 2</code></li>
      </ol>
    </div>

    <template v-else>
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
import { ChartNoAxesColumn, Loader2 } from "lucide-vue-next";
import { api, type ResultadoEvals } from "../api";
import Topbar from "../components/Topbar.vue";

const V = ["aplicar", "dudoso", "descartar"];
const r = ref<ResultadoEvals | null>(null);
const cargando = ref(true);
const pct = (x: number) => `${Math.round(x * 100)}%`;
const grave = (h: string, m: string) => (h === "aplicar" && m === "descartar") || (h === "descartar" && m === "aplicar");
const maximo = computed(() => Math.max(1, ...Object.values(r.value?.metricas.confusion ?? {})));
const intensidad = (h: string, m: string) => (r.value?.metricas.confusion[`${h}→${m}`] ?? 0) / maximo.value;
onMounted(async () => { try { r.value = await api.evals(); } finally { cargando.value = false; } });
</script>

<style scoped>
.sub { margin-top: .25rem; }
.pasos-vacio ol { text-align: left; display: grid; gap: .4rem; margin: .4rem 0 0; }
code { background: var(--superficie-2); border: 1px solid var(--borde); border-radius: 6px; padding: .1rem .35rem; font-size: .85rem; }
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
