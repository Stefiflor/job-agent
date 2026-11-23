<template>
  <section>
    <Topbar><span class="marca">job-agent</span></Topbar>

    <div class="hero">
      <div class="texto">
        <p class="eyebrow"><BadgeCheck aria-hidden="true" />Agente inteligente</p>
        <h1>Tu búsqueda laboral,<br />en piloto automático.</h1>
        <p class="bajada">El agente encuentra, analiza y prioriza oportunidades según tu perfil, experiencia y objetivos.</p>
      </div>
      <svg class="formas" viewBox="0 0 320 240" aria-hidden="true">
        <defs>
          <linearGradient id="g-rosa" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fbd3e0" /><stop offset="1" stop-color="#f4a6c0" /></linearGradient>
          <linearGradient id="g-verde" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1a7a4f" /><stop offset="1" stop-color="#0b3a2c" /></linearGradient>
        </defs>
        <path d="M70 40C120 0 200 10 225 60S190 190 120 200 20 170 25 120 40 65 70 40Z" fill="url(#g-rosa)" opacity=".9" />
        <path d="M150 230C120 150 170 70 250 50s80 40 60 110-60 85-100 85-50-5-60-15Z" fill="url(#g-verde)" />
      </svg>
    </div>

    <form class="prompt" @submit.prevent="correr()">
      <Sparkles class="chispa" aria-hidden="true" />
      <label class="solo-lector" for="pedido">¿Qué tipo de trabajo querés encontrar?</label>
      <input id="pedido" ref="entrada" v-model="pedido" type="text" placeholder="¿Qué tipo de trabajo querés encontrar?" />
      <button class="enviar" :disabled="!pedido.trim()" aria-label="Correr el agente"><Play aria-hidden="true" /></button>
    </form>
    <div class="sugerencias">
      <button v-for="s in sugerencias" :key="s.texto" type="button" class="sugerencia" @click="correr(s.pedido)">{{ s.texto }}</button>
      <button type="button" class="sugerencia mas" aria-label="Escribir otro pedido" @click="entrada?.focus()"><Plus aria-hidden="true" /></button>
    </div>

    <div class="tarjeta ejecucion">
      <span class="punto" :class="{ apagado: !ultima }" aria-hidden="true"></span>
      <div class="detalle">
        <strong>{{ ultima ? "Ejecución reciente" : "Todavía no corriste el agente" }}</strong>
        <span v-if="ultima" class="texto-2">
          {{ ultima.ofertas_analizadas }} ofertas analizadas · {{ ultima.evaluaciones }} evaluaciones · US$ {{ ultima.costo_usd.toFixed(3) }} · {{ formatoFecha(ultima.fecha) }}
        </span>
        <span v-else class="texto-2">Escribí qué buscás arriba y el agente arranca.</span>
      </div>
      <RouterLink v-if="ultima" to="/agente" class="btn btn-secundario">Ver actividad<ArrowRight aria-hidden="true" /></RouterLink>
    </div>

    <div class="stats">
      <RouterLink to="/ofertas" class="tarjeta stat">
        <span class="icono rosa"><Search aria-hidden="true" /></span>
        <div><strong>{{ resumen?.candidatas ?? "–" }}</strong><span>Descubiertas</span></div>
      </RouterLink>
      <RouterLink to="/ofertas" class="tarjeta stat">
        <span class="icono verde"><Check aria-hidden="true" /></span>
        <div><strong>{{ resumen?.por_veredicto.aplicar ?? 0 }}</strong><span>Para aplicar</span></div>
      </RouterLink>
      <RouterLink to="/tracker" class="tarjeta stat">
        <span class="icono naranja"><Send aria-hidden="true" /></span>
        <div><strong>{{ enCurso }}</strong><span>En curso</span></div>
      </RouterLink>
      <div class="tarjeta stat">
        <span class="icono rosa"><Layers aria-hidden="true" /></span>
        <div><strong>{{ resumen ? `US$ ${costoTotal}` : "–" }}</strong><span>Costo total</span></div>
      </div>
    </div>
    <p v-if="error" class="error-caja"><TriangleAlert aria-hidden="true" />{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowRight, BadgeCheck, Check, Layers, Play, Plus, Search, Send, Sparkles, TriangleAlert } from "@lucide/vue";
import { api, formatoFecha, type Resumen, type UltimaEjecucion } from "../api";
import Topbar from "../components/Topbar.vue";

const router = useRouter();
const pedido = ref("");
const entrada = ref<HTMLInputElement | null>(null);
const resumen = ref<Resumen | null>(null);
const ultima = ref<UltimaEjecucion | null>(null);
const error = ref("");
const sugerencias = [
  { texto: "AI Engineer remoto", pedido: "Buscame trabajos remotos de AI Engineer." },
  { texto: "Roles con LLM", pedido: "Buscame roles donde construya productos con LLMs y agentes." },
  { texto: "Trabajo en Europa", pedido: "Buscame trabajos remotos para Europa en AI o full stack." },
];
const enCurso = computed(() => (resumen.value ? resumen.value.tracker.aplicada + resumen.value.tracker.entrevista + resumen.value.tracker.oferta : "–"));
const costoTotal = computed(() => ((resumen.value?.costo_evaluaciones_usd ?? 0) + (ultima.value?.costo_usd ?? 0)).toFixed(2));

function correr(texto?: string) {
  const p = (texto ?? pedido.value).trim();
  if (p) router.push({ path: "/agente", query: { pedido: p, auto: "1" } });
}

onMounted(async () => {
  try { [resumen.value, ultima.value] = await Promise.all([api.resumen(), api.ultimaEjecucion()]); }
  catch (e) { error.value = `No se pudo conectar con la API (${(e as Error).message}). Levantala con "uv run job-agent api".`; }
});
</script>

<style scoped>
.marca { font-family: var(--f-titulo); font-weight: 600; font-size: 1.35rem; letter-spacing: 0; }
.hero { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 1.2rem; }
.eyebrow { display: inline-flex; align-items: center; gap: .4rem; color: var(--rosa-600); font-weight: 750; font-size: .78rem; letter-spacing: .12em; text-transform: uppercase; margin-bottom: .9rem; }
.eyebrow svg { width: 1rem; height: 1rem; }
h1 { font-size: clamp(2rem, 4.2vw, 3.1rem); font-family: var(--f-titulo); font-weight: 600; letter-spacing: 0; line-height: 1.05; }
.bajada { margin-top: .9rem; font-size: 1.05rem; color: var(--texto-2); max-width: 46ch; }
.formas { width: min(340px, 38%); flex: none; }
.prompt { display: flex; align-items: center; gap: .8rem; background: var(--superficie); border: 1px solid var(--borde); border-radius: 999px; padding: .45rem .45rem .45rem 1.3rem; box-shadow: var(--sombra-alta); max-width: 820px; }
.prompt:focus-within { border-color: var(--rosa); box-shadow: 0 0 0 4px var(--rosa-50), var(--sombra-alta); }
.chispa { width: 1.4rem; height: 1.4rem; color: var(--rosa-600); flex: none; }
.prompt input { border: 0; box-shadow: none !important; font-size: 1.05rem; padding: .7rem 0; background: transparent; }
.enviar { width: 3rem; height: 3rem; border-radius: 50%; border: 0; background: var(--grad-verde); color: #fff; display: grid; place-items: center; cursor: pointer; flex: none; }
.enviar:hover:not(:disabled) { background: var(--grad-verde-hover); }
.enviar:disabled { opacity: .45; cursor: not-allowed; }
.enviar svg { width: 1.15rem; height: 1.15rem; margin-left: 2px; }
.sugerencias { display: flex; gap: .6rem; flex-wrap: wrap; margin: 1rem 0 1.6rem; }
.sugerencia { background: var(--superficie); border: 1px solid var(--borde-fuerte); border-radius: 999px; padding: .5rem 1.1rem; font-weight: 600; font-size: .88rem; cursor: pointer; }
.sugerencia:hover { border-color: var(--rosa); color: var(--rosa-600); }
.sugerencia.mas { padding: .5rem .75rem; display: grid; place-items: center; }
.sugerencia.mas svg { width: 1rem; height: 1rem; }
.ejecucion { display: flex; align-items: center; gap: 1rem; padding: 1.1rem 1.3rem; max-width: 820px; margin-bottom: 1.2rem; }
.punto { width: .6rem; height: .6rem; border-radius: 50%; background: #22c55e; box-shadow: 0 0 0 4px #dcfce7; flex: none; }
.punto.apagado { background: var(--texto-3); box-shadow: none; }
.detalle { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.detalle .texto-2 { font-size: .88rem; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; max-width: 820px; }
.stat { display: flex; align-items: center; gap: .9rem; padding: 1.1rem 1.2rem; color: inherit; transition: box-shadow .15s, transform .15s; }
a.stat:hover { box-shadow: var(--sombra-alta); transform: translateY(-1px); }
.stat div { display: flex; flex-direction: column; }
.stat strong { font-size: 1.55rem; font-family: var(--f-titulo); font-weight: 600; letter-spacing: 0; line-height: 1.1; }
.stat span:not(.icono) { font-size: .85rem; color: var(--texto-2); }
.icono { width: 2.8rem; height: 2.8rem; border-radius: 13px; display: grid; place-items: center; flex: none; }
.icono svg { width: 1.3rem; height: 1.3rem; }
.icono.rosa { background: var(--rosa-50); color: var(--rosa-600); }
.icono.verde { background: var(--verde-50); color: var(--verde-600); }
.icono.naranja { background: var(--naranja-100); color: var(--naranja); }
.error-caja { margin-top: 1rem; max-width: 820px; }
@media (max-width: 900px) { .stats { grid-template-columns: 1fr 1fr; } .formas { display: none; } }
</style>
