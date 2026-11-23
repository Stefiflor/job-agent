<template>
  <header class="topbar">
    <div class="titulos"><slot /></div>
    <form class="buscar" role="search" @submit.prevent="ir">
      <kbd aria-hidden="true">⌘ K</kbd>
      <label class="solo-lector" for="buscar-global">Buscar ofertas por puesto o empresa</label>
      <input id="buscar-global" ref="entrada" v-model="q" type="search" placeholder="Buscar ofertas…" />
    </form>
  </header>
</template>

<script setup lang="ts">
// Búsqueda global: Cmd/Ctrl+K enfoca, Enter lleva a Ofertas filtradas por ese texto.
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const q = ref("");
const entrada = ref<HTMLInputElement | null>(null);
const ir = () => router.push({ path: "/ofertas", query: q.value ? { q: q.value } : {} });
const atajo = (e: KeyboardEvent) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); entrada.value?.focus(); }
};
onMounted(() => window.addEventListener("keydown", atajo));
onBeforeUnmount(() => window.removeEventListener("keydown", atajo));
</script>

<style scoped>
.topbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1.6rem; }
.titulos { min-width: 0; }
.buscar { display: flex; align-items: center; gap: .55rem; background: var(--superficie); border: 1px solid var(--borde); border-radius: 999px; padding: .3rem .4rem .3rem .45rem; width: 250px; box-shadow: var(--sombra); flex: none; }
.buscar:focus-within { border-color: var(--verde-600); box-shadow: 0 0 0 3px var(--verde-100); }
kbd { white-space: nowrap; font-family: var(--f); font-size: .72rem; font-weight: 700; background: var(--superficie-2); border: 1px solid var(--borde-fuerte); border-radius: 7px; padding: .1rem .4rem; color: var(--texto-2); }
.buscar input { border: 0; padding: .3rem .2rem; box-shadow: none !important; font-size: .85rem; background: transparent; }
@media (max-width: 760px) { .buscar { display: none; } }
</style>
