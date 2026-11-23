<template>
  <span class="pill" :class="tono" :aria-label="`Encaje ${encaje} por ciento`">{{ encaje }}%</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ encaje: number }>();
const tono = computed(() => (props.encaje >= 65 ? "alto" : props.encaje >= 40 ? "medio" : "bajo"));
</script>

<style scoped>
.pill { display: inline-block; font-weight: 750; font-size: .85rem; padding: .3rem .6rem; border-radius: 10px; font-variant-numeric: tabular-nums; }
.alto { background: var(--verde-100); color: var(--verde-700); }
.medio { background: var(--naranja-100); color: #b45c0c; }
.bajo { background: var(--rojo-100); color: var(--rojo); }
</style>
