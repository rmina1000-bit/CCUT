// [SCRIPT-1 검증 전용] 국장 스택(8000/5173) 무접촉을 위한 병렬 설정.
// 백엔드 8001 프록시, 포트 5174. 커밋된 vite.config.ts는 손대지 않는다.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig(() => ({
  server: {
    host: true,
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8001", changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
      "/static": { target: "http://127.0.0.1:8001", changeOrigin: true },
    },
  },
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
}));
