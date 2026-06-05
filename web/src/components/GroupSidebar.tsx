import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { AssetGroup } from "@/api/types";
import { Button } from "@/components/ui/Button";

interface Props {
  /** 当前选中分组 id（null = 全部素材） */
  selectedGroupId: string | null;
  onSelect: (groupId: string | null) => void;
}

export function GroupSidebar({ selectedGroupId, onSelect }: Props) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const groups = useQuery({
    queryKey: ["groups"],
    queryFn: () => api.listGroups(),
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => api.createGroup(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["groups"] });
      setCreating(false);
      setNewName("");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.updateGroup(id, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["groups"] });
      setEditingId(null);
      setEditName("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteGroup(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["groups"] });
      if (selectedGroupId === editingId) onSelect(null);
    },
  });

  const handleCreate = () => {
    if (!newName.trim()) return;
    createMutation.mutate(newName.trim());
  };

  const handleUpdate = (id: string) => {
    if (!editName.trim()) return;
    updateMutation.mutate({ id, name: editName.trim() });
  };

  const handleDelete = (id: string) => {
    if (!confirm(t("assets.group.deleteConfirm", "确定要删除该分组？素材将移回未分组。"))) return;
    deleteMutation.mutate(id);
  };

  const startEdit = (g: AssetGroup) => {
    setEditingId(g.id);
    setEditName(g.name);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-3 border-b border-line">
        <h3 className="text-[11px] uppercase tracking-[1.5px] text-txt-3 font-semibold mb-2">
          {t("assets.group.title", "分组")}
        </h3>

        {/* 全部素材 */}
        <button
          onClick={() => onSelect(null)}
          className={`w-full text-left px-2.5 py-2 rounded-m text-[13px] transition-colors ${
            selectedGroupId === null
              ? "bg-[var(--acc)]/15 text-[var(--acc)] font-medium"
              : "text-txt-2 hover:bg-bg-3"
          }`}
        >
          📁 {t("assets.group.all", "全部素材")}
        </button>
      </div>

      {/* 分组列表 */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {groups.isLoading && (
          <div className="text-[11px] text-txt-3 py-2">{t("common.loading")}</div>
        )}

        {groups.data?.items.map((g) => (
          <div key={g.id} className="group/sidebar relative">
            {editingId === g.id ? (
              <div className="flex items-center gap-1 py-1">
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleUpdate(g.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  className="flex-1 bg-bg-2 border border-line rounded px-2 py-1 text-[12px] text-txt-1 outline-none focus:border-[var(--acc)]"
                  autoFocus
                />
                <Button size="xs" variant="ghost" onClick={() => handleUpdate(g.id)}>✓</Button>
                <Button size="xs" variant="ghost" onClick={() => setEditingId(null)}>✕</Button>
              </div>
            ) : (
              <button
                onClick={() => onSelect(g.id)}
                className={`w-full text-left px-2.5 py-2 rounded-m text-[13px] transition-colors flex items-center justify-between ${
                  selectedGroupId === g.id
                    ? "bg-[var(--acc)]/15 text-[var(--acc)] font-medium"
                    : "text-txt-2 hover:bg-bg-3"
                }`}
              >
                <span className="truncate flex-1">📁 {g.name}</span>
                <span className="hidden group-hover/sidebar:flex items-center gap-0.5 ml-1 flex-shrink-0">
                  <button
                    onClick={(e) => { e.stopPropagation(); startEdit(g); }}
                    className="px-1 py-0.5 rounded text-[10px] text-txt-3 hover:text-txt-1 hover:bg-bg-1"
                    title={t("common.edit", "编辑")}
                  >
                    ✎
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(g.id); }}
                    className="px-1 py-0.5 rounded text-[10px] text-red-400 hover:text-red-300 hover:bg-bg-1"
                    title={t("common.delete", "删除")}
                  >
                    ✕
                  </button>
                </span>
              </button>
            )}
          </div>
        ))}

        {groups.data && groups.data.items.length === 0 && (
          <div className="text-[11px] text-txt-3 py-2">
            {t("assets.group.empty", "暂无分组")}
          </div>
        )}
      </div>

      {/* 新建分组 */}
      <div className="px-3 py-3 border-t border-line">
        {creating ? (
          <div className="flex items-center gap-1">
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleCreate();
                if (e.key === "Escape") { setCreating(false); setNewName(""); }
              }}
              placeholder={t("assets.group.namePlaceholder", "分组名称")}
              className="flex-1 bg-bg-2 border border-line rounded px-2 py-1.5 text-[12px] text-txt-1 outline-none focus:border-[var(--acc)]"
              autoFocus
            />
            <Button size="xs" variant="primary" onClick={handleCreate} loading={createMutation.isPending}>
              {t("common.create")}
            </Button>
            <Button size="xs" variant="ghost" onClick={() => { setCreating(false); setNewName(""); }}>
              ✕
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            className="w-full justify-start text-[12px]"
            onClick={() => setCreating(true)}
          >
            ＋ {t("assets.group.create", "新建分组")}
          </Button>
        )}
      </div>
    </div>
  );
}
