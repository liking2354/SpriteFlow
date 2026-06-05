/**
 * Sprite Sheet 处理算法库（纯函数，无 UI 依赖）
 *
 * 移植并优化自 FrameRonin（systemchester/FrameRonin）的精灵表处理逻辑：
 *  - 网格均分切分（比例边界取整，避免累积误差）
 *  - 透明间隙自动切分（行/列投影扫描）
 *  - 帧统一尺寸（底部对齐 + 水平居中，逐像素拷贝避免插值模糊）
 *  - GIF 导出（gifenc，正确处理透明色）
 *  - ZIP 打包导出
 *  - 重组合为单张精灵表
 *
 * 全部基于浏览器原生 Canvas 2D，像素画场景统一关闭插值。
 */
import JSZip from "jszip";
// @ts-expect-error gifenc 无类型声明
import { GIFEncoder, quantize, applyPalette } from "gifenc";

export interface Frame {
  /** 帧画布（已是独立的一张图） */
  canvas: HTMLCanvasElement;
  width: number;
  height: number;
}

/** 把任意图片源加载成 HTMLImageElement */
export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("图片加载失败"));
    img.src = src;
  });
}

function newCanvas(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = Math.max(1, w);
  c.height = Math.max(1, h);
  return c;
}

function ctx2d(canvas: HTMLCanvasElement): CanvasRenderingContext2D {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("无法创建 canvas 2d 上下文");
  ctx.imageSmoothingEnabled = false; // 像素画不插值
  return ctx;
}

/**
 * 网格均分切分
 * 用比例边界取整，避免无法整除时最后一行/列缺像素
 */
export function splitGrid(
  img: HTMLImageElement,
  cols: number,
  rows: number
): Frame[] {
  const c = Math.max(1, Math.floor(cols));
  const r = Math.max(1, Math.floor(rows));
  const W = img.naturalWidth;
  const H = img.naturalHeight;
  const frames: Frame[] = [];

  for (let row = 0; row < r; row++) {
    for (let col = 0; col < c; col++) {
      const sx = Math.floor((col * W) / c);
      const ex = Math.floor(((col + 1) * W) / c);
      const sy = Math.floor((row * H) / r);
      const ey = Math.floor(((row + 1) * H) / r);
      const w = Math.max(1, ex - sx);
      const h = Math.max(1, ey - sy);
      const canvas = newCanvas(w, h);
      const ctx = ctx2d(canvas);
      ctx.drawImage(img, sx, sy, w, h, 0, 0, w, h);
      frames.push({ canvas, width: w, height: h });
    }
  }
  return frames;
}

/**
 * 计算指定列数/行数对应的"均分边界"列表（含 0 和 W/H 两端）。
 * 例如 cols=3, W=300 → [0, 100, 200, 300]
 */
export function evenBoundaries(total: number, segments: number): number[] {
  const n = Math.max(1, Math.floor(segments));
  const out: number[] = [];
  for (let i = 0; i <= n; i++) out.push(Math.floor((i * total) / n));
  return out;
}

/**
 * 自定义边界切分：xs / ys 必须是严格递增的边界数组（含两端 0 和 W/H）。
 * 切出的帧数 = (xs.length - 1) * (ys.length - 1)，行优先。
 * 适合宽高不能整除、需要手动对齐角色边的场景。
 */
export function splitGridByBoundaries(
  img: HTMLImageElement,
  xs: number[],
  ys: number[]
): Frame[] {
  const W = img.naturalWidth;
  const H = img.naturalHeight;
  const sx = sanitizeBoundaries(xs, W);
  const sy = sanitizeBoundaries(ys, H);
  const frames: Frame[] = [];
  for (let r = 0; r < sy.length - 1; r++) {
    for (let c = 0; c < sx.length - 1; c++) {
      const x0 = sx[c];
      const x1 = sx[c + 1];
      const y0 = sy[r];
      const y1 = sy[r + 1];
      const w = Math.max(1, x1 - x0);
      const h = Math.max(1, y1 - y0);
      const canvas = newCanvas(w, h);
      ctx2d(canvas).drawImage(img, x0, y0, w, h, 0, 0, w, h);
      frames.push({ canvas, width: w, height: h });
    }
  }
  return frames;
}

/** 规整边界数组：必含 0 和 total，严格递增、整数、相邻间距 ≥ 1 */
function sanitizeBoundaries(arr: number[], total: number): number[] {
  const set = new Set<number>();
  set.add(0);
  set.add(total);
  for (const v of arr) {
    const x = Math.round(v);
    if (x > 0 && x < total) set.add(x);
  }
  const sorted = Array.from(set).sort((a, b) => a - b);
  // 强制相邻间距 ≥ 1（去重已保证；这里保留作为冗余保险）
  return sorted;
}

// ---------------- 透明间隙切分 ----------------

function findTransparentRows(data: Uint8ClampedArray, width: number, height: number): number[] {
  const rows: number[] = [];
  for (let y = 0; y < height; y++) {
    let allTransparent = true;
    for (let x = 0; x < width; x++) {
      if (data[(y * width + x) * 4 + 3] !== 0) {
        allTransparent = false;
        break;
      }
    }
    if (allTransparent) rows.push(y);
  }
  return rows;
}

function findTransparentCols(
  data: Uint8ClampedArray,
  width: number,
  y0: number,
  y1: number
): number[] {
  const cols: number[] = [];
  for (let x = 0; x < width; x++) {
    let allTransparent = true;
    for (let y = y0; y < y1; y++) {
      if (data[(y * width + x) * 4 + 3] !== 0) {
        allTransparent = false;
        break;
      }
    }
    if (allTransparent) cols.push(x);
  }
  return cols;
}

function getRuns(arr: number[]): [number, number][] {
  if (arr.length === 0) return [];
  const runs: [number, number][] = [];
  let s = arr[0];
  let e = s;
  for (let i = 1; i < arr.length; i++) {
    if (arr[i] === e + 1) e = arr[i];
    else {
      runs.push([s, e]);
      s = arr[i];
      e = s;
    }
  }
  runs.push([s, e]);
  return runs;
}

function gapsFromRuns(runs: [number, number][], total: number): [number, number][] {
  if (runs.length === 0) return [[0, total - 1]];
  const regions: [number, number][] = [];
  regions.push([0, runs[0][0] - 1]);
  for (let i = 0; i < runs.length - 1; i++) {
    regions.push([runs[i][1] + 1, runs[i + 1][0] - 1]);
  }
  regions.push([runs[runs.length - 1][1] + 1, total - 1]);
  return regions.filter(([a, b]) => a <= b);
}

/**
 * 透明间隙自动切分
 * 先用全透明行把图切成横向条带，再在每条带内用全透明列切出单帧。
 * 适用于帧之间有清晰透明分隔的精灵表。
 *
 * @param unify 是否把所有帧统一到最大尺寸（底部对齐 + 水平居中）
 */
export function splitByTransparent(
  img: HTMLImageElement,
  unify = true
): Frame[] {
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  const src = newCanvas(w, h);
  const sctx = ctx2d(src);
  sctx.drawImage(img, 0, 0);
  const data = sctx.getImageData(0, 0, w, h).data;

  const rowRegions = gapsFromRuns(getRuns(findTransparentRows(data, w, h)), h);
  const rects: { x: number; y: number; w: number; h: number }[] = [];
  for (const [y0, y1] of rowRegions) {
    const rowHeight = y1 - y0 + 1;
    if (rowHeight <= 0) continue;
    const colRegions = gapsFromRuns(getRuns(findTransparentCols(data, w, y0, y1 + 1)), w);
    for (const [x0, x1] of colRegions) {
      const colWidth = x1 - x0 + 1;
      if (colWidth <= 0) continue;
      rects.push({ x: x0, y: y0, w: colWidth, h: rowHeight });
    }
  }

  if (rects.length === 0) throw new Error("未找到可拆分区域（图片需有透明分隔）");

  if (!unify) {
    return rects.map((rc) => {
      const canvas = newCanvas(rc.w, rc.h);
      ctx2d(canvas).drawImage(src, rc.x, rc.y, rc.w, rc.h, 0, 0, rc.w, rc.h);
      return { canvas, width: rc.w, height: rc.h };
    });
  }

  // 统一尺寸：底部对齐 + 水平居中，逐像素拷贝避免插值
  const maxW = Math.max(...rects.map((r) => r.w));
  const maxH = Math.max(...rects.map((r) => r.h));
  const srcData = sctx.getImageData(0, 0, w, h);

  return rects.map((rc) => {
    const canvas = newCanvas(maxW, maxH);
    const octx = ctx2d(canvas);
    const out = octx.createImageData(maxW, maxH);
    const padTop = maxH - rc.h;
    const padLeft = Math.floor((maxW - rc.w) / 2);
    for (let dy = 0; dy < rc.h; dy++) {
      for (let dx = 0; dx < rc.w; dx++) {
        const si = ((rc.y + dy) * w + (rc.x + dx)) * 4;
        const di = ((padTop + dy) * maxW + (padLeft + dx)) * 4;
        out.data[di] = srcData.data[si];
        out.data[di + 1] = srcData.data[si + 1];
        out.data[di + 2] = srcData.data[si + 2];
        out.data[di + 3] = srcData.data[si + 3];
      }
    }
    octx.putImageData(out, 0, 0);
    return { canvas, width: maxW, height: maxH };
  });
}

// ---------------- 帧变换 ----------------

/** 深拷贝一帧（独立 canvas，互不影响） */
export function cloneFrame(frame: Frame): Frame {
  const c = newCanvas(frame.width, frame.height);
  ctx2d(c).drawImage(frame.canvas, 0, 0);
  return { canvas: c, width: frame.width, height: frame.height };
}

/** 水平翻转一帧 */
export function flipFrameH(frame: Frame): Frame {
  const c = newCanvas(frame.width, frame.height);
  const ctx = ctx2d(c);
  ctx.translate(frame.width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(frame.canvas, 0, 0);
  return { canvas: c, width: frame.width, height: frame.height };
}

/** 应用逐帧偏移（dx/dy 像素平移，超出部分裁掉，空出部分透明） */
export function shiftFrame(frame: Frame, dx: number, dy: number): Frame {
  if (dx === 0 && dy === 0) return frame;
  const c = newCanvas(frame.width, frame.height);
  ctx2d(c).drawImage(frame.canvas, dx, dy);
  return { canvas: c, width: frame.width, height: frame.height };
}

/**
 * 把所有帧统一到相同尺寸（取最大宽高）
 * @param align 垂直对齐：bottom 适合站立角色，middle 适合居中物件
 */
export function unifyFrames(
  frames: Frame[],
  align: "bottom" | "middle" | "top" = "bottom"
): Frame[] {
  if (frames.length === 0) return [];
  const maxW = Math.max(...frames.map((f) => f.width));
  const maxH = Math.max(...frames.map((f) => f.height));
  return frames.map((f) => {
    const c = newCanvas(maxW, maxH);
    const ctx = ctx2d(c);
    const padLeft = Math.floor((maxW - f.width) / 2);
    let padTop = 0;
    if (align === "bottom") padTop = maxH - f.height;
    else if (align === "middle") padTop = Math.floor((maxH - f.height) / 2);
    ctx.drawImage(f.canvas, padLeft, padTop);
    return { canvas: c, width: maxW, height: maxH };
  });
}

/**
 * 自动裁掉一帧四周的"背景"边距（紧凑包围盒）
 *
 * @param opts.mode "alpha"=按 alpha 阈值（适合 PNG 透明）；
 *                  "bgColor"=按颜色与背景色的相近度（适合摄影/JPEG 深色或白色背景）
 * @param opts.alphaThreshold alpha <= 该值视为"透明"，默认 8
 * @param opts.bgColor 背景色 [r,g,b]，省略时取四角像素中位数自动估计
 * @param opts.colorTolerance 颜色容差（0~441，欧氏距离）；越大裁得越激进。默认 32
 */
export function trimTransparent(
  frame: Frame,
  opts: {
    mode?: "alpha" | "bgColor";
    alphaThreshold?: number;
    bgColor?: [number, number, number];
    colorTolerance?: number;
  } = {}
): Frame {
  const mode = opts.mode ?? "alpha";
  const alphaTh = opts.alphaThreshold ?? 8;
  const colorTol = opts.colorTolerance ?? 32;

  const w = frame.width;
  const h = frame.height;
  const ctx = ctx2d(frame.canvas);
  const data = ctx.getImageData(0, 0, w, h).data;

  // 自动估计背景色：四个角的中位数（rgb 各通道分别取）
  let bg: [number, number, number] = opts.bgColor ?? autoDetectBgColor(data, w, h);
  const tol2 = colorTol * colorTol;

  /** 像素是否算"内容（非背景）" */
  const isContent = (idx: number): boolean => {
    const a = data[idx + 3];
    if (mode === "alpha") return a > alphaTh;
    // bgColor 模式：alpha 太低也直接当背景
    if (a <= 8) return false;
    const dr = data[idx] - bg[0];
    const dg = data[idx + 1] - bg[1];
    const db = data[idx + 2] - bg[2];
    return dr * dr + dg * dg + db * db > tol2;
  };

  let top = h;
  let bottom = -1;
  let left = w;
  let right = -1;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (isContent((y * w + x) * 4)) {
        if (y < top) top = y;
        if (y > bottom) bottom = y;
        if (x < left) left = x;
        if (x > right) right = x;
      }
    }
  }
  // 整张全是"背景" → 返回 1×1 透明帧（占位）
  if (right < 0 || bottom < 0) {
    const c = newCanvas(1, 1);
    return { canvas: c, width: 1, height: 1 };
  }
  const tw = right - left + 1;
  const th = bottom - top + 1;
  const c = newCanvas(tw, th);
  ctx2d(c).drawImage(frame.canvas, left, top, tw, th, 0, 0, tw, th);
  return { canvas: c, width: tw, height: th };
}

/** 自动估计背景色：取四个角 + 四个中点像素的 rgb 中位数 */
function autoDetectBgColor(
  data: Uint8ClampedArray,
  w: number,
  h: number
): [number, number, number] {
  const samples: [number, number, number][] = [];
  const pts = [
    [0, 0],
    [w - 1, 0],
    [0, h - 1],
    [w - 1, h - 1],
    [Math.floor(w / 2), 0],
    [Math.floor(w / 2), h - 1],
    [0, Math.floor(h / 2)],
    [w - 1, Math.floor(h / 2)],
  ];
  for (const [x, y] of pts) {
    const i = (y * w + x) * 4;
    samples.push([data[i], data[i + 1], data[i + 2]]);
  }
  // 各通道取中位数，避免角落异常像素
  const med = (arr: number[]) => {
    const sorted = [...arr].sort((a, b) => a - b);
    return sorted[Math.floor(sorted.length / 2)];
  };
  return [
    med(samples.map((s) => s[0])),
    med(samples.map((s) => s[1])),
    med(samples.map((s) => s[2])),
  ];
}

/** 批量 trim：每帧独立按统一参数去掉四周背景边距 */
export function autoTrimFrames(
  frames: Frame[],
  opts: Parameters<typeof trimTransparent>[1] = {}
): Frame[] {
  return frames.map((f) => trimTransparent(f, opts));
}

/**
 * 把所有帧统一到相同尺寸（取最小宽高）—— 居中裁剪模式
 * 水平方向以中心对齐裁剪两侧多余；
 * 垂直方向按 align：bottom 裁顶部、top 裁底部、middle 上下对半裁。
 * 适合"宽度不一致但内容居中（如三视图角色）"，结果整齐且画面可被等距裁掉边缘空白。
 */
export function cropFramesToMin(
  frames: Frame[],
  align: "bottom" | "middle" | "top" = "bottom"
): Frame[] {
  if (frames.length === 0) return [];
  const minW = Math.min(...frames.map((f) => f.width));
  const minH = Math.min(...frames.map((f) => f.height));
  return frames.map((f) => {
    const c = newCanvas(minW, minH);
    const ctx = ctx2d(c);
    const sx = Math.floor((f.width - minW) / 2);
    let sy = 0;
    if (align === "bottom") sy = f.height - minH;
    else if (align === "middle") sy = Math.floor((f.height - minH) / 2);
    ctx.drawImage(f.canvas, sx, sy, minW, minH, 0, 0, minW, minH);
    return { canvas: c, width: minW, height: minH };
  });
}

// ---------------- 导出 ----------------

/**
 * 将一帧 fit 到目标 cellW × cellH 单元格里（保持比例 + 居中 + align 垂直对齐 + 透明背景）
 * 不放大像素：若帧本身就比目标格子小，仅居中放置（不被拉模糊）；
 * 若帧大于目标格子，按比例缩小（最近邻，保持像素画清晰）。
 */
export function fitFrameToCell(
  frame: Frame,
  cellW: number,
  cellH: number,
  align: "bottom" | "middle" | "top" = "bottom"
): Frame {
  const c = newCanvas(cellW, cellH);
  const ctx = ctx2d(c);
  const sx = frame.width / cellW;
  const sy = frame.height / cellH;
  const s = Math.max(sx, sy, 1); // ≥1 表示需要缩小；<1 表示帧更小，则不放大保持原尺寸
  const drawW = Math.round(frame.width / s);
  const drawH = Math.round(frame.height / s);
  const dx = Math.floor((cellW - drawW) / 2);
  let dy = 0;
  if (align === "bottom") dy = cellH - drawH;
  else if (align === "middle") dy = Math.floor((cellH - drawH) / 2);
  ctx.drawImage(frame.canvas, 0, 0, frame.width, frame.height, dx, dy, drawW, drawH);
  return { canvas: c, width: cellW, height: cellH };
}

/** 批量 fit：保证所有帧都是统一的 cellW×cellH */
export function fitFramesToCell(
  frames: Frame[],
  cellW: number,
  cellH: number,
  align: "bottom" | "middle" | "top" = "bottom"
): Frame[] {
  return frames.map((f) => fitFrameToCell(f, cellW, cellH, align));
}

function frameToBlob(frame: Frame): Promise<Blob> {
  return new Promise((resolve, reject) => {
    frame.canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("导出 PNG 失败"))),
      "image/png"
    );
  });
}

/** 导出选定帧为 ZIP（可选 cellSize 强制每张图统一尺寸） */
export async function exportFramesZip(
  frames: Frame[],
  baseName = "frame",
  opts: { cellW?: number; cellH?: number; align?: "bottom" | "middle" | "top" } = {}
): Promise<Blob> {
  const target =
    opts.cellW && opts.cellH
      ? fitFramesToCell(frames, opts.cellW, opts.cellH, opts.align ?? "bottom")
      : frames;
  const zip = new JSZip();
  for (let i = 0; i < target.length; i++) {
    const blob = await frameToBlob(target[i]);
    zip.file(`${baseName}_${String(i).padStart(3, "0")}.png`, blob);
  }
  return zip.generateAsync({ type: "blob" });
}

/**
 * 导出帧为 GIF（透明背景）
 * 注意：GIF 协议本身只支持 256 色 + 1 位 alpha，对真人照片/渐变背景会出现明显色块/边缘锯齿，
 *       这是格式限制，无法通过参数完全消除。要追求高保真请用 ZIP（PNG）或 APNG/WebP。
 *
 * @param delayMs 每帧延迟（ms）
 * @param align 垂直对齐
 * @param opts.cellW/cellH 强制目标尺寸（先 fit 再编码，确保清晰度上限）
 */
export async function exportFramesGif(
  frames: Frame[],
  delayMs = 100,
  align: "bottom" | "middle" | "top" = "bottom",
  opts: { cellW?: number; cellH?: number } = {}
): Promise<Blob> {
  if (frames.length === 0) throw new Error("没有可导出的帧");
  const unified =
    opts.cellW && opts.cellH
      ? fitFramesToCell(frames, opts.cellW, opts.cellH, align)
      : unifyFrames(frames, align);
  const maxW = unified[0].width;
  const maxH = unified[0].height;

  const gif = GIFEncoder();
  for (const f of unified) {
    const ctx = ctx2d(f.canvas);
    const { data } = ctx.getImageData(0, 0, maxW, maxH);
    const palette = quantize(data, 255, {
      format: "rgba4444",
      oneBitAlpha: 128,
      clearAlpha: true,
      clearAlphaThreshold: 128,
    });
    const index = applyPalette(data, palette, "rgba4444");
    const transIdx = palette.findIndex((c: number[]) => c[3] === 0);

    let finalPalette: number[][];
    let finalIndex: Uint8Array;
    let transparentIndex: number;
    if (transIdx >= 0) {
      finalPalette = [...palette];
      finalIndex = index;
      transparentIndex = transIdx;
    } else {
      finalPalette = [[0, 0, 0, 0], ...palette];
      finalIndex = new Uint8Array(index.length);
      for (let j = 0; j < data.length; j += 4) {
        finalIndex[j / 4] = data[j + 3] < 128 ? 0 : index[j / 4] + 1;
      }
      transparentIndex = 0;
    }
    gif.writeFrame(finalIndex, maxW, maxH, {
      palette: finalPalette,
      delay: delayMs,
      transparent: true,
      transparentIndex,
    });
  }
  gif.finish();
  return new Blob([gif.bytes()], { type: "image/gif" });
}

/**
 * 把帧重新拼合成一张精灵表 PNG
 * @param layoutCols 每行放几帧
 * @param opts.cellW/cellH 强制单格尺寸（先 fit 再拼合）
 */
export async function recombineFrames(
  frames: Frame[],
  layoutCols: number,
  opts: { cellW?: number; cellH?: number; align?: "bottom" | "middle" | "top" } = {}
): Promise<Blob> {
  if (frames.length === 0) throw new Error("没有可合成的帧");
  const target =
    opts.cellW && opts.cellH
      ? fitFramesToCell(frames, opts.cellW, opts.cellH, opts.align ?? "bottom")
      : frames;
  const cols = Math.max(1, Math.floor(layoutCols));
  const rows = Math.ceil(target.length / cols);
  const cellW = Math.max(...target.map((f) => f.width));
  const cellH = Math.max(...target.map((f) => f.height));

  const sheet = newCanvas(cellW * cols, cellH * rows);
  const ctx = ctx2d(sheet);
  target.forEach((f, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const dx = col * cellW + Math.floor((cellW - f.width) / 2);
    const dy = row * cellH + (cellH - f.height);
    ctx.drawImage(f.canvas, dx, dy);
  });

  return new Promise((resolve, reject) => {
    sheet.toBlob((b) => (b ? resolve(b) : reject(new Error("合成失败"))), "image/png");
  });
}

/** 触发浏览器下载 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
