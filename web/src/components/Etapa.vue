<template>
  <span class="etapa" :class="clase">{{ texto }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Estado } from "../api";
const props = defineProps<{ estado: Estado }>();
const MAPA: Record<Estado, [string, string]> = {
  "para aplicar": ["Para aplicar", "azul"], aplicada: ["Aplicada", "violeta"], entrevista: ["Entrevista", "rosa"],
  oferta: ["Oferta", "verde"], descartada: ["Descartada", "gris"],
};
const texto = computed(() => MAPA[props.estado][0]);
const clase = computed(() => MAPA[props.estado][1]);
</script>

<style scoped>
.etapa { display: inline-flex; align-items: center; gap: .4rem; font-size: .8rem; font-weight: 650; padding: .28rem .65rem; border-radius: 999px; white-space: nowrap; }
.etapa::before { content: ""; width: .45rem; height: .45rem; border-radius: 50%; background: currentColor; }
.azul { background: var(--azul-100); color: var(--azul); }
.violeta { background: var(--violeta-100); color: var(--violeta); }
.rosa { background: var(--rosa-100); color: var(--rosa-600); }
.verde { background: var(--verde-100); color: var(--verde-700); }
.gris { background: #eef0ef; color: var(--texto-2); }
</style>
