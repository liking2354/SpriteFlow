import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { GraphListItem } from "@/api/types";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { useConfirm } from "@/components/ui/Confirm";

const PAGE_SIZE = 15;

export function GraphListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const confirm = useConfirm();

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [searchTimeout, setSearchTimeout] = useState<ReturnType<typeof setTimeout> | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["graphs", debouncedSearch, offset],
    queryFn: async () => {
      if (debouncedSearch) {
        const results = await api.searchGraphs(debouncedSearch);
        return { graphs: results, total: results.length, limit: PAGE_SIZE, offset: 0 };
      }
      return api.listGraphs({ limit: PAGE_SIZE, offset });
    },
  });

  const graphs = data?.graphs ?? [];
  const total = data?.total ?? 0;

  // 搜索防抖
  const handleSearchChange = useCallback(
    (value: string) => {
      setSearch(value);
      if (searchTimeout) clearTimeout(searchTimeout);
      const tid = setTimeout(() => {
        setDebouncedSearch(value.trim());
        setOffset(0);
      }, 300);
      setSearchTimeout(tid);
    },
    [searchTimeout]
  );

  // 删除
  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteGraph(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["graphs"] });
    },
  });

  const handleDelete = async (item: GraphListItem) => {
    const ok = await confirm({
      title: t("graph.deleteTitle", "删除管线图"),
      message: t("graph.deleteConfirm", "确定要删除管线图「{{name}}」？该操作不可撤销。", { name: item.name }),
      okText: t("common.delete"),
      variant: "danger",
    });
    if (ok) {
      deleteMut.mutate(item.id);
    }
  };

  // 跳转编辑
  const handleEdit = (id: string) => {
    navigate(`/graphs/${id}/edit`);
  };

  // 新建
  const handleNew = () => {
    navigate("/graphs/new");
  };

  const formatDate = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch {
      return iso;
    }
  };

  return (
    <div className="max-w-[1300px]">
      {/* Header */}
      <div className="mb-5 flex items-end justify-between">
        <div>
          <h2 className="text-[16px] font-semibold text-txt-0 mb-1">
            {t("graph.management", "管线图管理")}
          </h2>
          <p className="text-[12px] text-txt-2">{t("graph.managementDesc", "管理管线图：创建、编辑、执行、删除")}</p>
        </div>
        <Button size="sm" variant="primary" onClick={handleNew}>
          + {t("graph.createGraph", "新建管线图")}
        </Button>
      </div>

      {/* Search & Stats */}
      <div className="mb-3 flex items-center gap-3">
        <div className="relative flex-1 max-w-[320px]">
          <input
            type="text"
            className="w-full h-8 pl-8 pr-3 rounded-lg text-[12px] bg-bg-0 border border-[var(--line)] text-txt-0 focus:outline-none focus:ring-1 focus:ring-[var(--acc)]"
            placeholder={t("graph.searchPlaceholder", "搜索管线图名称...")}
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[13px] text-txt-3 pointer-events-none">
            🔍
          </span>
          {search && (
            <button
              onClick={() => {
                setSearch("");
                setDebouncedSearch("");
                setOffset(0);
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-txt-3 hover:text-txt-1"
            >
              ✕
            </button>
          )}
        </div>
        <span className="text-[11px] text-txt-3">
          {t("graph.totalCount", "共 {{total}} 个管线图", { total })}
        </span>
      </div>

      {/* Table */}
      <Card glass className="!p-0 overflow-hidden">
        {isLoading && (
          <div className="text-center py-16 text-txt-3 text-[12px]">{t("common.loading")}</div>
        )}

        {!isLoading && graphs.length === 0 && (
          <div className="text-center py-16">
            <div className="text-[11px] text-txt-3 mb-2">
              {debouncedSearch
                ? t("graph.searchEmpty", "未找到匹配的管线图")
                : t("graph.empty", "暂无管线图，点击上方按钮新建")}
            </div>
            {!debouncedSearch && (
              <Button size="sm" variant="ghost" onClick={handleNew}>
                + {t("graph.createGraph", "新建管线图")}
              </Button>
            )}
          </div>
        )}

        {!isLoading && graphs.length > 0 && (
          <>
            <table className="w-full text-[12px]">
              <thead>
                <tr
                  className="border-b"
                  style={{ borderColor: "var(--line-soft)" }}
                >
                  <th className="text-left py-2.5 px-4 font-medium text-txt-2 w-[30%]">
                    {t("graph.colName", "名称")}
                  </th>
                  <th className="text-left py-2.5 px-4 font-medium text-txt-2 w-[30%]">
                    {t("graph.colDesc", "描述")}
                  </th>
                  <th className="text-center py-2.5 px-4 font-medium text-txt-2 w-[8%]">
                    {t("graph.colNodes", "节点")}
                  </th>
                  <th className="text-left py-2.5 px-4 font-medium text-txt-2 w-[12%]">
                    {t("graph.colUpdated", "更新时间")}
                  </th>
                  <th className="text-right py-2.5 px-4 font-medium text-txt-2 w-[20%]">
                    {t("graph.colActions", "操作")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {graphs.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-[var(--line-soft)] hover:bg-bg-3 transition-colors cursor-pointer group"
                    onClick={() => handleEdit(item.id)}
                  >
                    <td className="py-2.5 px-4">
                      <div className="font-medium text-txt-0 truncate max-w-[260px]">
                        {item.name || t("graph.untitled", "未命名")}
                      </div>
                      {item.tags && item.tags.length > 0 && (
                        <div className="flex gap-1 mt-0.5">
                          {item.tags.slice(0, 3).map((tag) => (
                            <span
                              key={tag}
                              className="text-[9px] px-1.5 py-0.5 rounded bg-bg-0 text-txt-3 font-mono"
                            >
                              {tag}
                            </span>
                          ))}
                          {item.tags.length > 3 && (
                            <span className="text-[9px] text-txt-3">+{item.tags.length - 3}</span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="py-2.5 px-4 text-txt-2 truncate max-w-[260px]">
                      {item.description || "—"}
                    </td>
                    <td className="py-2.5 px-4 text-center">
                      <span
                        className="inline-flex items-center justify-center w-7 h-5 rounded text-[10px] font-mono"
                        style={{
                          background: "var(--bg-2)",
                          color: item.node_count > 0 ? "var(--acc)" : "var(--txt-3)",
                        }}
                      >
                        {item.node_count}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-txt-3 font-mono text-[11px]">
                      {formatDate(item.updated_at || item.created_at)}
                    </td>
                    <td className="py-2.5 px-4 text-right">
                      <div
                        className="flex items-center justify-end gap-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Button
                          size="xs"
                          variant="ghost"
                          onClick={() => handleEdit(item.id)}
                        >
                          {t("common.edit")}
                        </Button>
                        <Button
                          size="xs"
                          variant="ghost"
                          onClick={() => handleDelete(item)}
                        >
                          {t("common.delete")}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            <div className="px-4 py-2 border-t border-[var(--line-soft)]">
              <Pagination
                total={total}
                limit={PAGE_SIZE}
                offset={offset}
                onChange={setOffset}
              />
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
