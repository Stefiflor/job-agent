import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import "@fontsource-variable/plus-jakarta-sans";
import "@fontsource-variable/fredoka";
import "./styles.css";
import App from "./App.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", component: () => import("./views/InicioView.vue"), meta: { titulo: "Inicio" } },
    { path: "/ofertas", component: () => import("./views/OfertasView.vue"), meta: { titulo: "Ofertas" } },
    { path: "/oferta/:id", component: () => import("./views/OfertaView.vue"), props: true, meta: { titulo: "Oferta" } },
    { path: "/agente", component: () => import("./views/AgenteView.vue"), meta: { titulo: "Agente" } },
    { path: "/tracker", component: () => import("./views/TrackerView.vue"), meta: { titulo: "Postulaciones" } },
    { path: "/evals", component: () => import("./views/EvalsView.vue"), meta: { titulo: "Calidad del evaluador" } },
    { path: "/busqueda", component: () => import("./views/BusquedaView.vue"), meta: { titulo: "Búsqueda semántica" } },
  ],
  scrollBehavior: () => ({ top: 0 }),
});
router.afterEach((to) => { document.title = `${to.meta.titulo ?? "job-agent"} · job-agent`; });

createApp(App).use(router).mount("#app");
