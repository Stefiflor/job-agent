<template>
  <span class="chip" :class="veredicto">
    <component :is="icono" aria-hidden="true" />{{ texto }}
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { CircleCheck, CircleHelp, CircleX } from "lucide-vue-next";
import type { Veredicto } from "../api";
const props = defineProps<{ veredicto: Veredicto }>();
const icono = computed(() => ({ aplicar: CircleCheck, dudoso: CircleHelp, descartar: CircleX })[props.veredicto]);
const texto = computed(() => ({ aplicar: "Aplicar", dudoso: "Dudoso", descartar: "Descartar" })[props.veredicto]);
</script>
