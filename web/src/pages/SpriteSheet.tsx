/**
 * /spritesheet — 精灵表工具页面（三步分阶段）
 *
 * 步骤：
 *   1. 选图与切分（Source & Split）
 *   2. 帧列表处理（Frames）
 *   3. 导出与下载（Export）
 *
 * 用顶部步骤条导航，每步可点击回退；已完成的步显示摘要。
 * 全过程纯前端 Canvas，复用 SpriteFlow 现有 UI 与素材接口。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactDOM from "react-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Segment } from "@/components/ui/Segment";
import { Field, Switch } from "@/components/ui/Field";
import { AssetPicker } from "@/components/ui/AssetPicker";
import { FaCheck, FaPause, FaPlay } from "react-icons/fa6";
import { IoClose } from "react-icons/io5";
import {
  type Frame,
  loadImage,
  splitGridByBoundaries,
  evenBoundaries,
  splitByTransparent,
  unifyFrames,
  cropFramesToMin,
  autoTrimFrames,
  fitFramesToCell,
  flipFrameH,
  shiftFrame,
  scaleFrame,
  cloneFrame,
  exportFramesZip,
  exportFramesGif,
  recombineFrames,
  downloadBlob,
} from "@/lib/spritesheet";

type SplitMode = "grid" | "transparent";
type VAlign = "bottom" | "middle" | "top";
/** 帧尺寸统一策略：off=保持各自原尺寸；pad=扩到最大尺寸（居中补透明）；crop=裁到最小尺寸（居中裁剪） */
type Unify = "off" | "pad" | "crop";
type Step = 1 | 2 | 3 | 4;
type ProcessingMode = "pixel" | "smooth";

interface FrameState {
  id: number;
  frame: Frame;
  selected: boolean;
  dx: number;
  dy: number;
}

let _uid = 0;

/** 滑块拖动数字输入 */
function SliderInput({
  value,
  onChange,
  min = 1,
  max = 256,
  className = "",
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  className?: string;
}) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 h-2 appearance-none bg-bg-0 border border-line rounded-full cursor-pointer accent-[var(--acc)]"
      />
      <span className="w-10 text-center text-[11px] font-mono text-txt-1 tabular-nums">{value}</span>
    </div>
  );
}

export function SpriteSheetPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  // —— 步骤 ——
  const [step, setStep] = useState<Step>(1);

  // —— 源图 ——
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [imgEl, setImgEl] = useState<HTMLImageElement | null>(null);
  const [sourceLabel, setSourceLabel] = useState<string>("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  // —— 切分参数 ——
  const [mode, setMode] = useState<SplitMode>("grid");
  const [cols, setCols] = useState(4);
  const [rows, setRows] = useState(4);
  const [unify, setUnify] = useState(true);
  const [vAlign, setVAlign] = useState<VAlign>("bottom");
  /** 切完后是否统一帧尺寸（grid 模式默认 pad，最适合宽不一致+高度不一的角色三视图） */
  const [unifyMode, setUnifyMode] = useState<Unify>("pad");
  /** 自动裁背景边的方式：off=不裁；alpha=按 alpha 通道；bgColor=按背景色相近度 */
  const [trimMode, setTrimMode] = useState<"off" | "alpha" | "bgColor">("alpha");
  /** alpha 阈值 */
  const [trimThreshold, setTrimThreshold] = useState(8);
  /** bgColor 模式的颜色容差（0~441） */
  const [colorTolerance, setColorTolerance] = useState(32);
  // 自定义切分边界（不含两端 0/W、0/H 的中间分割线位置；像素值）
  const [xCuts, setXCuts] = useState<number[]>([]);
  const [yCuts, setYCuts] = useState<number[]>([]);

  // —— 帧 ——
  const [frames, setFrames] = useState<FrameState[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);

  // —— 预览播放 ——
  const [playing, setPlaying] = useState(false);
  const [fps, setFps] = useState(8);
  const ZOOM = 4; // 预览渲染固定倍率（不再显示滑块）
  const [checker, setChecker] = useState(true);
  /** 是否显示居中十字线辅助线（帧缩略图 + 预览画布同步显示） */
  const [crosshair, setCrosshair] = useState(false);
  const [playIdx, setPlayIdx] = useState(0);
  const previewRef = useRef<HTMLCanvasElement>(null);

  // —— 帧列表显示网格 ——
  const [gridCols, setGridCols] = useState(4);

  // —— 导出参数 ——
  const [layoutCols, setLayoutCols] = useState(4);
  const [busy, setBusy] = useState<string | null>(null);
  /** 导出固定单帧尺寸：0 = 用原始尺寸（取最大宽高），其它 = 强制 cellW = cellH */
  const [cellSize, setCellSize] = useState<number>(0);
  /** 处理模式：pixel=像素处理（最近邻，默认），smooth=原图处理（平滑插值） */
  const [processingMode, setProcessingMode] = useState<ProcessingMode>("pixel");
  const smooth = processingMode === "smooth";
  /** 大图详情对话框开关 */
  const [previewLightbox, setPreviewLightbox] = useState(false);

  // ============ 载图 ============
  const setSource = async (url: string, label: string) => {
    setLoadErr(null);
    setImgUrl(url);
    setSourceLabel(label);
    setFrames([]);
    try {
      const proxied = `/api/proxy-image?url=${encodeURIComponent(url)}`;
      const res = await fetch(proxied);
      if (!res.ok) throw new Error(`代理请求失败: ${res.status}`);
      const objUrl = URL.createObjectURL(await res.blob());
      const img = await loadImage(objUrl);
      setImgEl(img);
    } catch (e) {
      setLoadErr(String(e));
      setImgEl(null);
    }
  };

  const uploadMut = useMutation({
    mutationFn: (file: File) => api.uploadAsset(file, "spritesheet:source"),
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      setSource(asset.uri, asset.id);
    },
  });

  // 当源图/列数/行数变化时，把切分线重置为均分位置（不含两端）
  useEffect(() => {
    if (!imgEl) {
      setXCuts([]);
      setYCuts([]);
      return;
    }
    const ev = evenBoundaries(imgEl.naturalWidth, cols).slice(1, -1);
    const eh = evenBoundaries(imgEl.naturalHeight, rows).slice(1, -1);
    setXCuts(ev);
    setYCuts(eh);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imgEl, cols, rows]);

  const onLocalFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const url = URL.createObjectURL(f);
    setLoadErr(null);
    setImgUrl(url);
    setSourceLabel(f.name);
    setFrames([]);
    loadImage(url).then(setImgEl).catch((er) => setLoadErr(String(er)));
    uploadMut.mutate(f);
    e.target.value = "";
  };

  // ============ 切分 ============
  const doSplit = () => {
    if (!imgEl) return;
    try {
      let raw: Frame[];
      if (mode === "grid") {
        const W = imgEl.naturalWidth;
        const H = imgEl.naturalHeight;
        const xs = [0, ...xCuts, W];
        const ys = [0, ...yCuts, H];
        raw = splitGridByBoundaries(imgEl, xs, ys);
      } else {
        raw = splitByTransparent(imgEl, unify);
      }

      // 1) 先按需自动裁掉每帧四周的"背景"边距（紧凑包围盒）
      let processed = raw;
      if (trimMode === "alpha") {
        processed = autoTrimFrames(raw, { mode: "alpha", alphaThreshold: trimThreshold });
      } else if (trimMode === "bgColor") {
        processed = autoTrimFrames(raw, { mode: "bgColor", colorTolerance });
      }
      // 2) 再做尺寸统一（crop=取最小+居中裁；pad=取最大+居中补透明；off=保留各自尺寸）
      if (unifyMode === "pad") processed = unifyFrames(processed, vAlign);
      else if (unifyMode === "crop") processed = cropFramesToMin(processed, vAlign);

      setFrames(
        processed.map((frame) => ({
          id: _uid++,
          frame,
          selected: true,
          dx: 0,
          dy: 0,
        }))
      );
      setActiveIdx(0);
      setPlayIdx(0);
      const guessCols = mode === "grid" ? xCuts.length + 1 : Math.min(processed.length, 8);
      setLayoutCols(guessCols);
      setGridCols(guessCols);
      setStep(2);
    } catch (e) {
      setLoadErr(String(e));
    }
  };

  // ============ 帧操作 ============
  const selectedFrames = useMemo(
    () => frames.filter((f) => f.selected),
    [frames]
  );

  const toggleSelect = (id: number) =>
    setFrames((fs) =>
      fs.map((f) => (f.id === id ? { ...f, selected: !f.selected } : f))
    );

  const selectAll = (v: boolean) =>
    setFrames((fs) => fs.map((f) => ({ ...f, selected: v })));

  const deleteFrame = (id: number) =>
    setFrames((fs) => fs.filter((f) => f.id !== id));

  /** 单帧复制：在该帧之后插入一份独立副本 */
  const duplicateFrame = (id: number) =>
    setFrames((fs) => {
      const idx = fs.findIndex((f) => f.id === id);
      if (idx < 0) return fs;
      const src = fs[idx];
      const copy: FrameState = {
        id: _uid++,
        frame: cloneFrame(src.frame),
        selected: src.selected,
        dx: src.dx,
        dy: src.dy,
      };
      const out = [...fs];
      out.splice(idx + 1, 0, copy);
      return out;
    });

  const flipFrame = (id: number) =>
    setFrames((fs) =>
      fs.map((f) =>
        f.id === id ? { ...f, frame: flipFrameH(f.frame) } : f
      )
    );

  const [scalePct, setScalePct] = useState(100);

  /** 缩放当前 active 帧（按 scale 倍数） */
  const scaleCurrent = (scale: number) => {
    const cur = frames[activeIdx];
    if (!cur || scale === 1) return;
    setFrames((fs) =>
      fs.map((f) =>
        f.id === cur.id
          ? { ...f, frame: scaleFrame(f.frame, scale, smooth) }
          : f
      )
    );
    setScalePct(Math.round(scale * 100));
  };

  /** 批量缩放所有选中帧 */
  const batchScaleFrames = (scale: number) => {
    if (scale === 1) return;
    setFrames((fs) =>
      fs.map((f) =>
        f.selected ? { ...f, frame: scaleFrame(f.frame, scale, smooth) } : f
      )
    );
    setScalePct(Math.round(scale * 100));
  };

  /**
   * 把指定 id 的帧移到目标位置 to。
   * to=Infinity 表示移到末尾，0 表示移到开头；其它索引表示插入到 to 之前。
   */
  const moveFrameTo = (id: number, to: number) =>
    setFrames((fs) => {
      const from = fs.findIndex((f) => f.id === id);
      if (from < 0) return fs;
      let target = to;
      if (!Number.isFinite(target)) target = fs.length - 1;
      target = Math.max(0, Math.min(fs.length - 1, target));
      if (target === from) return fs;
      const out = [...fs];
      const [it] = out.splice(from, 1);
      // 因移除了 from，from 之后的目标索引要 -1
      const insertAt = target > from ? target : target;
      out.splice(insertAt, 0, it);
      return out;
    });

  /** 单帧位置：相对当前位置移动 step（-1 前移、+1 后移、-Infinity 首、+Infinity 末） */
  const moveActiveBy = (step: number) => {
    const cur = frames[activeIdx];
    if (!cur) return;
    let target: number;
    if (step === -Infinity) target = 0;
    else if (step === Infinity) target = frames.length - 1;
    else target = Math.max(0, Math.min(frames.length - 1, activeIdx + step));
    if (target === activeIdx) return;
    moveFrameTo(cur.id, target);
    setActiveIdx(target);
  };

  const nudge = (id: number, ddx: number, ddy: number) =>
    setFrames((fs) =>
      fs.map((f) =>
        f.id === id
          ? { ...f, frame: shiftFrame(f.frame, ddx, ddy), dx: f.dx + ddx, dy: f.dy + ddy }
          : f
      )
    );

  // —— 行/列选择 ——
  const rowsCount = Math.max(1, Math.ceil(frames.length / Math.max(1, gridCols)));

  const rowIndices = (r: number) => {
    const out: number[] = [];
    const start = r * gridCols;
    const end = Math.min(start + gridCols, frames.length);
    for (let i = start; i < end; i++) out.push(i);
    return out;
  };
  const colIndices = (c: number) => {
    const out: number[] = [];
    for (let r = 0; r < rowsCount; r++) {
      const i = r * gridCols + c;
      if (i < frames.length) out.push(i);
    }
    return out;
  };

  const setSelectedAt = (indices: number[], v: boolean) =>
    setFrames((fs) => {
      const set = new Set(indices);
      return fs.map((f, i) => (set.has(i) ? { ...f, selected: v } : f));
    });

  const toggleGroup = (indices: number[]) => {
    if (indices.length === 0) return;
    const allSelected = indices.every((i) => frames[i]?.selected);
    setSelectedAt(indices, !allSelected);
  };

  // —— 批量操作 ——
  const batchDelete = () => {
    setFrames((fs) => fs.filter((f) => !f.selected));
    setActiveIdx(0);
  };

  const batchDuplicate = () =>
    setFrames((fs) => {
      const out: FrameState[] = [];
      for (const f of fs) {
        out.push(f);
        if (f.selected) {
          out.push({
            id: _uid++,
            frame: cloneFrame(f.frame),
            selected: true,
            dx: f.dx,
            dy: f.dy,
          });
        }
      }
      return out;
    });

  const batchFlip = () =>
    setFrames((fs) =>
      fs.map((f) => (f.selected ? { ...f, frame: flipFrameH(f.frame) } : f))
    );

  const moveSelectedRows = (dr: -1 | 1) => {
    if (frames.length === 0) return;
    const selectedRows = new Set<number>();
    frames.forEach((f, i) => {
      if (f.selected) selectedRows.add(Math.floor(i / gridCols));
    });
    if (selectedRows.size === 0) return;

    const rowsArr: FrameState[][] = [];
    for (let r = 0; r < rowsCount; r++) {
      rowsArr.push(rowIndices(r).map((i) => frames[i]));
    }
    const ordered = Array.from(selectedRows).sort((a, b) => (dr === -1 ? a - b : b - a));
    for (const r of ordered) {
      const tgt = r + dr;
      if (tgt < 0 || tgt >= rowsCount) continue;
      if (selectedRows.has(tgt)) continue;
      const tmp = rowsArr[r];
      rowsArr[r] = rowsArr[tgt];
      rowsArr[tgt] = tmp;
    }
    setFrames(rowsArr.flat());
  };

  const moveSelectedCols = (dc: -1 | 1) => {
    if (frames.length === 0) return;
    const selectedCols = new Set<number>();
    frames.forEach((f, i) => {
      if (f.selected) selectedCols.add(i % gridCols);
    });
    if (selectedCols.size === 0) return;

    const grid: (FrameState | null)[][] = [];
    for (let r = 0; r < rowsCount; r++) {
      const row: (FrameState | null)[] = [];
      for (let c = 0; c < gridCols; c++) {
        const i = r * gridCols + c;
        row.push(i < frames.length ? frames[i] : null);
      }
      grid.push(row);
    }
    const ordered = Array.from(selectedCols).sort((a, b) => (dc === -1 ? a - b : b - a));
    for (const c of ordered) {
      const tgt = c + dc;
      if (tgt < 0 || tgt >= gridCols) continue;
      if (selectedCols.has(tgt)) continue;
      for (let r = 0; r < rowsCount; r++) {
        const tmp = grid[r][c];
        grid[r][c] = grid[r][tgt];
        grid[r][tgt] = tmp;
      }
    }
    const flat = grid.flat().filter((x): x is FrameState => x !== null);
    setFrames(flat);
  };

  const hasSelection = frames.some((f) => f.selected);

  // —— 拖拽 reorder ——
  const [dragId, setDragId] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  const onFrameDragStart = (e: React.DragEvent, id: number) => {
    setDragId(id);
    e.dataTransfer.effectAllowed = "move";
    // 必须 setData 否则 Firefox 不触发 dragover
    e.dataTransfer.setData("text/plain", String(id));
  };
  const onFrameDragOver = (e: React.DragEvent, idx: number) => {
    if (dragId == null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOverIdx !== idx) setDragOverIdx(idx);
  };
  const onFrameDrop = (e: React.DragEvent, idx: number) => {
    e.preventDefault();
    if (dragId == null) return;
    moveFrameTo(dragId, idx);
    // 拖拽后让被拖动帧成为 active
    setActiveIdx(idx);
    setDragId(null);
    setDragOverIdx(null);
  };
  const onFrameDragEnd = () => {
    setDragId(null);
    setDragOverIdx(null);
  };

  // ============ 预览动画 ============
  // 选帧时同步预览位置 + 重置缩放比例
  useEffect(() => {
    if (playing) return;
    const idxInSelected = selectedFrames.findIndex(
      (f) => f.id === frames[activeIdx]?.id
    );
    if (idxInSelected >= 0) setPlayIdx(idxInSelected);
  }, [activeIdx, frames, selectedFrames, playing]);

  // 切帧时重置等比例缩放滑块
  useEffect(() => {
    setScalePct(100);
  }, [activeIdx]);

  useEffect(() => {
    if (!playing || selectedFrames.length === 0) return;
    const timer = setInterval(() => {
      setPlayIdx((i) => (i + 1) % selectedFrames.length);
    }, 1000 / fps);
    return () => clearInterval(timer);
  }, [playing, fps, selectedFrames.length]);

  useEffect(() => {
    const canvas = previewRef.current;
    if (!canvas) return;
    const cur = selectedFrames[playIdx % Math.max(1, selectedFrames.length)];
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const fw = cur?.frame.width ?? 64;
    const fh = cur?.frame.height ?? 64;
    // 画布尺寸固定 = 帧尺寸 × 渲染倍率（不随缩放比例变化）
    canvas.width = fw * ZOOM;
    canvas.height = fh * ZOOM;
    ctx.imageSmoothingEnabled = smooth;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (cur) {
      const s = scalePct / 100;
      const sw = Math.round(fw * ZOOM * s);
      const sh = Math.round(fh * ZOOM * s);
      const dx = Math.round((fw * ZOOM - sw) / 2);
      const dy = Math.round((fh * ZOOM - sh) / 2);
      ctx.drawImage(cur.frame.canvas, dx, dy, sw, sh);
    }
  }, [playIdx, selectedFrames, scalePct, step]);

  // ============ 导出 ============
  const withBusy = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      setLoadErr(String(e));
    } finally {
      setBusy(null);
    }
  };

  const orderedSelected = () =>
    frames.filter((f) => f.selected).map((f) => f.frame);

  /** 将选中 Frame 的 canvas 转为 PNG Blob（供 MAGIC 上传时调用） */
  const getMagicBlobs = useCallback(async (): Promise<Blob[]> => {
    const sel = frames.filter((f) => f.selected);
    const blobs = await Promise.all(
      sel.map(
        (f) =>
          new Promise<Blob>((resolve) =>
            f.frame.canvas.toBlob((b) => resolve(b!), "image/png")
          )
      )
    );
    return blobs;
  }, [frames]);

  /** 当前导出用的 cell 尺寸选项；0 表示使用原始尺寸 */
  const cellOpts = { ...(cellSize > 0 ? { cellW: cellSize, cellH: cellSize } : {}), align: vAlign, smooth };

  const handleZip = () =>
    withBusy("zip", async () => {
      const blob = await exportFramesZip(orderedSelected(), "frame", cellOpts);
      downloadBlob(blob, `${sourceLabel || "sprite"}_frames.zip`);
    });

  const handleGif = () =>
    withBusy("gif", async () => {
      const blob = await exportFramesGif(
        orderedSelected(),
        1000 / fps,
        vAlign,
        cellSize > 0 ? { cellW: cellSize, cellH: cellSize, smooth } : { smooth }
      );
      downloadBlob(blob, `${sourceLabel || "sprite"}.gif`);
    });

  const handleRecombine = () =>
    withBusy("png", async () => {
      const blob = await recombineFrames(orderedSelected(), layoutCols, cellOpts);
      downloadBlob(blob, `${sourceLabel || "sprite"}_sheet.png`);
    });

  const handleSaveSheet = () =>
    withBusy("save", async () => {
      const blob = await recombineFrames(orderedSelected(), layoutCols, cellOpts);
      const file = new File([blob], "sheet.png", { type: "image/png" });
      await api.uploadAsset(file, "spritesheet:recombined");
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      queryClient.invalidateQueries({ queryKey: ["assets-grid"] });
    });

  // ============ 步骤可达性 ============
  const canStep2 = frames.length > 0;
  const canStep3 = frames.length > 0;
  const canStep4 = selectedFrames.length > 0;

  // ============ 渲染 ============
  return (
    <div className="max-w-[1500px] mx-auto space-y-4">
      {/* ============ 顶部步骤条 ============ */}
      <Stepper
        step={step}
        onJump={(s) => {
          if (s === 1) setStep(1);
          else if (s === 2 && canStep2) setStep(2);
          else if (s === 3 && canStep3) setStep(3);
          else if (s === 4 && canStep4) setStep(4);
        }}
        canStep2={canStep2}
        canStep3={canStep3}
        canStep4={canStep4}
        sourceSummary={
          imgEl
            ? t("spritesheet.summarySource", {
                label: sourceLabel || "sheet",
                w: imgEl.naturalWidth,
                h: imgEl.naturalHeight,
                n: frames.length,
              })
            : ""
        }
        framesSummary={t("spritesheet.summaryFrames", {
          n: selectedFrames.length,
          total: frames.length,
        })}
      />

      {/* 全局错误提示 */}
      {loadErr && (
        <div className="px-3 py-2 bg-[var(--red)]/10 border border-[var(--red)]/30 rounded-s text-[11.5px] text-[var(--red)]">
          ⚠️ {loadErr}
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={onLocalFile}
      />

      {/* ============ 步骤 1：选图 + 切分 ============ */}
      {step === 1 && (
        <div
          className="grid gap-5"
          style={{ gridTemplateColumns: "minmax(360px, 420px) 1fr" }}
        >
          {/* 左：源图 + 切分参数 */}
          <div className="space-y-4">
            <Card title={t("spritesheet.title")} subtitle={t("spritesheet.subtitle")}>
              {!imgUrl ? (
                <div
                  onClick={() => fileRef.current?.click()}
                  className="cursor-pointer rounded-l border-2 border-dashed border-line hover:border-[var(--acc)] hover:bg-[var(--acc-soft)]/40 transition-colors py-10 grid place-items-center text-center"
                >
                  <div className="mb-2 opacity-60 text-2xl">📤</div>
                  <div className="text-[12.5px] text-txt-1 font-medium mb-1">
                    {t("spritesheet.dropTitle")}
                  </div>
                  <div className="text-[11px] text-txt-3">{t("spritesheet.dropHint")}</div>
                </div>
              ) : (
                <div className="relative rounded-l border border-line overflow-hidden bg-bg-0">
                  <img
                    src={imgUrl}
                    alt=""
                    className="w-full max-h-[260px] object-contain pixelated"
                  />
                  {imgEl && (
                    <div className="absolute bottom-1 left-1 px-1.5 py-0.5 rounded bg-black/60 text-[9.5px] font-mono text-white">
                      {imgEl.naturalWidth}×{imgEl.naturalHeight}
                    </div>
                  )}
                </div>
              )}
              <div className="flex gap-2 mt-3">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => fileRef.current?.click()}
                  loading={uploadMut.isPending}
                >
                  📤 {t("spritesheet.upload")}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPickerOpen(true)}>
                  📚 {t("spritesheet.fromLibrary")}
                </Button>
              </div>
            </Card>

            {imgEl && (
              <Card title={t("spritesheet.splitTitle")}>
                <Field label={t("spritesheet.mode")}>
                  <Segment
                    items={[
                      { value: "grid", label: t("spritesheet.modeGrid") },
                      { value: "transparent", label: t("spritesheet.modeTransparent") },
                    ]}
                    value={mode}
                    onChange={(v) => setMode(v as SplitMode)}
                  />
                </Field>
                {mode === "grid" ? (
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={t("spritesheet.cols")}>
                      <SliderInput value={cols} onChange={setCols} min={1} max={64} />
                    </Field>
                    <Field label={t("spritesheet.rows")}>
                      <SliderInput value={rows} onChange={setRows} min={1} max={64} />
                    </Field>
                  </div>
                ) : (
                  <Field hint={t("spritesheet.transparentHint")}>
                    <Switch checked={unify} onChange={setUnify} label={t("spritesheet.unify")} />
                  </Field>
                )}
                {(mode === "transparent" && unify) || mode === "grid" ? (
                  <Field label={t("spritesheet.vAlign")}>
                    <Segment
                      items={[
                        { value: "bottom", label: t("spritesheet.alignBottom") },
                        { value: "middle", label: t("spritesheet.alignMiddle") },
                        { value: "top", label: t("spritesheet.alignTop") },
                      ]}
                      value={vAlign}
                      onChange={(v) => setVAlign(v as VAlign)}
                    />
                  </Field>
                ) : null}
                {mode === "grid" && (
                  <Field
                    label={t("spritesheet.unifyMode")}
                    hint={t(`spritesheet.unifyHint_${unifyMode}`)}
                  >
                    <Segment
                      items={[
                        { value: "crop", label: t("spritesheet.unifyCrop") },
                        { value: "pad", label: t("spritesheet.unifyPad") },
                        { value: "off", label: t("spritesheet.unifyOff") },
                      ]}
                      value={unifyMode}
                      onChange={(v) => setUnifyMode(v as Unify)}
                    />
                  </Field>
                )}
                {mode === "grid" && (
                  <Field
                    label={t("spritesheet.trimMode")}
                    hint={t(`spritesheet.trimHint_${trimMode}`)}
                  >
                    <Segment
                      items={[
                        { value: "alpha", label: t("spritesheet.trimAlpha") },
                        { value: "bgColor", label: t("spritesheet.trimBgColor") },
                        { value: "off", label: t("spritesheet.trimOff") },
                      ]}
                      value={trimMode}
                      onChange={(v) => setTrimMode(v as "off" | "alpha" | "bgColor")}
                    />
                    {trimMode === "alpha" && (
                      <label className="flex items-center gap-2 mt-2 text-[10.5px] text-txt-3">
                        α
                        <input
                          type="range"
                          min={0}
                          max={64}
                          value={trimThreshold}
                          onChange={(e) => setTrimThreshold(Number(e.target.value))}
                          className="flex-1 accent-[var(--acc)]"
                        />
                        <span className="w-8 text-right font-mono text-txt-1">
                          {trimThreshold}
                        </span>
                      </label>
                    )}
                    {trimMode === "bgColor" && (
                      <label className="flex items-center gap-2 mt-2 text-[10.5px] text-txt-3">
                        Δ
                        <input
                          type="range"
                          min={4}
                          max={120}
                          value={colorTolerance}
                          onChange={(e) => setColorTolerance(Number(e.target.value))}
                          className="flex-1 accent-[var(--acc)]"
                        />
                        <span className="w-8 text-right font-mono text-txt-1">
                          {colorTolerance}
                        </span>
                      </label>
                    )}
                  </Field>
                )}
                {mode === "grid" && (
                  <div className="text-[10.5px] text-txt-3 leading-relaxed -mt-1">
                    ℹ️ {t("spritesheet.dragHint")}
                  </div>
                )}
                <Button variant="primary" className="w-full mt-1" onClick={doSplit}>
                  ✂️ {t("spritesheet.doSplit")}
                </Button>
              </Card>
            )}
          </div>

          {/* 右：切分预览（实时按当前参数虚拟切分预览） */}
          <Card title={imgEl ? t("spritesheet.previewTitle") : t("spritesheet.framesTitle")}>
            {!imgEl ? (
              <div className="text-center py-20 text-txt-3 text-[12px]">
                {t("spritesheet.uploadFirst")}
              </div>
            ) : (
              <SplitPreview
                img={imgEl}
                mode={mode}
                xCuts={xCuts}
                yCuts={yCuts}
                onChangeXCuts={setXCuts}
                onChangeYCuts={setYCuts}
                onResetX={() =>
                  setXCuts(evenBoundaries(imgEl.naturalWidth, cols).slice(1, -1))
                }
                onResetY={() =>
                  setYCuts(evenBoundaries(imgEl.naturalHeight, rows).slice(1, -1))
                }
              />
            )}
          </Card>
        </div>
      )}

      {/* ============ 步骤 2：帧列表处理 ============ */}
      {step === 2 && frames.length > 0 && (
        <div
          className="grid gap-5 items-start"
          style={{ gridTemplateColumns: "1fr minmax(360px, 420px)" }}
        >
          {/* 左：帧列表（主操作区） */}
          <Card
            title={t("spritesheet.framesTitle")}
            actions={
              <div className="flex flex-wrap items-center gap-1.5">
                {/* 批量操作：紧凑图标按钮，hover 显 tooltip */}
                <IconBatch disabled={!hasSelection} onClick={batchDuplicate} title={t("spritesheet.batchDuplicate")}>📋</IconBatch>
                <IconBatch disabled={!hasSelection} onClick={batchFlip} title={t("spritesheet.batchFlip")}>↔️</IconBatch>
                <IconBatch disabled={!hasSelection} onClick={batchDelete} title={t("spritesheet.batchDelete")} danger>🗑️</IconBatch>
                <span className="mx-0.5 w-px h-4 bg-line" />
                <IconBatch disabled={!hasSelection} onClick={() => moveSelectedRows(-1)} title={t("spritesheet.moveUp")}>↑</IconBatch>
                <IconBatch disabled={!hasSelection} onClick={() => moveSelectedRows(1)} title={t("spritesheet.moveDown")}>↓</IconBatch>
                <IconBatch disabled={!hasSelection} onClick={() => moveSelectedCols(-1)} title={t("spritesheet.moveLeft")}>←</IconBatch>
                <IconBatch disabled={!hasSelection} onClick={() => moveSelectedCols(1)} title={t("spritesheet.moveRight")}>→</IconBatch>
                <span className="mx-0.5 w-px h-4 bg-line" />
                <button
                  onClick={() => selectAll(true)}
                  title={t("spritesheet.selectAll")}
                  className="h-7 px-2 rounded-s border border-line bg-bg-3 text-[11px] text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
                >
                  {t("spritesheet.selectAll")}
                </button>
                <button
                  onClick={() => selectAll(false)}
                  title={t("spritesheet.selectNone")}
                  className="h-7 px-2 rounded-s border border-line bg-bg-3 text-[11px] text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
                >
                  {t("spritesheet.selectNone")}
                </button>
                <span className="mx-0.5 w-px h-4 bg-line" />
                <label className="flex items-center gap-1.5 text-[11px] text-txt-2">
                  {t("spritesheet.gridCols")}
                  <input
                    type="number"
                    min={1}
                    max={32}
                    value={gridCols}
                    onChange={(e) =>
                      setGridCols(Math.max(1, Math.min(32, Number(e.target.value) || 1)))
                    }
                    className="w-12 h-7 px-1.5 rounded-s border border-line bg-bg-3 text-txt-1 text-[11px] text-center"
                  />
                </label>
              </div>
            }
          >
            {/* 已选计数 */}
            <div className="text-[11px] text-txt-2 mb-2">
              {t("spritesheet.selectedCount", {
                n: selectedFrames.length,
                total: frames.length,
              })}
            </div>

            {/* 列头（不滚动，吸顶） */}
            <div
              className="grid gap-2.5 mb-1.5 sticky top-0 z-10 bg-bg-2 py-1"
              style={{ gridTemplateColumns: `28px repeat(${gridCols}, minmax(0, 1fr))` }}
            >
              <div />
              {Array.from({ length: gridCols }).map((_, c) => {
                const idxs = colIndices(c);
                const allOn = idxs.length > 0 && idxs.every((i) => frames[i].selected);
                const someOn = idxs.some((i) => frames[i].selected);
                return (
                  <button
                    key={c}
                    title={t("spritesheet.selectCol")}
                    onClick={() => toggleGroup(idxs)}
                    className={`h-6 rounded-s text-[10px] font-mono border transition-colors ${
                      allOn
                        ? "border-[var(--acc)] bg-[var(--acc)] text-white"
                        : someOn
                        ? "border-[var(--acc)]/60 bg-[var(--acc)]/15 text-txt-1"
                        : "border-line bg-bg-3 text-txt-3 hover:text-txt-1 hover:border-[var(--acc)]/60"
                    }`}
                  >
                    C{c + 1}
                  </button>
                );
              })}
            </div>

            {/* 滚动容器：超过约 4 行后内部滚动，不撑全页 */}
            <div
              className="overflow-y-auto pr-1"
              style={{ maxHeight: "60vh" }}
            >
              {/* 行头 + 帧 */}
              <div
                className="grid gap-2.5"
                style={{ gridTemplateColumns: `28px repeat(${gridCols}, minmax(0, 1fr))` }}
              >
              {Array.from({ length: rowsCount }).map((_, r) => {
                const idxs = rowIndices(r);
                const allOn = idxs.length > 0 && idxs.every((i) => frames[i].selected);
                const someOn = idxs.some((i) => frames[i].selected);
                return (
                  <FragmentRow
                    key={r}
                    header={
                      <button
                        title={t("spritesheet.selectRow")}
                        onClick={() => toggleGroup(idxs)}
                        className={`h-full min-h-[40px] w-7 rounded-s text-[10px] font-mono border transition-colors flex items-center justify-center ${
                          allOn
                            ? "border-[var(--acc)] bg-[var(--acc)] text-white"
                            : someOn
                            ? "border-[var(--acc)]/60 bg-[var(--acc)]/15 text-txt-1"
                            : "border-line bg-bg-3 text-txt-3 hover:text-txt-1 hover:border-[var(--acc)]/60"
                        }`}
                      >
                        R{r + 1}
                      </button>
                    }
                  >
                    {Array.from({ length: gridCols }).map((_, c) => {
                      const idx = r * gridCols + c;
                      if (idx >= frames.length) return <div key={c} />;
                      const f = frames[idx];
                      return (
                        <div
                          key={f.id}
                          onClick={() => setActiveIdx(idx)}
                          draggable
                          onDragStart={(e) => onFrameDragStart(e, f.id)}
                          onDragOver={(e) => onFrameDragOver(e, idx)}
                          onDrop={(e) => onFrameDrop(e, idx)}
                          onDragEnd={onFrameDragEnd}
                          className={`group relative aspect-square rounded-s border-2 overflow-hidden cursor-grab active:cursor-grabbing transition-colors ${
                            activeIdx === idx
                              ? "border-[var(--acc)]"
                              : f.selected
                              ? "border-line"
                              : "border-transparent opacity-40"
                          } ${
                            dragOverIdx === idx && dragId !== null
                              ? "ring-2 ring-[var(--acc)] ring-offset-1 ring-offset-bg-2"
                              : ""
                          } ${dragId === f.id ? "opacity-30" : ""}`}
                          style={{
                            background:
                              "repeating-conic-gradient(#1c2230 0% 25%, #161b24 0% 50%) 50% / 12px 12px",
                          }}
                        >
                          <FrameThumb frame={f.frame} />
                          {/* 居中十字线辅助：crosshair 开关 → 全部常显；否则仅在选中（active）的那一帧显示 */}
                          {(crosshair || activeIdx === idx) && (
                            <div className="pointer-events-none absolute inset-0">
                              <div
                                className="absolute left-1/2 top-0 bottom-0 -translate-x-1/2"
                                style={{
                                  width: 1,
                                  background:
                                    "repeating-linear-gradient(to bottom, var(--red) 0 3px, transparent 3px 6px)",
                                  opacity: 0.85,
                                }}
                              />
                              <div
                                className="absolute top-1/2 left-0 right-0 -translate-y-1/2"
                                style={{
                                  height: 1,
                                  background:
                                    "repeating-linear-gradient(to right, var(--red) 0 3px, transparent 3px 6px)",
                                  opacity: 0.85,
                                }}
                              />
                            </div>
                          )}
                          <div className="absolute top-0.5 left-0.5 px-1 rounded bg-black/60 text-[9px] font-mono text-white">
                            {idx + 1}
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleSelect(f.id);
                            }}
                            className="absolute top-0.5 right-0.5 w-4 h-4 rounded grid place-items-center text-[9px]"
                            style={{
                              background: f.selected ? "var(--acc)" : "rgba(0,0,0,0.5)",
                              color: f.selected ? "#fff" : "var(--txt-3)",
                            }}
                          >
                            {f.selected ? <FaCheck size={10} /> : ""}
                          </button>
                          <div className="absolute inset-x-0 bottom-0 flex justify-center gap-1 py-0.5 bg-black/55 opacity-0 group-hover:opacity-100 transition-opacity">
                            <IconMini
                              title={t("spritesheet.duplicateFrame")}
                              onClick={(e) => {
                                e.stopPropagation();
                                duplicateFrame(f.id);
                              }}
                            >
                              📋
                            </IconMini>
                            <IconMini
                              title={t("spritesheet.flip")}
                              onClick={(e) => {
                                e.stopPropagation();
                                flipFrame(f.id);
                              }}
                            >
                              ↔️
                            </IconMini>
                            <IconMini
                              title={t("common.delete")}
                              onClick={(e) => {
                                e.stopPropagation();
                                deleteFrame(f.id);
                              }}
                            >
                              🗑️
                            </IconMini>
                          </div>
                        </div>
                      );
                    })}
                  </FragmentRow>
                );
              })}
            </div>
            </div>{/* /滚动容器 */}
          </Card>

          {/* 右：sticky 操作侧栏（预览 + 批量 + 微调 + 步骤导航） */}
          <div className="sticky top-0 space-y-3">
            <Card
              title={t("spritesheet.previewTitle")}
              actions={
                <Button
                  size="sm"
                  variant={playing ? "primary" : "outline"}
                  onClick={() => {
                    if (!playing) {
                      const idxInSelected = selectedFrames.findIndex(
                        (f) => f.id === frames[activeIdx]?.id
                      );
                      setPlayIdx(idxInSelected >= 0 ? idxInSelected : 0);
                    }
                    setPlaying((p) => !p);
                  }}
                >
                  {playing ? <FaPause size={14} /> : <FaPlay size={14} />}
                </Button>
              }
            >
              {/* 预览画布：始终居中适配，保证动画播放完整可视 */}
              <div
                className="grid place-items-center rounded-l border border-line overflow-hidden mb-3"
                style={{
                  width: "100%",
                  height: 240,
                  background: checker
                    ? "repeating-conic-gradient(#1c2230 0% 25%, #161b24 0% 50%) 50% / 24px 24px"
                    : "var(--bg-0)",
                }}
              >
                <div className="relative inline-block">
                  <canvas
                    ref={previewRef}
                    style={{
                      maxWidth: "100%",
                      maxHeight: 220,
                      imageRendering: "pixelated",
                      display: "block",
                    }}
                  />
                  {crosshair && (
                    <div className="pointer-events-none absolute inset-0">
                      <div
                        className="absolute left-1/2 top-0 bottom-0 -translate-x-1/2"
                        style={{
                          width: 1,
                          background:
                            "repeating-linear-gradient(to bottom, var(--red) 0 4px, transparent 4px 8px)",
                          opacity: 0.85,
                        }}
                      />
                      <div
                        className="absolute top-1/2 left-0 right-0 -translate-y-1/2"
                        style={{
                          height: 1,
                          background:
                            "repeating-linear-gradient(to right, var(--red) 0 4px, transparent 4px 8px)",
                          opacity: 0.85,
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* 控制：fps / checker */}
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-[11px] text-txt-2">
                  <span className="w-10 shrink-0 font-mono">{t("spritesheet.fps")}</span>
                  <input
                    type="range"
                    min={1}
                    max={24}
                    value={fps}
                    onChange={(e) => setFps(Number(e.target.value))}
                    className="flex-1 accent-[var(--acc)]"
                  />
                  <span className="w-5 text-right font-mono text-txt-1">{fps}</span>
                </label>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <Switch checked={checker} onChange={setChecker} label={t("spritesheet.checker")} />
                    <Switch checked={crosshair} onChange={setCrosshair} label={t("spritesheet.crosshair")} />
                  </div>
                  <div className="text-[11px] text-txt-3 font-mono">
                    {t("spritesheet.frameOf", {
                      cur: selectedFrames.length ? (playIdx % selectedFrames.length) + 1 : 0,
                      total: selectedFrames.length,
                    })}
                  </div>
                </div>

                {/* 当前帧微调 */}
                {frames[activeIdx] && (
                  <div className="pt-2.5 border-t border-line">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-[11px] text-txt-2">
                        {t("spritesheet.nudgeFrame", { n: activeIdx + 1 })}
                      </span>
                      <span className="text-[10.5px] text-txt-3 font-mono">
                        dx={frames[activeIdx].dx} dy={frames[activeIdx].dy}
                      </span>
                    </div>
                    {/* 第一行：方向微调 + 翻转 */}
                    <div className="flex items-center gap-1.5">
                      <NudgeBtn onClick={() => nudge(frames[activeIdx].id, -1, 0)}>←</NudgeBtn>
                      <NudgeBtn onClick={() => nudge(frames[activeIdx].id, 1, 0)}>→</NudgeBtn>
                      <NudgeBtn onClick={() => nudge(frames[activeIdx].id, 0, -1)}>↑</NudgeBtn>
                      <NudgeBtn onClick={() => nudge(frames[activeIdx].id, 0, 1)}>↓</NudgeBtn>
                      <button
                        onClick={() => flipFrame(frames[activeIdx].id)}
                        className="ml-auto px-2.5 h-7 rounded-s border border-line bg-bg-3 text-[11px] text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
                      >
                        ↔️ {t("spritesheet.flip")}
                      </button>
                    </div>
                    {/* 第二行：单帧位置移动（在帧序列中） */}
                    <div className="flex items-center gap-1.5 mt-1.5">
                      <span className="text-[10.5px] text-txt-3 mr-1">
                        {t("spritesheet.position")}
                      </span>
                      <PosBtn
                        onClick={() => moveActiveBy(-Infinity)}
                        title={t("spritesheet.moveToFirst")}
                      >
                        ⏮
                      </PosBtn>
                      <PosBtn
                        onClick={() => moveActiveBy(-1)}
                        title={t("spritesheet.movePrev")}
                      >
                        ◀
                      </PosBtn>
                      <PosBtn
                        onClick={() => moveActiveBy(1)}
                        title={t("spritesheet.moveNext")}
                      >
                        ▶
                      </PosBtn>
                      <PosBtn
                        onClick={() => moveActiveBy(Infinity)}
                        title={t("spritesheet.moveToLast")}
                      >
                        ⏭
                      </PosBtn>
                      <span className="ml-auto text-[10.5px] text-txt-3 font-mono">
                        {activeIdx + 1} / {frames.length}
                      </span>
                    </div>
                    {/* 第三行：单帧复制 / 删除 */}
                    <div className="flex items-center gap-1.5 mt-1.5">
                      <button
                        onClick={() => duplicateFrame(frames[activeIdx].id)}
                        title={t("spritesheet.duplicateFrame")}
                        className="flex-1 h-7 rounded-s border border-line bg-bg-3 text-[11px] text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
                      >
                        📋 {t("spritesheet.duplicateFrame")}
                      </button>
                      <button
                        onClick={() => {
                          const id = frames[activeIdx].id;
                          // 删除当前帧后保持 active 不越界
                          deleteFrame(id);
                          setActiveIdx((i) =>
                            Math.max(0, Math.min(i, frames.length - 2))
                          );
                        }}
                        title={t("spritesheet.deleteFrame")}
                        className="flex-1 h-7 rounded-s border border-[var(--red)]/40 bg-bg-3 text-[11px] text-[var(--red)] hover:bg-[var(--red)]/10 hover:border-[var(--red)]"
                      >
                        🗑️ {t("spritesheet.deleteFrame")}
                      </button>
                    </div>
                    {/* 第四行：等比例缩放 */}
                    <div className="pt-2 mt-2 border-t border-line">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[11px] text-txt-2">
                          {t("spritesheet.scaleTitle")}
                        </span>
                        <span className="text-[10.5px] text-txt-3 font-mono">
                          {frames[activeIdx].frame.width}×{frames[activeIdx].frame.height}
                        </span>
                      </div>
                      {/* 滑块 1%~200% */}
                      <div className="flex items-center gap-2">
                        <input
                          type="range"
                          min={1}
                          max={200}
                          step={1}
                          value={scalePct}
                          onChange={(e) => setScalePct(Number(e.target.value))}
                          className="flex-1 h-1 accent-[var(--acc)]"
                        />
                        <span className="text-[10.5px] text-txt-2 font-mono w-10 text-right tabular-nums">
                          {t("spritesheet.scalePercent", { p: scalePct })}
                        </span>
                      </div>
                      {/* 微调按钮：- / + / 复原 */}
                      <div className="flex items-center gap-1.5 mt-2">
                        <button
                          onClick={() => setScalePct((p) => Math.max(1, p - 5))}
                          title={t("spritesheet.scaleMinus")}
                          className="h-6 w-7 rounded-s text-[11px] border border-line bg-bg-3 text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
                        >
                          {t("spritesheet.scaleMinus")}
                        </button>
                        <button
                          onClick={() => setScalePct((p) => Math.min(200, p + 5))}
                          title={t("spritesheet.scalePlus")}
                          className="h-6 w-7 rounded-s text-[11px] border border-line bg-bg-3 text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
                        >
                          {t("spritesheet.scalePlus")}
                        </button>
                        <button
                          onClick={() => setScalePct(100)}
                          className="h-6 px-2.5 rounded-s text-[10px] border border-line bg-bg-3 text-txt-2 hover:text-txt-1 hover:border-[var(--acc)]"
                        >
                          {t("spritesheet.scaleReset")}
                        </button>
                        <button
                          onClick={() => scaleCurrent(scalePct / 100)}
                          className="ml-auto h-6 px-3 rounded-s text-[10px] border border-[var(--acc)]/50 bg-[var(--acc)]/10 text-txt-1 hover:bg-[var(--acc)]/20 hover:border-[var(--acc)]"
                        >
                          {t("spritesheet.scaleApplyTo", { n: activeIdx + 1 })}
                        </button>
                      </div>
                      {/* 批量应用 */}
                      {hasSelection && (
                        <button
                          onClick={() => batchScaleFrames(scalePct / 100)}
                          className="w-full mt-1.5 h-6 rounded-s text-[10px] border border-line bg-bg-3 text-txt-2 hover:text-txt-1 hover:border-[var(--acc)]"
                        >
                          {t("spritesheet.scaleApplySelected")}
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </Card>

            {/* 步骤导航 */}
            <div className="grid grid-cols-2 gap-2">
              <Button variant="ghost" onClick={() => setStep(1)}>
              ← {t("spritesheet.reSplit")}
              </Button>
              <Button variant="primary" disabled={!canStep3} onClick={() => setStep(3)}>
              {t("spritesheet.next")} →
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ============ 步骤 3：导出与下载 ============ */}
      {step === 3 && frames.length > 0 && (
        <div
          className="grid gap-5 items-start"
          style={{ gridTemplateColumns: "minmax(360px, 420px) 1fr" }}
        >
          {/* 左：参数与动作 */}
          <Card title={t("spritesheet.exportTitle")}>
            <div className="text-[11.5px] text-txt-2 mb-3">
              {t("spritesheet.selectedCount", {
                n: selectedFrames.length,
                total: frames.length,
              })}
            </div>

            {/* 单帧尺寸预设 */}
            <Field label={t("spritesheet.cellSize")} hint={t("spritesheet.cellSizeHint")}>
              <div className="grid grid-cols-5 gap-1.5">
                {[0, 32, 48, 64, 96, 128, 192, 256, 384, 512].map((s) => (
                  <button
                    key={s}
                    onClick={() => setCellSize(s)}
                    className={`h-7 rounded-s border text-[11px] transition-colors ${
                      cellSize === s
                        ? "border-[var(--acc)] bg-[var(--acc)]/15 text-txt-0"
                        : "border-line bg-bg-3 text-txt-2 hover:text-txt-0 hover:border-[var(--acc)]/60"
                    }`}
                  >
                    {s === 0 ? t("spritesheet.cellOriginal") : s}
                  </button>
                ))}
              </div>
              <label className="flex items-center gap-2 mt-2 text-[10.5px] text-txt-3">
                {t("spritesheet.cellCustom")}
                <input
                  type="number"
                  min={0}
                  max={2048}
                  value={cellSize}
                  onChange={(e) =>
                    setCellSize(Math.max(0, Math.min(2048, Number(e.target.value) || 0)))
                  }
                  className="w-16 h-6 px-1.5 rounded-s border border-line bg-bg-3 text-txt-1 text-[11px] text-center"
                />
                px
              </label>
            </Field>

            <Field label={t("spritesheet.layoutCols")}>
              <SliderInput value={layoutCols} onChange={setLayoutCols} min={1} max={64} />
            </Field>
            <Field label={t("spritesheet.vAlign")}>
              <Segment
                items={[
                  { value: "bottom", label: t("spritesheet.alignBottom") },
                  { value: "middle", label: t("spritesheet.alignMiddle") },
                  { value: "top", label: t("spritesheet.alignTop") },
                ]}
                value={vAlign}
                onChange={(v) => setVAlign(v as VAlign)}
              />
            </Field>

            <Field label={t("spritesheet.processingMode")}>
              <div className="flex rounded-s border border-line overflow-hidden">
                <button
                  onClick={() => setProcessingMode("pixel")}
                  className={`flex-1 h-7 text-[11px] transition-colors ${
                    processingMode === "pixel"
                      ? "bg-[var(--acc)] text-white"
                      : "bg-bg-3 text-txt-2 hover:text-txt-1"
                  }`}
                >
                  {t("spritesheet.modePixel")}
                </button>
                <button
                  onClick={() => setProcessingMode("smooth")}
                  className={`flex-1 h-7 text-[11px] transition-colors ${
                    processingMode === "smooth"
                      ? "bg-[var(--acc)] text-white"
                      : "bg-bg-3 text-txt-2 hover:text-txt-1"
                  }`}
                >
                  {t("spritesheet.modeSmooth")}
                </button>
              </div>
            </Field>

            {/* 资源处理 */}
            <div className="mt-3 pt-3 border-t border-line">
              <div className="text-[10.5px] text-txt-3 mb-2">{t("spritesheet.assetAction", "资源处理")}</div>
              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant="primary"
                  loading={busy === "save"}
                  onClick={handleSaveSheet}
                  title={t("spritesheet.saveTooltip")}
                  className="h-9"
                >
                  💾 {t("spritesheet.saveLibrary")}
                </Button>
                <DownloadMenu
                  busy={busy}
                  onZip={handleZip}
                  onGif={handleGif}
                  onPng={handleRecombine}
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-4 mt-4 border-t border-line">
              <Button variant="ghost" onClick={() => setStep(2)}>
              ← {t("spritesheet.prev")}
              </Button>
            </div>
          </Card>

          {/* 右：合成预览 */}
          <div className="flex flex-col gap-5">
            <Card
              title={t("spritesheet.recombine")}
              actions={
                <Button size="sm" variant="ghost" onClick={() => setPreviewLightbox(true)}>
                  🔍 {t("spritesheet.viewDetail")}
                </Button>
              }
            >
              <RecombinePreview
                frames={
                  cellSize > 0
                    ? fitFramesToCell(orderedSelected(), cellSize, cellSize, vAlign, smooth)
                    : orderedSelected()
                }
                cols={layoutCols}
                maxHeight={400}
                onOpen={() => setPreviewLightbox(true)}
              />
            </Card>

            {/* → 进入 MAGIC 处理 */}
            {canStep4 && (
              <div className="flex items-center justify-end">
                <Button variant="primary" onClick={() => setStep(4)}>
                  {t("spritesheet.toMagic", "MAGIC 超分辨率处理 →")}
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 大图详情：可拖动 + 滚轮缩放 */}
      {previewLightbox && (
        <Lightbox
          frames={
            cellSize > 0
              ? fitFramesToCell(orderedSelected(), cellSize, cellSize, vAlign, smooth)
              : orderedSelected()
          }
          cols={layoutCols}
          onClose={() => setPreviewLightbox(false)}
        />
      )}

      {/* ============ 步骤 4：MAGIC 超分辨率处理 ============ */}
      {step === 4 && selectedFrames.length > 0 && (
        <MagicStep
          getFrames={getMagicBlobs}
          label={sourceLabel || "sprite-sheet"}
          onBack={() => setStep(3)}
          t={t}
        />
      )}

      <AssetPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={(a) => setSource(a.uri, a.id)}
        filterType="image"
      />
    </div>
  );
}

// ====================== 步骤 4：MAGIC 超分辨率处理 ======================

const MAGIC_VARIANT_INFO: Record<string, { label: string; desc: string }> = {
  half:    { label: "MAGIC 1/2", desc: "画布为原尺寸 ½" },
  quarter: { label: "MAGIC 1/4", desc: "画布为原尺寸 ¼" },
  eighth:  { label: "MAGIC 1/8", desc: "画布为原尺寸 ⅛" },
};

function MagicStep({
  getFrames,
  label,
  onBack,
  t,
}: {
  getFrames: () => Promise<Blob[]>;
  label: string;
  onBack: () => void;
  t: (key: string, fallback?: string) => string;
}) {
  const queryClient = useQueryClient();
  const [resizeMode, setResizeMode] = useState<"hard" | "soft">("hard");
  const [gridCols, setGridCols] = useState(8);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{
    magic_id: string;
    frames_count: number;
    source_size: { width: number; height: number };
    resize_mode: string;
    upscale_available: boolean;
    variants: { key: string; label: string; scale: number; output_size: number[] | null }[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [variantImages, setVariantImages] = useState<Record<string, string>>({});
  const [saveBusy, setSaveBusy] = useState<Record<string, boolean>>({});
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const handleMagic = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setVariantImages({});

    try {
      const frames = await getFrames();
      if (frames.length === 0) throw new Error("没有可处理的帧");

      const formData = new FormData();
      formData.append("label", label);
      formData.append("resize_mode", resizeMode);
      for (let i = 0; i < frames.length; i++) {
        formData.append("frames", frames[i], `frame_${i.toString().padStart(4, "0")}.png`);
      }

      const resp = await fetch("/api/magic/process-upload", { method: "POST", body: formData });
      if (!resp.ok) {
        const detail = (await resp.json().catch(() => ({}))) as { detail?: string };
        throw new Error(detail.detail || `HTTP ${resp.status}`);
      }
      const data = await resp.json() as typeof result;
      if (!data) return;
      setResult(data);

      // 加载各变体第一帧预览
      if (data.magic_id && data.variants) {
        for (const v of data.variants) {
          try {
            const imgResp = await fetch(`/api/magic/${data.magic_id}/frames/${v.key}/frame_0000.png`);
            if (imgResp.ok) {
              const blob = await imgResp.blob();
              setVariantImages(prev => ({ ...prev, [v.key]: URL.createObjectURL(blob) }));
            }
          } catch { /* ignore */ }
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleDownloadZip = (variantKey: string) => {
    if (!result?.magic_id) return;
    const a = document.createElement("a");
    a.href = `/api/magic/${result.magic_id}/export/${variantKey}`;
    a.download = `magic-${variantKey}-frames.zip`;
    a.click();
  };

  const handleDownloadSheet = (variantKey: string) => {
    if (!result?.magic_id) return;
    const a = document.createElement("a");
    a.href = `/api/magic/${result.magic_id}/spritesheet/${variantKey}?columns=${gridCols}`;
    a.download = `magic-${variantKey}-sheet.png`;
    a.click();
  };

  const handleSaveToLibrary = async (variantKey: string) => {
    if (!result?.magic_id) return;
    setSaveBusy(prev => ({ ...prev, [variantKey]: true }));
    try {
      const resp = await fetch(`/api/magic/${result.magic_id}/save-to-library/${variantKey}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ columns: gridCols }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json() as { asset_id: string; uri: string; variant: string };
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      setSavedMsg(t("spritesheet.magicSaved", "已保存 MAGIC {{variant}} 合成图到素材库", { variant: data.variant }) || `已保存 MAGIC ${data.variant} 合成图到素材库`);
      setTimeout(() => setSavedMsg(null), 4000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaveBusy(prev => ({ ...prev, [variantKey]: false }));
    }
  };

  return (
    <div className="grid gap-5 items-start" style={{ gridTemplateColumns: "minmax(320px, 380px) 1fr" }}>
      {/* ====== 左：参数设置 ====== */}
      <Card title={t("spritesheet.magicSettings", "MAGIC 参数设置")}>
        {/* 缩放模式 */}
        <Field label={t("spritesheet.magicResizeMode", "缩放模式")}>
          <div className="space-y-2">
            <label className={`flex items-start gap-2 p-2.5 rounded-s border cursor-pointer transition-colors ${resizeMode === "hard" ? "border-[var(--acc)] bg-[var(--acc)]/10" : "border-line bg-bg-3"}`}>
              <input
                type="radio" name="magicStepResize" value="hard"
                checked={resizeMode === "hard"} onChange={() => setResizeMode("hard")}
                disabled={busy} className="mt-0.5"
              />
              <div>
                <span className="text-xs font-medium" style={{ color: resizeMode === "hard" ? "var(--acc)" : "var(--txt-1)" }}>
                  {t("spritesheet.magicHard", "硬 (像素边缘)")}
                </span>
                <p className="text-[10.5px] mt-0.5 text-txt-3">
                  {t("spritesheet.magicHardDesc", "最近邻缩小，保留硬朗像素边缘，适合像素风 Sprite 动画 / 点阵游戏素材")}
                </p>
              </div>
            </label>
            <label className={`flex items-start gap-2 p-2.5 rounded-s border cursor-pointer transition-colors ${resizeMode === "soft" ? "border-[var(--acc)] bg-[var(--acc)]/10" : "border-line bg-bg-3"}`}>
              <input
                type="radio" name="magicStepResize" value="soft"
                checked={resizeMode === "soft"} onChange={() => setResizeMode("soft")}
                disabled={busy} className="mt-0.5"
              />
              <div>
                <span className="text-xs font-medium" style={{ color: resizeMode === "soft" ? "var(--acc)" : "var(--txt-1)" }}>
                  {t("spritesheet.magicSoft", "软 (平滑抗锯齿)")}
                </span>
                <p className="text-[10.5px] mt-0.5 text-txt-3">
                  {t("spritesheet.magicSoftDesc", "BOX 缩小平滑边缘，适合需要柔和抗锯齿的现代风格插画素材")}
                </p>
              </div>
            </label>
          </div>
        </Field>

        {/* 合成每行帧数 */}
        <Field label={t("spritesheet.magicGridCols", "合成每行帧数")}>
          <SliderInput value={gridCols} onChange={setGridCols} min={1} max={64} />
        </Field>

        {/* MAGIC 按钮 */}
        <div className="mt-3">
          <button
            onClick={handleMagic}
            disabled={busy}
            className="w-full py-2 rounded-lg text-sm font-medium transition-all"
            style={{
              background: busy ? "var(--line)" : "#f59e0b",
              color: busy ? "var(--txt-3)" : "#fff",
              cursor: busy ? "not-allowed" : "pointer",
            }}
          >
            {busy ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" opacity=".3" />
                  <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" fill="none" />
                </svg>
                {t("spritesheet.magicProcessing", "MAGIC 处理中...")}
              </span>
            ) : (
              `✨ ${t("spritesheet.magicRun", "开始 MAGIC 处理")}`
            )}
          </button>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="mt-3 text-xs p-2 rounded" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444" }}>
            {error}
            <button onClick={() => setError(null)} className="ml-2 underline" style={{ color: "#ef4444" }}>关闭</button>
          </div>
        )}

        {/* 保存成功提示 */}
        {savedMsg && (
          <div className="mt-3 text-xs p-2 rounded" style={{ background: "rgba(34,197,94,0.1)", color: "#22c55e" }}>{savedMsg}</div>
        )}

        <div className="flex items-center justify-between pt-4 mt-4 border-t border-line">
          <Button variant="ghost" onClick={onBack}>
            ← {t("spritesheet.prev")}
          </Button>
          {result && (
            <span className="text-[11px] text-txt-3">
              {t("spritesheet.magicProcessed", "已处理 {{count}} 帧", { count: result.frames_count })}
            </span>
          )}
        </div>
      </Card>

      {/* ====== 右：结果展示 ====== */}
      <div>
        {result?.variants && result.variants.length > 0 ? (
          <div className="grid grid-cols-3 gap-3">
            {result.variants.map((v) => {
              const info = MAGIC_VARIANT_INFO[v.key] || { label: v.label, desc: "" };
              const imgUrl = variantImages[v.key];
              const saving = saveBusy[v.key];

              return (
                <div
                  key={v.key}
                  className="rounded-lg border p-3"
                  style={{ background: "var(--bg-2)", borderColor: "var(--line)" }}
                >
                  {/* 变体标签 */}
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold" style={{ color: "var(--txt-0)" }}>
                      {info.label}
                    </span>
                    <span className="text-[10px]" style={{ color: "var(--txt-3)" }}>
                      {info.desc}
                    </span>
                  </div>

                  {/* 预览 */}
                  <div
                    className="w-full aspect-square rounded flex items-center justify-center mb-2"
                    style={{ background: "repeating-conic-gradient(var(--bg-3) 0% 25%, transparent 0% 50%) 50% / 16px 16px" }}
                  >
                    {imgUrl ? (
                      <img
                        src={imgUrl}
                        alt={info.label}
                        className="max-w-full max-h-full object-contain"
                        style={{ imageRendering: resizeMode === "hard" ? "pixelated" : "auto" }}
                      />
                    ) : (
                      <span className="text-xs text-txt-3">-</span>
                    )}
                  </div>

                  {/* 输出尺寸 */}
                  {v.output_size && (
                    <div className="text-[10px] mb-2" style={{ color: "var(--txt-2)" }}>
                      {v.output_size[0]} × {v.output_size[1]}
                    </div>
                  )}

                  {/* 操作按钮 */}
                  <div className="space-y-1.5">
                    <button
                      onClick={() => handleDownloadZip(v.key)}
                      className="w-full py-1 rounded text-xs font-medium transition-colors"
                      style={{ background: "var(--bg-3)", color: "var(--txt-1)", border: "1px solid var(--line)" }}
                    >
                      {t("spritesheet.magicDownloadZip", "下载 ZIP")}
                    </button>
                    <button
                      onClick={() => handleDownloadSheet(v.key)}
                      className="w-full py-1 rounded text-xs font-medium transition-colors"
                      style={{ background: "var(--acc-soft)", color: "var(--acc)" }}
                    >
                      {t("spritesheet.magicDownloadSheet", "下载合成PNG")}
                    </button>
                    <button
                      onClick={() => handleSaveToLibrary(v.key)}
                      disabled={saving}
                      className="w-full py-1 rounded text-xs font-medium transition-colors"
                      style={{
                        background: saving ? "var(--line)" : "var(--green-soft, rgba(34,197,94,0.15))",
                        color: saving ? "var(--txt-3)" : "#22c55e",
                      }}
                    >
                      {saving ? t("spritesheet.magicSaving", "保存中...") : `💾 ${t("spritesheet.magicSaveLibrary", "保存到素材库")}`}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <Card title={t("spritesheet.magicResult", "MAGIC 处理结果")}>
            <div className="py-8 text-center text-xs text-txt-3">
              {busy
                ? t("spritesheet.magicWaiting", "正在处理中，请稍候...")
                : t("spritesheet.magicHint", "左侧设置参数后点击「开始 MAGIC 处理」，结果将显示在此处")}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}


// ====================== 子组件 ======================

function Stepper({
  step,
  onJump,
  canStep2,
  canStep3,
  canStep4,
  sourceSummary,
  framesSummary,
}: {
  step: Step;
  onJump: (s: Step) => void;
  canStep2: boolean;
  canStep3: boolean;
  canStep4: boolean;
  sourceSummary: string;
  framesSummary: string;
}) {
  const { t } = useTranslation();
  const items: { id: Step; label: string; hint: string; enabled: boolean; summary?: string }[] = [
    {
      id: 1,
      label: t("spritesheet.stepSource"),
      hint: t("spritesheet.stepHintSource"),
      enabled: true,
      summary: step > 1 ? sourceSummary : undefined,
    },
    {
      id: 2,
      label: t("spritesheet.stepFrames"),
      hint: t("spritesheet.stepHintFrames"),
      enabled: canStep2,
      summary: step > 2 ? framesSummary : undefined,
    },
    {
      id: 3,
      label: t("spritesheet.stepExport"),
      hint: t("spritesheet.stepHintExport"),
      enabled: canStep3,
    },
    {
      id: 4,
      label: t("spritesheet.stepMagic", "MAGIC"),
      hint: t("spritesheet.stepHintMagic", "超分辨率处理（按需）"),
      enabled: canStep4,
    },
  ];

  return (
    <div className="rounded-l border border-line bg-bg-2 p-3">
      <div className="grid grid-cols-4 gap-2">
        {items.map((it, i) => {
          const active = it.id === step;
          const done = it.id < step;
          const clickable = it.enabled;
          return (
            <button
              key={it.id}
              disabled={!clickable}
              onClick={() => clickable && onJump(it.id)}
              className={`relative text-left rounded-s border px-3 py-2.5 transition-colors ${
                active
                  ? "border-[var(--acc)] bg-[var(--acc)]/10"
                  : done
                  ? "border-line bg-bg-3 hover:border-[var(--acc)]/60"
                  : clickable
                  ? "border-line bg-bg-3 hover:border-[var(--acc)]/60"
                  : "border-line/40 bg-bg-3/40 cursor-not-allowed"
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`w-5 h-5 grid place-items-center rounded-full text-[11px] font-mono ${
                    active
                      ? "bg-[var(--acc)] text-white"
                      : done
                      ? "bg-[var(--green)]/80 text-white"
                      : "bg-bg-0 text-txt-3 border border-line"
                  }`}
                >
                  {done ? <FaCheck size={10} /> : i + 1}
                </span>
                <span
                  className={`text-[12.5px] font-medium ${
                    active ? "text-txt-0" : clickable ? "text-txt-1" : "text-txt-3"
                  }`}
                >
                  {it.label}
                </span>
              </div>
              <div className="mt-1 text-[10.5px] text-txt-3 line-clamp-1">
                {it.summary || it.hint}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * 步骤 1 右侧的"切分预览"：
 *  - grid 模式：在原图上画出可拖动的横/竖切分线；双击线 → 重置该线到均分位置
 *  - transparent 模式：仅显示原图（透明切结果要等真正切分后才知道）
 */
function SplitPreview({
  img,
  mode,
  xCuts,
  yCuts,
  onChangeXCuts,
  onChangeYCuts,
  onResetX,
  onResetY,
}: {
  img: HTMLImageElement;
  mode: SplitMode;
  xCuts: number[];
  yCuts: number[];
  onChangeXCuts: (v: number[]) => void;
  onChangeYCuts: (v: number[]) => void;
  onResetX: () => void;
  onResetY: () => void;
}) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoverLine, setHoverLine] = useState<
    | { axis: "x" | "y"; index: number }
    | null
  >(null);
  // 拖拽中状态用 ref 避免 mousemove 反复重建闭包
  const dragRef = useRef<{ axis: "x" | "y"; index: number } | null>(null);

  // 把画布像素坐标 → 原图像素坐标
  const W = img.naturalWidth;
  const H = img.naturalHeight;
  const maxW = 720;
  const scale = Math.min(1, maxW / W);
  const cw = Math.floor(W * scale);
  const ch = Math.floor(H * scale);

  // 在画布上绘制
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    c.width = cw;
    c.height = ch;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, cw, ch);
    ctx.drawImage(img, 0, 0, cw, ch);

    if (mode !== "grid") return;

    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    // 普通切线 + hover/drag 高亮
    xCuts.forEach((x, i) => {
      const isHi =
        (hoverLine && hoverLine.axis === "x" && hoverLine.index === i) ||
        (dragRef.current && dragRef.current.axis === "x" && dragRef.current.index === i);
      const px = Math.floor(x * scale) + 0.5;
      ctx.strokeStyle = isHi ? "rgba(96,165,250,1)" : "rgba(96,165,250,0.7)";
      ctx.lineWidth = isHi ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(px, 0);
      ctx.lineTo(px, ch);
      ctx.stroke();
    });
    yCuts.forEach((y, i) => {
      const isHi =
        (hoverLine && hoverLine.axis === "y" && hoverLine.index === i) ||
        (dragRef.current && dragRef.current.axis === "y" && dragRef.current.index === i);
      const py = Math.floor(y * scale) + 0.5;
      ctx.strokeStyle = isHi ? "rgba(96,165,250,1)" : "rgba(96,165,250,0.7)";
      ctx.lineWidth = isHi ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(0, py);
      ctx.lineTo(cw, py);
      ctx.stroke();
    });
    ctx.setLineDash([]);
  }, [img, mode, xCuts, yCuts, hoverLine, cw, ch, scale]);

  // —— 鼠标事件 ——
  /** 鼠标位置 → 画布坐标（处理 dpr/缩放） */
  const getPos = (e: React.MouseEvent | MouseEvent) => {
    const c = canvasRef.current!;
    const rect = c.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * cw;
    const y = ((e.clientY - rect.top) / rect.height) * ch;
    return { x, y };
  };

  /** 找最近的切分线（画布坐标），返回 axis/index/距离（像素） */
  const findNearestLine = (pxX: number, pxY: number): { axis: "x" | "y"; index: number; dist: number } | null => {
    const HIT = 6; // px 容差
    let best: { axis: "x" | "y"; index: number; dist: number } | null = null;
    for (let i = 0; i < xCuts.length; i++) {
      const d = Math.abs(xCuts[i] * scale - pxX);
      if (d <= HIT && (!best || d < best.dist)) best = { axis: "x", index: i, dist: d };
    }
    for (let i = 0; i < yCuts.length; i++) {
      const d = Math.abs(yCuts[i] * scale - pxY);
      if (d <= HIT && (!best || d < best.dist)) best = { axis: "y", index: i, dist: d };
    }
    return best;
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (mode !== "grid") return;
    const { x, y } = getPos(e);
    if (dragRef.current) return; // 拖拽中由全局 listener 处理
    setHoverLine(findNearestLine(x, y));
  };

  const onMouseDown = (e: React.MouseEvent) => {
    if (mode !== "grid") return;
    const { x, y } = getPos(e);
    const hit = findNearestLine(x, y);
    if (!hit) return;
    dragRef.current = { axis: hit.axis, index: hit.index };
    setHoverLine(hit);
    // 全局 listener，离开 canvas 也能继续拖
    const move = (ev: MouseEvent) => {
      const c = canvasRef.current;
      if (!c || !dragRef.current) return;
      const rect = c.getBoundingClientRect();
      const px = ((ev.clientX - rect.left) / rect.width) * cw;
      const py = ((ev.clientY - rect.top) / rect.height) * ch;
      const drag = dragRef.current;
      if (drag.axis === "x") {
        const next = [...xCuts];
        // 限制：不能超过相邻线，留 1px 间距
        const left = drag.index > 0 ? xCuts[drag.index - 1] + 1 : 1;
        const right = drag.index < xCuts.length - 1 ? xCuts[drag.index + 1] - 1 : W - 1;
        next[drag.index] = Math.max(left, Math.min(right, Math.round(px / scale)));
        onChangeXCuts(next);
      } else {
        const next = [...yCuts];
        const top = drag.index > 0 ? yCuts[drag.index - 1] + 1 : 1;
        const bot = drag.index < yCuts.length - 1 ? yCuts[drag.index + 1] - 1 : H - 1;
        next[drag.index] = Math.max(top, Math.min(bot, Math.round(py / scale)));
        onChangeYCuts(next);
      }
    };
    const up = () => {
      dragRef.current = null;
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  /** 双击线条 → 把它重置回均分位置 */
  const onDoubleClick = (e: React.MouseEvent) => {
    if (mode !== "grid") return;
    const { x, y } = getPos(e);
    const hit = findNearestLine(x, y);
    if (!hit) return;
    if (hit.axis === "x") {
      const n = xCuts.length + 1; // 段数
      const next = [...xCuts];
      next[hit.index] = Math.floor(((hit.index + 1) * W) / n);
      onChangeXCuts(next);
    } else {
      const n = yCuts.length + 1;
      const next = [...yCuts];
      next[hit.index] = Math.floor(((hit.index + 1) * H) / n);
      onChangeYCuts(next);
    }
  };

  const cursor =
    mode !== "grid"
      ? "default"
      : hoverLine
      ? hoverLine.axis === "x"
        ? "ew-resize"
        : "ns-resize"
      : "default";

  return (
    <div className="space-y-2">
      <div
        className="rounded-l border border-line overflow-auto bg-bg-0 grid place-items-center min-h-[400px]"
      >
        <canvas
          ref={canvasRef}
          onMouseMove={onMouseMove}
          onMouseLeave={() => !dragRef.current && setHoverLine(null)}
          onMouseDown={onMouseDown}
          onDoubleClick={onDoubleClick}
          style={{
            imageRendering: "pixelated",
            maxWidth: "100%",
            cursor,
            userSelect: "none",
          }}
        />
      </div>
      {mode === "grid" && (
        <div className="flex items-center justify-between text-[10.5px] text-txt-3">
          <span>
            {xCuts.length + 1} × {yCuts.length + 1} ={" "}
            <span className="text-txt-1 font-mono">
              {(xCuts.length + 1) * (yCuts.length + 1)}
            </span>{" "}
            {t("spritesheet.framesTitle")}
          </span>
          <span className="flex gap-1">
            <button
              onClick={onResetX}
              className="px-2 h-6 rounded-s border border-line bg-bg-3 text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
            >
              ↔ {t("spritesheet.resetCuts")}
            </button>
            <button
              onClick={onResetY}
              className="px-2 h-6 rounded-s border border-line bg-bg-3 text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
            >
              ↕ {t("spritesheet.resetCuts")}
            </button>
          </span>
        </div>
      )}
    </div>
  );
}

/** 步骤 3 的合成预览 */
function RecombinePreview({
  frames,
  cols,
  maxHeight = 400,
  onOpen,
}: {
  frames: Frame[];
  cols: number;
  maxHeight?: number;
  onOpen?: () => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  // 保留原始 sheet 尺寸用于显示
  const [sheetSize, setSheetSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const c = ref.current;
    if (!c || frames.length === 0) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const cellW = Math.max(...frames.map((f) => f.width));
    const cellH = Math.max(...frames.map((f) => f.height));
    const cc = Math.max(1, Math.floor(cols));
    const rr = Math.ceil(frames.length / cc);
    c.width = cellW * cc;
    c.height = cellH * rr;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, c.width, c.height);
    frames.forEach((f, i) => {
      const col = i % cc;
      const row = Math.floor(i / cc);
      const dx = col * cellW + Math.floor((cellW - f.width) / 2);
      const dy = row * cellH + (cellH - f.height);
      ctx.drawImage(f.canvas, dx, dy);
    });
    setSheetSize({ w: c.width, h: c.height });
  }, [frames, cols]);

  if (frames.length === 0) {
    return <div className="text-center py-20 text-txt-3 text-[12px]">—</div>;
  }

  return (
    <div className="space-y-2">
      <div
        className="rounded-l border border-line overflow-hidden grid place-items-center cursor-zoom-in"
        style={{
          background: "repeating-conic-gradient(#1c2230 0% 25%, #161b24 0% 50%) 50% / 24px 24px",
          maxHeight,
        }}
        onClick={onOpen}
      >
        <canvas
          ref={ref}
          style={{
            imageRendering: "pixelated",
            // 缩放显示（保持比例），不撑工作台
            maxWidth: "100%",
            maxHeight,
            width: "auto",
            height: "auto",
          }}
        />
      </div>
      {sheetSize && (
        <div className="text-[10.5px] text-txt-3 font-mono text-right">
          {sheetSize.w} × {sheetSize.h} px
        </div>
      )}
    </div>
  );
}

/** 下载格式菜单：点击展开 ZIP/GIF/PNG */
function DownloadMenu({
  busy,
  onZip,
  onGif,
  onPng,
}: {
  busy: string | null;
  onZip: () => void;
  onGif: () => void;
  onPng: () => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);
  const isBusy = busy === "zip" || busy === "gif" || busy === "png";
  return (
    <div ref={wrapRef} className="relative">
      <Button variant="outline" loading={isBusy} onClick={() => setOpen((o) => !o)}>
        ⬇️ {t("spritesheet.download")} ▾
      </Button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-48 rounded-s border border-line bg-bg-2 shadow-2xl z-30 overflow-hidden">
          <DLMenuItem onClick={() => { setOpen(false); onPng(); }} icon="🖼️" title={t("spritesheet.dlPng")} hint={t("spritesheet.dlPngHint")} />
          <DLMenuItem onClick={() => { setOpen(false); onZip(); }} icon="📦" title={t("spritesheet.dlZip")} hint={t("spritesheet.dlZipHint")} />
          <DLMenuItem onClick={() => { setOpen(false); onGif(); }} icon="🎬" title={t("spritesheet.dlGif")} hint={t("spritesheet.dlGifHint")} />
        </div>
      )}
    </div>
  );
}

function DLMenuItem({
  icon,
  title,
  hint,
  onClick,
}: {
  icon: string;
  title: string;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-2 hover:bg-[var(--acc)]/10 border-b border-line last:border-b-0"
    >
      <div className="flex items-center gap-2 text-[12px] text-txt-1">
        <span>{icon}</span>
        <span>{title}</span>
      </div>
      <div className="text-[10.5px] text-txt-3 mt-0.5 ml-6">{hint}</div>
    </button>
  );
}

/** 大图详情对话框：拖动平移 + 滚轮缩放 */
function Lightbox({
  frames,
  cols,
  onClose,
}: {
  frames: Frame[];
  cols: number;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragging = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c || frames.length === 0) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const cellW = Math.max(...frames.map((f) => f.width));
    const cellH = Math.max(...frames.map((f) => f.height));
    const cc = Math.max(1, Math.floor(cols));
    const rr = Math.ceil(frames.length / cc);
    c.width = cellW * cc;
    c.height = cellH * rr;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, c.width, c.height);
    frames.forEach((f, i) => {
      const col = i % cc;
      const row = Math.floor(i / cc);
      const dx = col * cellW + Math.floor((cellW - f.width) / 2);
      const dy = row * cellH + (cellH - f.height);
      ctx.drawImage(f.canvas, dx, dy);
    });
    setSize({ w: c.width, h: c.height });
    // 自适应初始缩放：让图最长边落在视窗 80% 内
    const fit = Math.min(window.innerWidth * 0.8 / c.width, window.innerHeight * 0.7 / c.height, 1);
    setZoom(fit > 0 ? fit : 1);
    setPan({ x: 0, y: 0 });
  }, [frames, cols]);

  // ESC 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = -e.deltaY;
    setZoom((z) => Math.max(0.05, Math.min(20, z * (delta > 0 ? 1.1 : 1 / 1.1))));
  };
  const onMouseDown = (e: React.MouseEvent) => {
    dragging.current = { sx: e.clientX, sy: e.clientY, ox: pan.x, oy: pan.y };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragging.current) return;
    setPan({
      x: dragging.current.ox + (e.clientX - dragging.current.sx),
      y: dragging.current.oy + (e.clientY - dragging.current.sy),
    });
  };
  const onMouseUp = () => {
    dragging.current = null;
  };
  const reset = () => {
    if (!size) return;
    const fit = Math.min(window.innerWidth * 0.8 / size.w, window.innerHeight * 0.7 / size.h, 1);
    setZoom(fit > 0 ? fit : 1);
    setPan({ x: 0, y: 0 });
  };

  return ReactDOM.createPortal(
    <div
      className="fixed inset-0 z-[100] grid place-items-center"
      style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(4px)" }}
      onWheel={onWheel}
    >
      {/* 顶栏 */}
      <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-1.5 rounded-l bg-bg-2 border border-line text-[11.5px] text-txt-1 z-10">
        {size && (
          <span className="font-mono text-txt-2">
            {size.w} × {size.h} · {Math.round(zoom * 100)}%
          </span>
        )}
        <button
          onClick={() => setZoom((z) => Math.max(0.05, z / 1.2))}
          className="px-2 h-6 rounded-s border border-line bg-bg-3 text-txt-1 hover:border-[var(--acc)]"
        >
          −
        </button>
        <button
          onClick={() => setZoom((z) => Math.min(20, z * 1.2))}
          className="px-2 h-6 rounded-s border border-line bg-bg-3 text-txt-1 hover:border-[var(--acc)]"
        >
          +
        </button>
        <button
          onClick={reset}
          className="px-2 h-6 rounded-s border border-line bg-bg-3 text-txt-1 hover:border-[var(--acc)]"
        >
          {t("spritesheet.fit")}
        </button>
      </div>

      {/* 关闭 */}
      <button
        onClick={onClose}
        className="absolute top-3 right-3 w-9 h-9 grid place-items-center rounded-full bg-bg-2 border border-line text-txt-1 hover:bg-bg-3 z-10"
        title={t("spritesheet.close")}
      >
        <IoClose size={18} />
      </button>

      {/* 画布容器 */}
      <div
        className="w-full h-full grid place-items-center overflow-hidden cursor-grab active:cursor-grabbing select-none"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        style={{
          background: "repeating-conic-gradient(#1c2230 0% 25%, #161b24 0% 50%) 50% / 32px 32px",
        }}
      >
        <canvas
          ref={canvasRef}
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: "center center",
            imageRendering: "pixelated",
            transition: dragging.current ? "none" : "transform 80ms ease-out",
          }}
        />
      </div>
    </div>,
    document.body
  );
}

function FrameThumb({ frame }: { frame: Frame }) {
  const ref = useRef<HTMLImageElement>(null);
  useEffect(() => {
    frame.canvas.toBlob((b) => {
      if (b && ref.current) ref.current.src = URL.createObjectURL(b);
    });
  }, [frame]);
  return <img ref={ref} alt="" className="w-full h-full object-contain pixelated" />;
}

function IconMini({
  children,
  onClick,
  title,
}: {
  children: React.ReactNode;
  onClick: (e: React.MouseEvent) => void;
  title?: string;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className="w-5 h-5 grid place-items-center rounded text-white text-[10px] hover:bg-white/20"
    >
      {children}
    </button>
  );
}

/** 单击型按钮：用于"位置移动"等不应自动连发的场景 */
function PosBtn({
  children,
  onClick,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="w-7 h-7 grid place-items-center rounded-s border border-line bg-bg-3 text-txt-1 hover:text-txt-0 hover:border-[var(--acc)] text-[12px] select-none"
    >
      {children}
    </button>
  );
}

/**
 * 方向微调按钮：点击 +1，按住后加速连续触发。
 * - 350ms 长按门槛 → 开始第一波重复（90ms/次）
 * - 持续按住 1200ms 后切换到高速档（40ms/次）
 * - 鼠标松开/离开按钮/失焦时停止
 */
function NudgeBtn({
  children,
  onClick,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title?: string;
}) {
  const onClickRef = useRef(onClick);
  onClickRef.current = onClick;
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);

  const stop = () => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const tick = () => {
    onClickRef.current();
    const elapsed = performance.now() - startedAtRef.current;
    const interval = elapsed > 1200 ? 40 : 90;
    timerRef.current = window.setTimeout(tick, interval);
  };

  const onPointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.button !== undefined && e.button !== 0) return; // 只响应左键
    e.currentTarget.setPointerCapture?.(e.pointerId);
    onClickRef.current(); // 立刻执行一次
    startedAtRef.current = performance.now();
    timerRef.current = window.setTimeout(tick, 350); // 长按门槛
  };

  return (
    <button
      title={title}
      onPointerDown={onPointerDown}
      onPointerUp={stop}
      onPointerLeave={stop}
      onPointerCancel={stop}
      onBlur={stop}
      // 阻止默认的 click → 避免 onPointerDown 已触发后再触发一次
      onClick={(e) => e.preventDefault()}
      className="w-7 h-7 grid place-items-center rounded-s border border-line bg-bg-3 text-txt-1 hover:text-txt-0 hover:border-[var(--acc)] text-[12px] select-none"
    >
      {children}
    </button>
  );
}

/** 紧凑图标按钮（帧列表 actions 工具条用） */
function IconBatch({
  children,
  onClick,
  title,
  disabled,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  title?: string;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`w-7 h-7 grid place-items-center rounded-s border text-[12px] transition-colors ${
        disabled
          ? "border-line/60 bg-bg-3/60 text-txt-3 cursor-not-allowed"
          : danger
          ? "border-[var(--red)]/40 bg-bg-3 text-[var(--red)] hover:bg-[var(--red)]/10 hover:border-[var(--red)]"
          : "border-line bg-bg-3 text-txt-1 hover:text-txt-0 hover:border-[var(--acc)]"
      }`}
    >
      {children}
    </button>
  );
}

/** display:contents 的行包装：把行头与该行的帧一起摊到外层 grid 上 */
function FragmentRow({
  header,
  children,
}: {
  header: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <>
      {header}
      {children}
    </>
  );
}
