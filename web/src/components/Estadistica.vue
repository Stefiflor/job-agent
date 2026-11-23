<template>
  <div class="stat panel">
    <span class="icono" :class="tono" aria-hidden="true"><component :is="icono" /></span>
    <div>
      <p class="valor">{{ valor }}</p>
      <p class="etiqueta">{{ etiqueta }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from "vue";
defineProps<{ valor: string | number; etiqueta: string; icono: Component; tono?: "acento" | "aplicar" | "dudoso" | "neutro" }>();
</script>

<style scoped>
.stat { display: flex; align-items: center; gap: .9rem; padding: 1rem 1.15rem; }
.icono { display: grid; place-items: center; width: 2.6rem; height: 2.6rem; border-radius: 11px; flex: none; background: var(--superficie-2); color: var(--texto-2); }
.icono svg { width: 1.25rem; height: 1.25rem; }
.icono.acento { background: var(--acento-suave); color: var(--acento); }
.icono.aplicar { background: var(--aplicar-suave); color: var(--aplicar); }
.icono.dudoso { background: var(--dudoso-suave); color: var(--dudoso); }
.valor { font-size: 1.45rem; font-weight: 800; letter-spacing: -.02em; font-variant-numeric: tabular-nums; line-height: 1.1; }
.etiqueta { font-size: .84rem; color: var(--texto-2); font-weight: 550; }
</style>
