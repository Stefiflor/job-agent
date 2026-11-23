<template>
  <div class="anillo" :class="tono" role="img" :aria-label="`Encaje ${encaje} por ciento`">
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <circle class="pista" cx="60" cy="60" r="50" />
      <circle class="valor" cx="60" cy="60" r="50" pathLength="100" :style="{ strokeDasharray: `${encaje} 100` }" />
    </svg>
    <div class="centro"><strong>{{ encaje }}%</strong><span>Encaje</span></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ encaje: number }>();
const tono = computed(() => (props.encaje >= 65 ? "alto" : props.encaje >= 40 ? "medio" : "bajo"));
</script>

<style scoped>
.anillo { position: relative; width: 132px; height: 132px; flex: none; }
svg { width: 100%; height: 100%; transform: rotate(-90deg); }
circle { fill: none; stroke-width: 11; }
.pista { stroke: var(--verde-50); }
.valor { stroke-linecap: round; transition: stroke-dasharray .8s ease; }
.alto .valor { stroke: var(--verde-800); }
.medio .valor { stroke: var(--naranja); } .medio .pista { stroke: var(--naranja-100); }
.bajo .valor { stroke: var(--rojo); } .bajo .pista { stroke: var(--rojo-100); }
.centro { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
strong { font-size: 1.75rem; font-family: var(--f-titulo); font-weight: 600; letter-spacing: 0; line-height: 1; }
span { font-size: .8rem; font-weight: 600; color: var(--texto-2); }
</style>
