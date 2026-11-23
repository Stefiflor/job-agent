<template>
  <span class="avatar" :class="tam" :style="{ background: fondo, color: tinta }" aria-hidden="true">{{ inicial }}</span>
</template>

<script setup lang="ts">
// Inicial de la empresa con un color estable derivado del nombre, dentro de una paleta acotada.
import { computed } from "vue";
const props = withDefaults(defineProps<{ nombre: string; tam?: "normal" | "grande" }>(), { tam: "normal" });
const PALETA = [["#fde9f1", "#c24b7d"], ["#e8effd", "#3d63c9"], ["#dcf2e4", "#156244"], ["#fdf0e3", "#b45c0c"], ["#f1ebfe", "#6d3fd1"]];
const par = computed(() => PALETA[[...props.nombre].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % PALETA.length]);
const inicial = computed(() => props.nombre.trim().charAt(0).toUpperCase() || "?");
const fondo = computed(() => par.value[0]);
const tinta = computed(() => par.value[1]);
</script>

<style scoped>
.avatar { display: grid; place-items: center; width: 2.6rem; height: 2.6rem; border-radius: 12px; font-family: var(--f-titulo); font-weight: 600; font-size: 1rem; flex: none; }
.grande { width: 3.6rem; height: 3.6rem; border-radius: 16px; font-size: 1.5rem; }
</style>
