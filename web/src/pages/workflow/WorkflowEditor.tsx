import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ReactFlowProvider } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Toaster } from "react-hot-toast";
import axios from "axios";
import { useTranslation } from "react-i18next";
import NodeFlow from "./components/NodeFlow";

export function WorkflowEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [nodeSchemas, setNodeSchemas] = useState<any>(null);
  const [workflowData, setWorkflowData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    console.log("[WorkflowEditor] loadData called, id:", id);
    if (!id) {
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      setError(null);
      console.log("[WorkflowEditor] fetching APIs...");
      const [schemasRes, defRes] = await Promise.all([
        axios.get(`/api/workflow/${id}/node-schemas`),
        axios.get(`/api/workflow/get-workflow-def/${id}`),
      ]);
      console.log("[WorkflowEditor] APIs returned:", {
        schemasKeys: Object.keys(schemasRes.data || {}),
        defName: defRes.data?.name,
        defDataKeys: defRes.data?.data ? Object.keys(defRes.data.data) : [],
      });
      setNodeSchemas(schemasRes.data || {});
      setWorkflowData(defRes.data || null);
    } catch (err: any) {
      console.error("Failed to load workflow data", err);
      const msg = err?.response?.data?.detail || err?.message || "Unknown error";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (!id) {
    // New workflow - no data to load
    return (
      <div className="flex flex-col h-full w-full">
        <ReactFlowProvider>
          <NodeFlow initialNodeSchemas={null} initialWorkflowData={null} />
        </ReactFlowProvider>
        <Toaster position="top-right" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full w-full">
        <div className="text-lg text-[var(--txt-2)]">{t('workflow.loading')}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full gap-4">
        <div className="text-lg text-red-500">{t('workflow.loadFailed')}</div>
        <div className="text-sm text-[var(--txt-3)]">{error}</div>
        <button
          onClick={() => navigate("/workflow")}
          className="px-4 py-2 rounded text-sm"
          style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
        >
          {t('workflow.backToList')}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-full">
      <ReactFlowProvider>
        <NodeFlow
          initialNodeSchemas={nodeSchemas}
          initialWorkflowData={workflowData}
        />
      </ReactFlowProvider>
      <Toaster position="top-right" />
    </div>
  );
}
