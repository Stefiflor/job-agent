<template>
  <section v-if="d">
    <div class="barra-sup">
      <nav class="migas" aria-label="Ruta"><RouterLink to="/ofertas"><ArrowLeft aria-hidden="true" />Ofertas</RouterLink><span>/</span><span>Detalle</span></nav>
      <div class="acciones">
        <button class="btn btn-secundario btn-icono" :aria-label="d.en_tracker ? 'Guardada en postulaciones' : 'Guardar en postulaciones'" :disabled="d.en_tracker" @click="agregar">
          <BookmarkCheck v-if="d.en_tracker" aria-hidden="true" /><Bookmark v-else aria-hidden="true" />
        </button>
        <a class="btn btn-secundario" :href="d.candidata.link" target="_blank" rel="noopener">Ver aviso externo<ExternalLink aria-hidden="true" /></a>
        <button class="btn btn-primario" :disabled="d.en_tracker || agregando" @click="agregar">
          <Check v-if="d.en_tracker" aria-hidden="true" /><Plus v-else aria-hidden="true" />{{ d.en_tracker ? "En postulaciones" : "Agregar a postulaciones" }}
        </button>
      </div>
    </div>

    <header class="cabecera">
      <Avatar :nombre="d.candidata.empresa" tam="grande" />
      <div>
        <h1>{{ d.candidata.titulo }}</h1>
        <p class="texto-2 empresa">{{ d.candidata.empresa }}</p>
        <div class="chips">
          <span class="chip verde punto-chip">Remoto</span>
          <span class="chip"><Wallet aria-hidden="true" />{{ formatoSalario(d.candidata.salario_usd_mes, d.candidata.por_hora) }}</span>
          <span class="chip"><Globe aria-hidden="true" />{{ ubicacionCorta(d.candidata.paises_validos) }}</span>
        </div>
      </div>
    </header>

    <div class="tabs" role="tablist" aria-label="Secciones de la oferta">
      <button v-for="t in tabs" :key="t.id" role="tab" :aria-selected="tab === t.id" :class="{ activo: tab === t.id }" @click="tab = t.id">{{ t.texto }}</button>
    </div>
    <p v-if="error" class="error-caja"><TriangleAlert aria-hidden="true" />{{ error }}</p>

    <!-- Análisis -->
    <div v-if="tab === 'analisis'" class="panel-tab">
      <template v-if="ev">
        <div class="analisis">
          <div class="tarjeta evaluacion">
            <h2>Evaluación del encaje</h2>
            <div class="eval-cuerpo">
              <ScoreRing :encaje="ev.encaje" />
              <div>
                <p class="resumen">{{ ev.resumen }}</p>
                <ul class="checklist">
                  <li v-for="x in ev.cumple.slice(0, 4)" :key="x"><CircleCheck class="ok" aria-hidden="true" />{{ x }}</li>
                  <li v-for="x in ev.falta.slice(0, 2)" :key="x"><Circle class="falta" aria-hidden="true" />{{ x }} <span class="texto-3">(a reforzar)</span></li>
                </ul>
              </div>
            </div>
          </div>
          <div class="tarjeta proxima">
            <h2><Zap aria-hidden="true" />Próxima acción</h2>
            <p>{{ proxima.texto }}</p>
            <button class="btn btn-primario ancho" @click="proxima.accion()"><component :is="proxima.icono" aria-hidden="true" />{{ proxima.boton }}</button>
          </div>
        </div>
        <div class="resumenes">
          <button class="tarjeta mini" @click="tab = 'requisitos'"><CircleCheck class="ok" aria-hidden="true" /><div><strong>Cumple</strong><span class="texto-2">{{ ev.cumple.length }} requisitos</span></div></button>
          <button class="tarjeta mini" @click="tab = 'requisitos'"><CircleAlert class="falta" aria-hidden="true" /><div><strong>Le falta</strong><span class="texto-2">{{ ev.falta.length }} {{ ev.falta.length === 1 ? "requisito" : "requisitos" }}</span></div></button>
          <button class="tarjeta mini" @click="tab = 'requisitos'"><TriangleAlert class="alerta" aria-hidden="true" /><div><strong>Alertas</strong><span class="texto-2">{{ ev.red_flags[0] ?? "Sin alertas" }}</span></div></button>
        </div>
      </template>
      <div v-else class="tarjeta vacio"><CircleHelp aria-hidden="true" /><strong>Esta oferta todavía no fue evaluada</strong></div>
    </div>

    <!-- Descripción -->
    <div v-else-if="tab === 'descripcion'" class="tarjeta panel-tab texto-largo">{{ d.candidata.descripcion }}</div>

    <!-- Requisitos -->
    <div v-else-if="tab === 'requisitos'" class="panel-tab">
      <div v-if="ev" class="tres">
        <div class="tarjeta col"><h2><CircleCheck class="ok" aria-hidden="true" />Cumple</h2><ul><li v-for="x in ev.cumple" :key="x">{{ x }}</li></ul></div>
        <div class="tarjeta col"><h2><CircleAlert class="falta" aria-hidden="true" />Le falta</h2><ul><li v-for="x in ev.falta" :key="x">{{ x }}</li></ul><p v-if="!ev.falta.length" class="texto-3">Nada relevante.</p></div>
        <div class="tarjeta col"><h2><TriangleAlert class="alerta" aria-hidden="true" />Alertas</h2><ul><li v-for="x in ev.red_flags" :key="x">{{ x }}</li></ul><p v-if="!ev.red_flags.length" class="texto-3">Sin alertas.</p></div>
      </div>
      <p v-if="ev" class="texto-3 meta">Elegibilidad por ubicación: {{ ev.elegible_ubicacion }} · Salario en el texto: {{ ev.salario_detectado }} · Tipo: {{ ev.tipo_puesto }}</p>
    </div>

    <!-- Carta -->
    <div v-else class="tarjeta panel-tab carta">
      <div class="carta-cab">
        <div><h2>Carta de presentación</h2><p class="texto-2">Escrita solo con tu base de experiencia. Un segundo modelo verifica que no invente nada.</p></div>
        <div class="acciones">
          <select v-model="idioma" aria-label="Idioma"><option value="English">Inglés</option><option value="Spanish">Español</option></select>
          <button class="btn btn-primario" :disabled="generando" @click="generar">
            <Loader2 v-if="generando" class="girando" aria-hidden="true" /><PenLine v-else aria-hidden="true" />{{ generando ? "Escribiendo y verificando…" : carta || d.carta_md ? "Escribir de nuevo" : "Generar carta" }}
          </button>
        </div>
      </div>
      <template v-if="carta">
        <p class="estado" :class="carta.verificada ? 'ok' : 'mal'">
          <ShieldCheck v-if="carta.verificada" aria-hidden="true" /><ShieldAlert v-else aria-hidden="true" />
          {{ carta.verificada ? `Verificada: todas las afirmaciones tienen respaldo` : "Tiene afirmaciones sin respaldo: revisala antes de enviarla" }}
          <span class="texto-3">· {{ carta.intentos }} {{ carta.intentos === 1 ? "intento" : "intentos" }} · US$ {{ carta.costo_usd }}</span>
        </p>
        <div class="hoja">
          <button class="btn btn-secundario copiar" @click="copiar"><Copy aria-hidden="true" />{{ copiado ? "Copiada" : "Copiar" }}</button>
          <p v-for="(par, i) in parrafos" :key="i">{{ par }}</p>
        </div>
        <details><summary>De dónde sale cada afirmación ({{ carta.afirmaciones.length }})</summary>
          <ul class="fuentes"><li v-for="a in carta.afirmaciones" :key="a.texto"><span>{{ a.texto }}</span><span class="chip">{{ a.fuentes.join(", ") }}</span></li></ul>
        </details>
        <ul v-if="carta.problemas.length" class="error-caja problemas"><li v-for="p in carta.problemas" :key="p.afirmacion">{{ p.afirmacion }}: {{ p.motivo }}</li></ul>
      </template>
      <pre v-else-if="d.carta_md" class="hoja">{{ d.carta_md }}</pre>
      <div v-else class="vacio"><PenLine aria-hidden="true" /><strong>Todavía no hay carta para esta oferta</strong><span>Tocá “Generar carta”: tarda unos 30 segundos.</span></div>
    </div>
  </section>
  <p v-else-if="error" class="error-caja" role="alert">{{ error }}</p>
  <div v-else class="vacio"><Loader2 class="girando" aria-hidden="true" />Cargando…</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ArrowLeft, Bookmark, BookmarkCheck, Check, Circle, CircleAlert, CircleCheck, CircleHelp, Copy, ExternalLink,
  Globe, Loader2, PenLine, Plus, Send, ShieldAlert, ShieldCheck, TriangleAlert, Wallet, Zap,
} from "@lucide/vue";
import { api, formatoSalario, ubicacionCorta, type DetalleOferta, type ResultadoCarta } from "../api";
import Avatar from "../components/Avatar.vue";
import ScoreRing from "../components/ScoreRing.vue";

const props = defineProps<{ id: string }>();
const d = ref<DetalleOferta | null>(null);
const ev = computed(() => d.value?.evaluacion ?? null);
const tabs = [
  { id: "analisis", texto: "Análisis" }, { id: "descripcion", texto: "Descripción" },
  { id: "requisitos", texto: "Requisitos" }, { id: "carta", texto: "Carta de presentación" },
] as const;
const tab = ref<(typeof tabs)[number]["id"]>("analisis");
const carta = ref<ResultadoCarta | null>(null);
const parrafos = computed(() => (carta.value?.carta ?? "").split(/\n\s*\n/).filter(Boolean));
const idioma = ref<"English" | "Spanish">("English");
const generando = ref(false);
const agregando = ref(false);
const copiado = ref(false);
const error = ref("");

// La próxima acción sugerida depende de en qué punto está la oferta.
const proxima = computed(() => {
  const tieneCarta = !!(carta.value || d.value?.carta_md);
  if (!tieneCarta) return { texto: "Completar carta de presentación y aplicar.", boton: "Generar carta", icono: PenLine, accion: () => { tab.value = "carta"; generar(); } };
  if (!d.value?.en_tracker) return { texto: "Ya tenés la carta. Guardá la oferta para seguir la postulación.", boton: "Agregar a postulaciones", icono: Bookmark, accion: agregar };
  return { texto: "Carta lista y oferta guardada. Enviá la postulación desde el aviso.", boton: "Ir al aviso", icono: Send, accion: () => window.open(d.value!.candidata.link, "_blank", "noopener") };
});

onMounted(async () => { try { d.value = await api.oferta(props.id); } catch (e) { error.value = (e as Error).message; } });

async function agregar() {
  if (!d.value || d.value.en_tracker) return;
  agregando.value = true;
  try { await api.agregarAlTracker(props.id, ev.value?.resumen ?? ""); d.value.en_tracker = true; }
  catch (e) { error.value = (e as Error).message; }
  finally { agregando.value = false; }
}

async function generar() {
  generando.value = true; error.value = "";
  try { carta.value = await api.carta(props.id, idioma.value); }
  catch (e) { error.value = `No se pudo escribir la carta: ${(e as Error).message}`; }
  finally { generando.value = false; }
}

async function copiar() {
  await navigator.clipboard.writeText(carta.value?.carta ?? "");
  copiado.value = true; setTimeout(() => (copiado.value = false), 1800);
}
</script>

<style scoped>
.barra-sup { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.6rem; }
.migas { display: flex; align-items: center; gap: .5rem; color: var(--texto-2); font-weight: 600; font-size: .9rem; }
.migas a { display: inline-flex; align-items: center; gap: .35rem; color: var(--texto-2); }
.migas a:hover { color: var(--texto); }
.migas svg { width: 1rem; height: 1rem; }
.acciones { display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
.acciones select { width: auto; }
.cabecera { display: flex; gap: 1.1rem; align-items: flex-start; margin-bottom: 1.4rem; }
.cabecera h1 { font-size: clamp(1.6rem, 3vw, 2.1rem); font-family: var(--f-titulo); font-weight: 600; }
.empresa { font-weight: 600; margin: .2rem 0 .7rem; }
.chips { display: flex; gap: .4rem; flex-wrap: wrap; }
.tabs { display: flex; gap: 1.8rem; border-bottom: 1px solid var(--borde-fuerte); margin-bottom: 1.3rem; overflow-x: auto; }
.tabs button { border: 0; background: none; padding: .7rem 0; font-weight: 650; color: var(--texto-2); cursor: pointer; border-bottom: 2.5px solid transparent; margin-bottom: -1px; white-space: nowrap; }
.tabs button.activo { color: var(--texto); border-bottom-color: var(--rosa); }
.panel-tab { display: flex; flex-direction: column; gap: 1.1rem; }
.analisis { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(260px, 1fr); gap: 1.1rem; }
.evaluacion, .proxima { padding: 1.4rem; }
.evaluacion h2 { margin-bottom: 1.1rem; }
.eval-cuerpo { display: flex; gap: 1.6rem; align-items: center; }
.resumen { font-weight: 550; margin-bottom: .8rem; }
.checklist { list-style: none; padding: 0; margin: 0; display: grid; gap: .5rem; font-size: .9rem; }
.checklist li { display: flex; gap: .55rem; align-items: flex-start; }
.checklist svg { width: 1.1rem; height: 1.1rem; flex: none; margin-top: .1rem; }
.ok { color: var(--verde-600); } .falta { color: var(--naranja); } .alerta { color: var(--rojo); }
.proxima { display: flex; flex-direction: column; gap: 1rem; }
.proxima h2 { display: flex; align-items: center; gap: .5rem; }
.proxima h2 svg { width: 1.2rem; height: 1.2rem; color: var(--rosa-600); }
.proxima p { color: var(--texto-2); flex: 1; }
.ancho { width: 100%; }
.resumenes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.1rem; }
.mini { display: flex; gap: .75rem; align-items: flex-start; padding: 1.1rem 1.2rem; text-align: left; cursor: pointer; font: inherit; }
.mini:hover { box-shadow: var(--sombra-alta); }
.mini svg { width: 1.35rem; height: 1.35rem; flex: none; }
.mini div { display: flex; flex-direction: column; gap: .1rem; min-width: 0; }
.mini span { font-size: .85rem; }
.texto-largo { padding: 1.5rem; white-space: pre-line; color: var(--texto-2); line-height: 1.7; max-width: 90ch; }
.tres { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1.1rem; }
.col { padding: 1.3rem; }
.col h2 { display: flex; gap: .5rem; align-items: center; font-size: 1rem; margin-bottom: .7rem; }
.col h2 svg { width: 1.15rem; height: 1.15rem; }
.col ul { margin: 0; padding-left: 1.1rem; display: grid; gap: .4rem; color: var(--texto-2); }
.meta { font-size: .85rem; }
.carta { padding: 1.4rem; }
.carta-cab { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; align-items: flex-start; }
.carta-cab p { font-size: .9rem; margin-top: .2rem; }
.estado { display: flex; align-items: center; gap: .5rem; font-weight: 650; flex-wrap: wrap; }
.estado svg { width: 1.15rem; height: 1.15rem; }
.estado.ok { color: var(--verde-600); } .estado.mal { color: var(--rojo); }
.hoja { position: relative; background: var(--superficie-2); border: 1px solid var(--borde); border-radius: var(--r); padding: 1.6rem 1.8rem; max-width: 78ch; line-height: 1.75; display: grid; gap: .9rem; white-space: pre-wrap; font-family: var(--f); margin: 0; }
.copiar { position: absolute; top: .7rem; right: .7rem; padding: .4rem .7rem; }
summary { cursor: pointer; font-weight: 650; color: var(--texto-2); }
.fuentes { list-style: none; padding: 0; margin: .7rem 0 0; display: grid; gap: .45rem; }
.fuentes li { display: flex; justify-content: space-between; gap: 1rem; font-size: .9rem; }
.problemas { display: block; padding-left: 2rem; }
@media (max-width: 900px) {
  .analisis, .resumenes { grid-template-columns: 1fr; }
  .eval-cuerpo { flex-direction: column; align-items: flex-start; }
}
</style>
