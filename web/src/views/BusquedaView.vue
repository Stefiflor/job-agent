<template>
  <section>
    <Topbar>
      <nav class="migas" aria-label="Ruta"><RouterLink to="/ofertas"><ArrowLeft aria-hidden="true" />Ofertas</RouterLink><span>/</span><span>Búsqueda semántica</span></nav>
      <h1>Buscar por significado</h1>
      <p class="texto-2 sub">Describí el trabajo con tus palabras: encuentra ofertas aunque no usen los mismos términos.</p>
    </Topbar>

    <form class="prompt" @submit.prevent="buscar">
      <ScanSearch class="chispa" aria-hidden="true" />
      <label class="solo-lector" for="consulta">Qué trabajo buscás</label>
      <input id="consulta" v-model="consulta" type="text" placeholder="Ej.: construir agentes que llamen APIs para atención al cliente" />
      <button class="enviar" :disabled="buscando || !consulta.trim()" aria-label="Buscar"><Loader2 v-if="buscando" class="girando" aria-hidden="true" /><ArrowRight v-else aria-hidden="true" /></button>
    </form>
    <div class="opciones">
      <button v-for="e in ejemplos" :key="e" type="button" class="sugerencia" @click="consulta = e; buscar()">{{ e }}</button>
      <label class="check"><input v-model="todas" type="checkbox" />Incluir las que no pasan mis filtros</label>
    </div>

    <p v-if="error" class="error-caja"><TriangleAlert aria-hidden="true" />{{ error }}</p>
    <div v-if="resultados.length" class="tarjeta">
      <div class="r-cab"><h2>{{ resultados.length }} resultados</h2><span class="texto-3">por similitud</span></div>
      <ul class="lista">
        <li v-for="r in resultados" :key="r.id">
          <Avatar :nombre="r.empresa" />
          <div class="nombres">
            <a :href="r.link" target="_blank" rel="noopener">{{ r.titulo }}</a>
            <span class="texto-2">{{ r.empresa }}</span>
            <span v-if="!r.pasa_filtros" class="chip rojo">No pasa tus filtros: {{ r.motivo }}</span>
          </div>
          <div class="sim"><div class="barra"><span :style="{ width: `${Math.max(0, r.similitud) * 100}%` }"></span></div><strong>{{ Math.round(r.similitud * 100) }}%</strong></div>
        </li>
      </ul>
    </div>
    <div v-else-if="buscado && !error" class="tarjeta vacio"><SearchX aria-hidden="true" /><strong>Sin resultados</strong><span>Indexá más ofertas con “uv run job-agent rag indexar”.</span></div>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ArrowLeft, ArrowRight, Loader2, ScanSearch, SearchX, TriangleAlert } from "lucide-vue-next";
import { api, type ResultadoSemantico } from "../api";
import Avatar from "../components/Avatar.vue";
import Topbar from "../components/Topbar.vue";

const ejemplos = ["Agentes LLM para atención al cliente", "Frontend Vue con IA", "Evals y calidad de modelos"];
const consulta = ref("");
const todas = ref(false);
const resultados = ref<ResultadoSemantico[]>([]);
const buscando = ref(false);
const buscado = ref(false);
const error = ref("");

async function buscar() {
  if (!consulta.value.trim()) return;
  buscando.value = true; error.value = "";
  try { resultados.value = await api.semantico(consulta.value, todas.value); buscado.value = true; }
  catch (e) { error.value = (e as Error).message; resultados.value = []; }
  finally { buscando.value = false; }
}
</script>

<style scoped>
.migas { display: flex; align-items: center; gap: .5rem; color: var(--texto-2); font-weight: 600; font-size: .88rem; margin-bottom: .6rem; }
.migas a { display: inline-flex; align-items: center; gap: .35rem; color: var(--texto-2); }
.migas svg { width: 1rem; height: 1rem; }
.sub { margin-top: .25rem; }
.prompt { display: flex; align-items: center; gap: .8rem; background: var(--superficie); border: 1px solid var(--borde); border-radius: 999px; padding: .45rem .45rem .45rem 1.3rem; box-shadow: var(--sombra-alta); max-width: 820px; }
.prompt:focus-within { border-color: var(--rosa); box-shadow: 0 0 0 4px var(--rosa-50), var(--sombra-alta); }
.chispa { width: 1.35rem; height: 1.35rem; color: var(--rosa-600); flex: none; }
.prompt input { border: 0; box-shadow: none !important; font-size: 1.02rem; padding: .7rem 0; background: transparent; }
.enviar { width: 3rem; height: 3rem; border-radius: 50%; border: 0; background: var(--grad-verde); color: #fff; display: grid; place-items: center; cursor: pointer; flex: none; }
.enviar:disabled { opacity: .45; cursor: not-allowed; }
.enviar svg { width: 1.15rem; height: 1.15rem; }
.opciones { display: flex; flex-wrap: wrap; gap: .55rem; align-items: center; margin: 1rem 0 1.5rem; max-width: 820px; }
.sugerencia { background: var(--superficie); border: 1px solid var(--borde-fuerte); border-radius: 999px; padding: .45rem 1rem; font-weight: 600; font-size: .86rem; cursor: pointer; }
.sugerencia:hover { border-color: var(--rosa); color: var(--rosa-600); }
.check { display: flex; align-items: center; gap: .45rem; margin-left: auto; font-size: .88rem; font-weight: 550; color: var(--texto-2); }
.r-cab { display: flex; justify-content: space-between; align-items: center; padding: 1.1rem 1.3rem; border-bottom: 1px solid var(--borde); }
.lista { list-style: none; margin: 0; padding: .3rem .5rem; }
.lista li { display: flex; align-items: center; gap: .9rem; padding: .85rem .8rem; }
.lista li + li { border-top: 1px solid var(--borde); }
.nombres { display: flex; flex-direction: column; gap: .15rem; flex: 1; min-width: 0; align-items: flex-start; }
.nombres a { font-weight: 700; color: var(--texto); }
.nombres span.texto-2 { font-size: .85rem; }
.sim { display: flex; align-items: center; gap: .6rem; width: 170px; flex: none; }
.barra { flex: 1; height: .4rem; background: var(--rosa-50); border-radius: 999px; overflow: hidden; }
.barra span { display: block; height: 100%; background: var(--rosa); border-radius: 999px; }
.sim strong { width: 3.2ch; text-align: right; font-variant-numeric: tabular-nums; }
.vacio span { font-size: .9rem; }
@media (max-width: 640px) { .lista li { flex-wrap: wrap; } .sim { width: 100%; } }
</style>
