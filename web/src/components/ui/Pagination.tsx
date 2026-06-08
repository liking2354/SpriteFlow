import { useTranslation } from "react-i18next";

export interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}

export function Pagination({ total, limit, offset, onChange }: PaginationProps) {
  const { t } = useTranslation();
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;

  if (total <= limit) return null;

  const pages: (number | "...")[] = [];
  const maxVisible = 5;
  let start = Math.max(1, currentPage - Math.floor(maxVisible / 2));
  let end = Math.min(totalPages, start + maxVisible - 1);
  if (end - start + 1 < maxVisible) {
    start = Math.max(1, end - maxVisible + 1);
  }

  if (start > 1) {
    pages.push(1);
    if (start > 2) pages.push("...");
  }
  for (let i = start; i <= end; i++) pages.push(i);
  if (end < totalPages) {
    if (end < totalPages - 1) pages.push("...");
    pages.push(totalPages);
  }

  const btnBase =
    "h-7 min-w-[28px] px-1.5 rounded-md text-[11px] border transition-colors flex items-center justify-center";
  const btnInactive = "border-[var(--line)] text-txt-2 hover:bg-bg-3 hover:text-txt-1";
  const btnActive = "border-[var(--acc)] text-[var(--acc)] bg-[rgba(99,102,241,0.10)] font-semibold";

  return (
    <div className="flex items-center justify-between pt-3">
      <span className="text-[11px] text-txt-3">
        {t("graph.paginationInfo", "共 {{total}} 条，第 {{page}}/{{totalPages}} 页", {
          total,
          page: currentPage,
          totalPages,
        })}
      </span>
      <div className="flex items-center gap-1">
        <button
          disabled={currentPage <= 1}
          onClick={() => onChange(Math.max(0, offset - limit))}
          className={`${btnBase} ${currentPage <= 1 ? "opacity-30 cursor-not-allowed" : btnInactive}`}
        >
          ‹
        </button>
        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`dots-${i}`} className="px-1 text-[10px] text-txt-3">
              ...
            </span>
          ) : (
            <button
              key={p}
              onClick={() => onChange((p - 1) * limit)}
              className={`${btnBase} ${p === currentPage ? btnActive : btnInactive}`}
            >
              {p}
            </button>
          )
        )}
        <button
          disabled={currentPage >= totalPages}
          onClick={() => onChange(Math.min((totalPages - 1) * limit, offset + limit))}
          className={`${btnBase} ${currentPage >= totalPages ? "opacity-30 cursor-not-allowed" : btnInactive}`}
        >
          ›
        </button>
      </div>
    </div>
  );
}
