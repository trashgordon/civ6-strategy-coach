import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built to frontend/dist, which FastAPI serves as static files. In dev, `npm run dev`
// serves on :5173 and proxies /api through to the FastAPI server on :8000.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
