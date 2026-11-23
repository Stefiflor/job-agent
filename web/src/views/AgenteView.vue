<template>
  <section>
    <Topbar>
      <h1>Agente</h1>
      <p class="texto-2 sub">Decide solo qué buscar, qué leer y qué evaluar. El presupuesto lo hace cumplir el código.</p>
    </Topbar>

    <div class="layout">
      <form class="tarjeta config" @submit.prevent="correr">
        <h2><Sparkles aria-hidden="true" />Objetivo</h2>
        <label class="campo">Qué buscás<textarea v-model="pedido" rows="4" required></textarea></label>
        <div class="dos">
          <label class="campo">Ofertas para aplicar<input v-model.number="objetivo" type="number" min="1" max="10" /></label>
          <label class="campo">Evaluaciones máx.<input v-model.number="presupuesto" type="number" min="0" max="20" /></label>
        </div>
        <p class="nota texto-3"><Info aria-hidden="true" />Cada evaluación cuesta ~US$ 0,06 de tu cupo.</p>
        <button v-if="!corriendo" class="btn btn-primario"><Play aria-hidden="true" />Correr agente</button>
        <button v-else type="button" class="btn btn-secundario" @click="cortar?.()"><Square aria-hidden="true" />Detener</button>
      </form>

      <div class="tarjeta actividad">
        <div class="act-cab">
          <h2>Actividad</h2>
          <span v-if="corriendo" class="vivo"><span class="latido"></span>En vivo</span>
          <span v-else-if="fin" class="chip verde"><Check aria-hidden="true" />Terminado</span>
        </div>
        <div v-if="!pasos.length && !corriendo" class="vacio">
          <Bot aria-hidden="true" /><strong>El agente está listo</strong><span>Definí el objetivo y corrélo: vas a ver cada paso acá.</span>
        </div>
        <ol v-else class="timeline" aria-live="polite">
          <li v-for="(p, i) in pasos" :key="i" :class="p.tipo">
            <span class="nodo" aria-hidden="true"><component :is="iconoDe(p)" /></span>
            <div class="cuerpo">
              <template v-if="p.tipo === 'herramienta'"><strong>{{ nombres[p.nombre] ?? p.nombre }}</strong><span v-if="detalle(p)" class="texto-2">{{ detalle(p) }}</span></template>
              <span v-else :class="{ 'texto-2': p.tipo === 'pensamiento' }">{{ p.texto }}</span>
            </div>
          </li>
          <li v-if="corriendo" class="pensando"><span class="nodo"><Loader2 class="girando" aria-hidden="true" /></span><span class="texto-3">Pensando…</span></li>
        </ol>
      </div>
    </div>

    <div v-if="fin" class="stats">
      <div class="tarjeta stat"><span class="texto-2">Turnos</span><strong>{{ fin.turnos }}</strong></div>
      <div class="tarjeta stat"><span class="texto-2">Evaluaciones usadas</span><strong>{{ fin.evaluaciones_nuevas }} / {{ fin.max_evaluaciones }}</strong></div>
      <div class="tarjeta stat"><span class="texto-2">Costo total</span><strong>US$ {{ (fin.costo_agente_usd + fin.costo_evaluaciones_usd).toFixed(3) }}</strong></div>
    </div>

    <section v-if="informe" class="resultado">
      <h2>Lo que encontró</h2>
      <div class="ranking">
        <article v-for="(r, i) in informe.ranking" :key="r.id" class="tarjeta r-tarjeta">
          <div class="r-arriba"><span class="puesto">#{{ i + 1 }}</span><ScorePill :encaje="r.encaje" /></div>
          <div class="r-emp"><Avatar :nombre="r.empresa" /><div><h3>{{ r.titulo }}</h3><span class="texto-2">{{ r.empresa }}</span></div></div>
          <p class="porque">{{ r.por_que }}</p>
          <a v-if="r.link" :href="r.link" target="_blank" rel="noopener" class="btn btn-secundario">Ver aviso<ExternalLink aria-hidden="true" /></a>
        </article>
      </div>
      <div class="tarjeta como"><h3>Cómo buscó</h3><p class="texto-2">{{ informe.resumen }}</p></div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  BookmarkPlus, Bot, Check, ExternalLink, FileText, Gauge, Info, Lightbulb, Loader2, Play, ScanSearch, Search,
  Sparkles, Square, TriangleAlert,
} from "@lucide/vue";
import { escuchar } from "../api";
import Avatar from "../components/Avatar.vue";
import ScorePill from "../components/ScorePill.vue";
import Topbar from "../components/Topbar.vue";

const route = useRoute();
const pedido = ref(String(route.query.pedido ?? "Buscame trabajos remotos de AI Engineer con agentes LLM."));
const objetivo = ref(3);
const presupuesto = ref(5);
const corriendo = ref(false);
const pasos = ref<any[]>([]);
interface ItemRanking { id: string; titulo: string; empresa: string; encaje: number; por_que: string; link?: string }
const informe = ref<{ ranking: ItemRanking[]; resumen: string } | null>(null);
const fin = ref<any>(null);
let cortar: (() => void) | null = null;

const nombres: Record<string, string> = {
  buscar_ofertas: "Buscó por palabra clave", buscar_semantico: "Buscó por significado", ver_oferta: "Leyó una oferta",
  evaluar_oferta: "Evaluó el encaje", guardar_en_tracker: "Guardó en postulaciones",
};
const iconos: Record<string, any> = { buscar_ofertas: Search, buscar_semantico: ScanSearch, ver_oferta: FileText, evaluar_oferta: Gauge, guardar_en_tracker: BookmarkPlus };
const iconoDe = (p: any) => (p.tipo === "herramienta" ? iconos[p.nombre] ?? Bot : p.tipo === "error" ? TriangleAlert : Lightbulb);
const detalle = (p: any) => { const i = p.input ?? {}; return i.consulta ? `“${i.consulta}”` : i.motivo ? i.motivo : i.id ? `Oferta ${i.id}` : ""; };

function correr() {
  corriendo.value = true; pasos.value = []; informe.value = null; fin.value = null;
  const qs = new URLSearchParams({ pedido: pedido.value, objetivo: String(objetivo.value), max_evaluaciones: String(presupuesto.value) });
  cortar = escuchar(`/agente/stream?${qs}`, (e) => {
    if (["herramienta", "pensamiento", "error"].includes(e.tipo)) pasos.value.push(e);
    if (e.tipo === "informe") informe.value = e;
    if (e.tipo === "fin") fin.value = e;
  }, () => { corriendo.value = false; });
}

// Desde Inicio se llega con ?auto=1: arranca solo con el pedido que escribiste ahí.
onMounted(() => { if (route.query.auto === "1") correr(); });
</script>

<style scoped>
.sub { margin-top: .25rem; }
.layout { display: grid; grid-template-columns: minmax(280px, 360px) 1fr; gap: 1.1rem; align-items: start; }
.config { padding: 1.3rem; display: flex; flex-direction: column; gap: 1rem; }
.config h2, .act-cab h2 { display: flex; align-items: center; gap: .5rem; }
.config h2 svg { width: 1.15rem; height: 1.15rem; color: var(--rosa-600); }
.dos { display: grid; grid-template-columns: 1fr 1fr; gap: .7rem; }
.nota { display: flex; align-items: center; gap: .4rem; font-size: .82rem; }
.nota svg { width: .95rem; height: .95rem; }
.actividad { padding: 1.3rem; min-height: 340px; }
.act-cab { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.1rem; }
.vivo { display: inline-flex; align-items: center; gap: .45rem; font-size: .82rem; font-weight: 700; color: var(--rosa-600); }
.latido { width: .5rem; height: .5rem; border-radius: 50%; background: var(--rosa); animation: latido 1.2s ease-in-out infinite; }
@keyframes latido { 50% { opacity: .3; } }
.vacio span { font-size: .9rem; }
.timeline { list-style: none; margin: 0; padding: 0; }
.timeline li { display: flex; gap: .85rem; padding-bottom: 1rem; position: relative; }
.timeline li:not(:last-child)::before { content: ""; position: absolute; left: 1.05rem; top: 2.3rem; bottom: .15rem; width: 2px; background: var(--borde); }
.nodo { width: 2.15rem; height: 2.15rem; border-radius: 50%; display: grid; place-items: center; flex: none; background: var(--verde-50); color: var(--verde-700); }
.nodo svg { width: 1rem; height: 1rem; }
.pensamiento .nodo, .pensando .nodo { background: var(--rosa-50); color: var(--rosa-600); }
.error .nodo { background: var(--rojo-100); color: var(--rojo); }
.cuerpo { display: flex; flex-direction: column; padding-top: .35rem; min-width: 0; }
.cuerpo .texto-2 { font-size: .9rem; overflow-wrap: anywhere; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-top: 1.1rem; }
.stat { padding: 1rem 1.2rem; display: flex; flex-direction: column; }
.stat strong { font-size: 1.4rem; font-family: var(--f-titulo); font-weight: 600; letter-spacing: 0; }
.resultado { margin-top: 1.6rem; display: flex; flex-direction: column; gap: 1rem; }
.ranking { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
.r-tarjeta { padding: 1.2rem; display: flex; flex-direction: column; gap: .7rem; }
.r-arriba { display: flex; justify-content: space-between; align-items: center; }
.puesto { font-family: var(--f-titulo); font-weight: 600; color: var(--rosa-600); }
.r-emp { display: flex; gap: .7rem; align-items: flex-start; }
.r-emp span { font-size: .85rem; }
.porque { font-size: .88rem; color: var(--texto-2); flex: 1; }
.r-tarjeta .btn { align-self: flex-start; }
.como { padding: 1.2rem 1.3rem; }
.como p { margin-top: .4rem; white-space: pre-line; max-width: 90ch; }
@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .stats { grid-template-columns: 1fr; } }
</style>
