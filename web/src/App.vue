<template>
  <div class="app">
    <aside class="lateral">
      <RouterLink to="/" class="logo" aria-label="job-agent, inicio">
        <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M9 25 15 7M17 25 23 7" /></svg>
      </RouterLink>
      <nav aria-label="Secciones">
        <RouterLink v-for="item in items" :key="item.to" :to="item.to" class="nav-item" :class="{ activo: activo(item) }" :aria-label="item.texto">
          <component :is="item.icono" aria-hidden="true" />
          <span class="tip" aria-hidden="true">{{ item.texto }}</span>
        </RouterLink>
      </nav>
      <div class="abajo">
        <span class="estado" :class="{ ok: apiOk }" :title="apiOk ? 'API conectada' : 'API sin conexión'"></span>
        <span class="yo" title="Florencia Gambero">FG</span>
      </div>
    </aside>
    <main class="contenido"><RouterView /></main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ChartNoAxesColumn, House, Search, Sparkles, SquareKanban } from "lucide-vue-next";

const route = useRoute();
const items = [
  { to: "/", texto: "Inicio", icono: House, rutas: ["/"] },
  { to: "/ofertas", texto: "Ofertas", icono: Search, rutas: ["/ofertas", "/oferta", "/busqueda"] },
  { to: "/agente", texto: "Agente", icono: Sparkles, rutas: ["/agente"] },
  { to: "/tracker", texto: "Postulaciones", icono: SquareKanban, rutas: ["/tracker"] },
  { to: "/evals", texto: "Calidad del evaluador", icono: ChartNoAxesColumn, rutas: ["/evals"] },
];
const activo = (item: (typeof items)[number]) =>
  item.to === "/" ? route.path === "/" : item.rutas.some((r) => route.path.startsWith(r));
const apiOk = ref(false);
onMounted(async () => { apiOk.value = await fetch("/api/salud").then((r) => r.ok).catch(() => false); });
</script>

<style scoped>
.app { display: grid; grid-template-columns: 76px 1fr; min-height: 100vh; }
.lateral { background: var(--grad-verde); display: flex; flex-direction: column; align-items: center; padding: 1.1rem 0; gap: 1.4rem; position: sticky; top: 0; height: 100vh; border-radius: 0 22px 22px 0; }
.logo { width: 2.6rem; height: 2.6rem; display: grid; place-items: center; }
.logo svg { width: 2rem; height: 2rem; fill: none; stroke: var(--rosa); stroke-width: 4.2; stroke-linecap: round; }
nav { display: flex; flex-direction: column; gap: .55rem; }
.nav-item { position: relative; width: 2.8rem; height: 2.8rem; display: grid; place-items: center; border-radius: 12px; color: #b9d0c5; transition: background .15s, color .15s; }
.nav-item svg { width: 1.3rem; height: 1.3rem; }
.nav-item:hover { background: rgba(255, 255, 255, .08); color: #fff; }
.nav-item.activo { background: var(--rosa); color: var(--verde-950); box-shadow: 0 6px 18px rgba(244, 178, 201, .35); }
.tip { position: absolute; left: calc(100% + .7rem); background: var(--texto); color: #fff; font-size: .8rem; font-weight: 600; padding: .3rem .6rem; border-radius: 8px; white-space: nowrap; opacity: 0; pointer-events: none; transform: translateX(-4px); transition: opacity .15s, transform .15s; z-index: 10; }
.nav-item:hover .tip, .nav-item:focus-visible .tip { opacity: 1; transform: none; }
.abajo { margin-top: auto; display: flex; flex-direction: column; align-items: center; gap: .9rem; }
.estado { width: .55rem; height: .55rem; border-radius: 50%; background: var(--rojo); }
.estado.ok { background: #4ade80; box-shadow: 0 0 0 3px rgba(74, 222, 128, .25); }
.yo { width: 2.4rem; height: 2.4rem; border-radius: 50%; display: grid; place-items: center; background: var(--rosa-100); color: var(--rosa-600); font-weight: 800; font-size: .85rem; border: 2px solid rgba(255, 255, 255, .6); }
.contenido { padding: 1.6rem clamp(1rem, 3vw, 2.5rem) 3rem; min-width: 0; max-width: 1400px; width: 100%; }

@media (max-width: 760px) {
  .app { grid-template-columns: 1fr; }
  .lateral { position: sticky; z-index: 20; height: auto; flex-direction: row; padding: .5rem .8rem; border-radius: 0 0 18px 18px; gap: .6rem; }
  nav { flex-direction: row; gap: .3rem; }
  .abajo { margin: 0 0 0 auto; flex-direction: row; }
  .tip { display: none; }
}
</style>
