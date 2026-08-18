import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { VitePWA } from "vite-plugin-pwa";

// Workbox PWA strategy, taken from dinary:
//
// - registerType 'autoUpdate' + skipWaiting + clientsClaim: the new
//   bundle is served on the very next reload after a deploy.
// - globPatterns precaches every hashed Vite output, so the PWA can
//   boot fully offline once it has been opened online once.
// - navigateFallback to index.html keeps SPA navigations working
//   offline, excluding /api/* so backend calls always go to network.
// - runtimeCaching adds a NetworkOnly policy for /api/* as a belt-
//   and-braces guarantee that no API response is ever cached.
export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "auto",
      manifest: false,
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico,webmanifest,json}"],
        skipWaiting: true,
        clientsClaim: true,
        navigateFallback: "index.html",
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith("/api/"),
            handler: "NetworkOnly",
          },
        ],
      },
    }),
  ],
  build: {
    outDir: "../_static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8080",
    },
  },
});
