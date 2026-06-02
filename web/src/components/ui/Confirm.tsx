import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

interface ConfirmOptions {
  title?: string;
  message: ReactNode;
  okText?: string;
  cancelText?: string;
  variant?: "default" | "danger";
}

type Resolver = (v: boolean) => void;

interface Ctx {
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
}

const ConfirmCtx = createContext<Ctx | null>(null);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const [resolver, setResolver] = useState<Resolver | null>(null);

  const confirm = useCallback((o: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setOpts(o);
      setResolver(() => resolve);
    });
  }, []);

  const close = (v: boolean) => {
    resolver?.(v);
    setOpts(null);
    setResolver(null);
  };

  const danger = opts?.variant === "danger";

  return (
    <ConfirmCtx.Provider value={{ confirm }}>
      {children}
      {opts && (
        <div
          className="fixed inset-0 z-[300] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in"
          onClick={() => close(false)}
        >
          <div
            className="w-[420px] rounded-l border border-line bg-bg-2 shadow-[0_24px_60px_rgba(0,0,0,0.6)] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 pt-5 pb-3">
              <div className="flex items-start gap-3">
                <div
                  className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
                  style={{
                    background: danger ? "rgba(255,91,110,0.12)" : "var(--acc-soft)",
                    color: danger ? "var(--red)" : "var(--acc)",
                  }}
                >
                  {danger ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 16v-4M12 8h.01" />
                    </svg>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  {opts.title && (
                    <div className="text-[14px] font-semibold text-txt-0 mb-1">
                      {opts.title}
                    </div>
                  )}
                  <div className="text-[12.5px] text-txt-1 leading-relaxed">
                    {opts.message}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-[var(--line-soft)]">
              <button
                onClick={() => close(false)}
                className="h-8 px-4 rounded-s border border-line bg-bg-3 text-[12px] text-txt-1 hover:text-txt-0 hover:border-[#2f3647] transition-colors"
              >
                {opts.cancelText || t("common.cancel")}
              </button>
              <button
                onClick={() => close(true)}
                className="h-8 px-4 rounded-s text-[12px] font-semibold text-white transition-all hover:-translate-y-px"
                style={{
                  background: danger
                    ? "linear-gradient(135deg, var(--red), #e04757)"
                    : "linear-gradient(135deg, var(--acc), var(--acc-hover))",
                  boxShadow: danger
                    ? "0 4px 16px rgba(255,91,110,0.4)"
                    : "0 4px 16px var(--acc-glow)",
                }}
              >
                {opts.okText || t("common.confirm")}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmCtx.Provider>
  );
}

export function useConfirm(): Ctx["confirm"] {
  const ctx = useContext(ConfirmCtx);
  if (!ctx) throw new Error("useConfirm must be used within ConfirmProvider");
  return ctx.confirm;
}
