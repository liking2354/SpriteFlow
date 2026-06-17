/** 新增/编辑自定义模型表单（对接后端 CRUD API） */
import { useState } from "react";

type InitialData = {
  model_id: string;
  name: string;
  category: string;
  subcategory?: string;
  service: string;
};

type Props = {
  onSave: (data: Record<string, unknown>) => void;
  onClose: () => void;
  editData?: InitialData | null;
};

const CATEGORIES = [
  { value: "text", label: "文本模型" },
  { value: "image", label: "图像模型" },
  { value: "video", label: "视频模型" },
  { value: "audio", label: "音频模型" },
];

const SERVICES = [
  { value: "openai", label: "OpenAI 兼容（含 OpenRouter）" },
  { value: "replicate", label: "Replicate" },
  { value: "ollama", label: "Ollama" },
];

const SUBCATEGORIES: Record<string, { value: string; label: string }[]> = {
  image: [
    { value: "generation", label: "生成图像" },
    { value: "editing", label: "编辑图像" },
  ],
  video: [
    { value: "generation", label: "生成视频" },
    { value: "editing", label: "编辑视频" },
  ],
};

export function ModelForm({ onSave, onClose, editData }: Props) {
  const isEdit = !!editData;
  const [modelId, setModelId] = useState(editData?.model_id || "");
  const [name, setName] = useState(editData?.name || "");
  const [category, setCategory] = useState(editData?.category || "text");
  const [subcategory, setSubcategory] = useState(editData?.subcategory || "");
  const [service, setService] = useState(editData?.service || "openai");

  const handleSubmit = () => {
    if (!modelId.trim() || !name.trim()) return;
    onSave({
      model_id: modelId.trim(),
      name: name.trim(),
      category,
      subcategory,
      service,
    });
  };

  const subcategoryOptions = SUBCATEGORIES[category] || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-[#1a1c1f] border border-gray-700 rounded-xl w-full max-w-md mx-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h3 className="text-base font-semibold text-white">{isEdit ? "编辑模型" : "新增模型"}</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl leading-none">&times;</button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">模型标识 *</label>
            <input value={modelId} onChange={(e) => setModelId(e.target.value)}
              disabled={isEdit}
              className={`w-full border border-gray-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-blue-500 font-mono ${isEdit ? "bg-[#1a1c1f] text-gray-500 cursor-not-allowed" : "bg-[#242629] text-white"}`}
              placeholder="如: deepseek/deepseek-v4-pro 或 gpt-4o" />
            {!isEdit && <p className="text-[11px] text-gray-500 mt-1">OpenRouter 模型格式: 供应商/模型名</p>}
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">显示名称 *</label>
            <input value={name} onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500"
              placeholder="如: DeepSeek V4 Pro" />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">分类</label>
            <select value={category} onChange={(e) => { setCategory(e.target.value); setSubcategory(""); }}
              className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500">
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>
          {subcategoryOptions.length > 0 && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">子分类</label>
              <select value={subcategory} onChange={(e) => setSubcategory(e.target.value)}
                className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500">
                <option value="">不区分</option>
                {subcategoryOptions.map((sc) => (
                  <option key={sc.value} value={sc.value}>{sc.label}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="block text-xs text-gray-400 mb-1">服务类型</label>
            <select value={service} onChange={(e) => setService(e.target.value)}
              className="w-full bg-[#242629] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-blue-500">
              {SERVICES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-gray-800">
          <button onClick={onClose}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">取消</button>
          <button onClick={handleSubmit}
            className="px-4 py-2 text-sm bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors disabled:opacity-50"
            disabled={!modelId.trim() || !name.trim()}>
            {isEdit ? "保存" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}
