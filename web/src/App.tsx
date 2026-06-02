import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useThemeStore } from "@/stores/theme";
import { AppShell } from "@/components/layout/AppShell";
import { GeneratePage } from "@/pages/Generate";
import { WorkflowsPage } from "@/pages/Workflows";
import { AssetsPage } from "@/pages/Assets";
import { RoutingPage } from "@/pages/Routing";
import { NodesPage } from "@/pages/Nodes";

export function App() {
  const hydrate = useThemeStore((s) => s.hydrate);
  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<GeneratePage />} />
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/assets" element={<AssetsPage />} />
        <Route path="/nodes" element={<NodesPage />} />
        <Route path="/routing" element={<RoutingPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
