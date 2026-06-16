import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useThemeStore } from "@/stores/theme";
import { useMenuStore } from "@/stores/menu";
import { AppShell } from "@/components/layout/AppShell";
import { GeneratePage } from "@/pages/Generate";
import { AssetsPage } from "@/pages/Assets";
import { RoutingPage } from "@/pages/Routing";
import { EditorPage } from "@/pages/Editor";
import { SpriteSheetPage } from "@/pages/SpriteSheet";
import { VideoPage } from "@/pages/Video";
import { TemplatesPage } from "@/pages/Templates";
import { GraphListPage } from "@/pages/GraphList";
import { GraphEditorPage } from "@/pages/GraphEditor";
import { VideoFramesPage } from "@/pages/VideoFrames";
import { WorkflowListPage } from "@/pages/workflow/WorkflowList";
import { WorkflowEditorPage } from "@/pages/workflow/WorkflowEditor";
import { ModelManager } from "@/pages/model-manager/ModelManager";

export function App() {
  const hydrate = useThemeStore((s) => s.hydrate);
  const loadMenu = useMenuStore((s) => s.loadFromPersistence);
  useEffect(() => {
    hydrate();
    loadMenu();
  }, [hydrate, loadMenu]);

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<GeneratePage />} />
        <Route path="/video" element={<VideoPage />} />
        <Route path="/assets" element={<AssetsPage />} />
        <Route path="/editor" element={<EditorPage />} />
        <Route path="/spritesheet" element={<SpriteSheetPage />} />
        <Route path="/routing" element={<RoutingPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/graphs" element={<GraphListPage />} />
        <Route path="/graphs/:graphId/edit" element={<GraphEditorPage />} />
        <Route path="/graphs/new" element={<GraphEditorPage />} />
        <Route path="/video-frames" element={<VideoFramesPage />} />
        <Route path="/workflow" element={<WorkflowListPage />} />
        <Route path="/workflow/:id" element={<WorkflowEditorPage />} />
        <Route path="/model-manager" element={<ModelManager />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
