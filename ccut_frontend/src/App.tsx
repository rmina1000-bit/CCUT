import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Index from "./pages/Index.tsx";
import TrashPortal from "./pages/TrashPortal.tsx";
import AdminIndex from "./pages/AdminIndex.tsx";
import BasketPortal from "./pages/BasketPortal.tsx";
import NotFound from "./pages/NotFound.tsx";

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
          {/* [Admin v0] 관리자 셸 — 사용자 작업실과 분리된 독립 라우트 */}
          <Route path="/admin/*" element={<AdminIndex />} />
          {/* [바구니 새창 C] 작업대 바구니 전용창 — BroadcastChannel 동기화 */}
          <Route path="/basket-portal" element={<BasketPortal />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
