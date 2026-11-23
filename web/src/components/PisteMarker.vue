<template>
  <span :class="['marcador', veredicto, { chico }]" :title="etiqueta">
    <span class="forma" aria-hidden="true"></span>
    <span v-if="encaje !== undefined" class="numero">{{ encaje }}</span>
    <span class="solo-lector">{{ etiqueta }}</span>
  </span>
</template>

<script setup lang="ts">
// Encaje como señal de pista: azul-círculo = aplicar, rojo-cuadrado = dudoso, negro-rombo = descartar.
// La forma repite la información del color (no depende solo del color).
import { computed } from "vue";
import type { Veredicto } from "../api";

const props = defineProps<{ veredicto: Veredicto; encaje?: number; chico?: boolean }>();
const etiqueta = computed(() =>
  `${props.veredicto}${props.encaje !== undefined ? `, encaje ${props.encaje} de 100` : ""}`);
</script>

<style scoped>
.marcador { display: inline-flex; align-items: center; gap: .45rem; }
.forma { width: 1.5rem; height: 1.5rem; display: inline-block; flex: none; }
.chico .forma { width: .8rem; height: .8rem; }
.aplicar .forma { background: var(--pista-azul); border-radius: 50%; }
.dudoso .forma { background: var(--pista-roja); }
.descartar .forma { background: var(--pista-negra); transform: rotate(45deg) scale(.82); }
.numero { font-family: var(--f-titulo); font-weight: 600; font-size: 1.35rem; font-variant-numeric: tabular-nums; min-width: 2ch; }
</style>
