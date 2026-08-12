import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import LedgerPage from "./pages/LedgerPage";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Index from "./pages/Index.tsx";
import TrashPortal from "./pages/TrashPortal.tsx";
import AdminIndex from "./pages/AdminIndex.tsx";
import BasketPortal from "./pages/BasketPortal.tsx";
import NotFound from "./pages/NotFound.tsx";
import QwenDirect from "./pages/QwenDirect.tsx";
import FragmentPanelPreview from "./components/FragmentPanelPreview.tsx";
import "./ccut-ui.css";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/trash" element={<TrashPortal />} />
          {/* [LEDGER-1] 원고 — MASTER CONCEPT ①원고 (R0 읽기 전용) */}
          <Route path="/ledger" element={<LedgerPage />} />
          {/* [Admin v0] 관리자 셸 — 사용자 작업실과 분리된 독립 라우트 */}
          <Route path="/admin/*" element={<AdminIndex />} />
          {/* [바구니 새창 C] 작업대 바구니 전용창 — BroadcastChannel 동기화 */}
          <Route path="/basket-portal" element={<BasketPortal />} />
          {/* [QWEN-DIRECT] 국장↔큐원 직통 — 게이트·프롬프트·필터·저장 없음 */}
          <Route path="/qwen" element={<QwenDirect />} />
          {/* [PBE-PREVIEW] 외부 데이터·저장·재생 연결 없는 패널 목업 */}
          <Route path="/pbe-preview" element={<FragmentPanelPreview />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
