import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { WorkflowRunResponse } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { Led } from "@/components/ui/Led";

const SAMPLES = [
  "workflows/example_text2img.yaml",
  "workflows/example_img2img.yaml",
  "workflows/example_sequential_8dir.yaml",
  "workflows/example_multi_image_fusion.yaml",
];

const STATUS_COLOR: Record<string, "green" | "red" | "amber" | "acc"> = {
  completed: "green",
  failed: "red",
  running: "acc",
  pending: "amber",
};

export function WorkflowsPage() {
  const { t } = useTranslation();
  const [yamlPath, setYamlPath] = useState(SAMPLES[0]);
  const [run, setRun] = useState<WorkflowRunResponse | null>(null);

  const submit = useMutation({
    mutationFn: () => api.submitWorkflow(yamlPath),
    onSuccess: (data) => setRun(data),
  });

  return (
    <div className="grid grid-cols-12 gap-5 max-w-[1400px]">
      <div className="col-span-12 lg:col-span-5">
        <Card title={t("workflows.title")} subtitle={t("workflows.subtitle")}>
          <Field label={t("workflows.fields.yamlPath")}>
            <TextInput
              value={yamlPath}
              onChange={(e) => setYamlPath(e.target.value)}
              placeholder={t("workflows.fields.yamlPathPlaceholder")}
            />
          </Field>

          <div className="text-[11px] text-txt-3 mb-2 mt-3">
            {t("workflows.samples")}
          </div>
          <div className="flex flex-col gap-1.5 mb-5">
            {SAMPLES.map((s) => (
              <button
                key={s}
                onClick={() => setYamlPath(s)}
                className={`text-left px-3 h-8 rounded-s text-[11.5px] font-mono border transition-colors ${
                  yamlPath === s
                    ? "border-[var(--acc)] text-[var(--acc)]"
                    : "border-line text-txt-2 hover:border-[#2f3647] hover:text-txt-1"
                }`}
                style={yamlPath === s ? { background: "var(--acc-soft)" } : undefined}
              >
                {s}
              </button>
            ))}
          </div>

          <Button loading={submit.isPending} onClick={() => submit.mutate()}>
            ▶ {t("workflows.actions.run")}
          </Button>

          {submit.error && (
            <div className="mt-4 px-3 py-2.5 bg-[var(--red)]/10 border border-[var(--red)]/30 rounded-s text-[12px] text-[var(--red)]">
              {String(submit.error)}
            </div>
          )}
        </Card>
      </div>

      <div className="col-span-12 lg:col-span-7">
        <Card title={t("workflows.result.nodes")}>
          {!run && (
            <div className="text-center text-txt-3 py-12 text-[12px]">
              {t("common.empty")}
            </div>
          )}
          {run && (
            <>
              <div className="grid grid-cols-2 gap-3 mb-4 px-3 py-2.5 bg-bg-0 rounded-s font-mono text-[11px] text-txt-2">
                <span>
                  <span className="text-txt-3">{t("workflows.result.runId")}: </span>
                  {run.run_id}
                </span>
                <span className="flex items-center gap-1.5">
                  <Led color={STATUS_COLOR[run.status]} size={6} />
                  {t(`workflows.result.${run.status}`)}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                {Object.entries(run.results).map(([nid, r]) => (
                  <div
                    key={nid}
                    className="flex items-center gap-3 px-3 py-2.5 bg-bg-0 border border-[var(--line-soft)] rounded-s"
                  >
                    <Led color={STATUS_COLOR[r.status]} size={7} />
                    <span className="font-mono text-[12px] text-txt-1">{nid}</span>
                    <span className="ml-auto text-[10.5px] text-txt-2 font-mono">
                      {r.cache_hit && (
                        <span className="text-[var(--cyan)] mr-2">⚡ cache</span>
                      )}
                      {t(`workflows.result.${r.status}`)}
                    </span>
                    {r.error && (
                      <span className="text-[10.5px] text-[var(--red)]">{r.error}</span>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
