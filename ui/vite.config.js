import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies the API to a locally running simulator (python main.py)
export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 2000 },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:15001" },
  },
});
