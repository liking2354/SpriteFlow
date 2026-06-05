#!/usr/bin/env node
/**
 * scripts/fetch-imgly-models.mjs
 *
 * 一次性把 @imgly/background-removal 所需的模型/WASM 下载到 web/public/imgly/
 * 让前端编辑器在完全无外网的环境也能跑一键抠图。
 *
 * 默认只下载：
 *  - /models/isnet_quint8        ← 默认模型，质量+体积均衡（~22MB）
 *  - /onnxruntime-web/*.wasm/.mjs ← 推理运行时（~12MB）
 * 总计约 76 MB（22 个内容寻址 chunk）。
 *
 * 用法：
 *   pnpm fetch:imgly
 *
 * 强制重新下载：
 *   pnpm fetch:imgly --force
 */
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import https from "node:https";
import http from "node:http";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, "..");

// imgly 包版本（必须与 web/package.json 里 @imgly/background-removal 保持一致）
const IMGLY_VERSION =
  process.env.IMGLY_VERSION ||
  (() => {
    const pkg = JSON.parse(
      fs.readFileSync(path.join(PROJECT_ROOT, "package.json"), "utf-8")
    );
    const v =
      pkg.dependencies?.["@imgly/background-removal"] ||
      pkg.devDependencies?.["@imgly/background-removal"] ||
      "";
    return v.replace(/^[\^~>=<\s]+/, "").trim() || "1.7.0";
  })();

const CDN_BASE = `https://staticimgly.com/@imgly/background-removal-data/${IMGLY_VERSION}/dist/`;
const OUT_DIR = path.join(PROJECT_ROOT, "public", "imgly");

// 全量下载所有模型 + 所有 ONNX Runtime，让一键抠图可以让用户自由切换质量档位。
//
// 模型：
//   - /models/isnet_quint8  ~22MB  量化版（快速）— 默认
//   - /models/isnet_fp16    ~44MB  半精度（标准）
//   - /models/isnet         ~88MB  全精度（高质量）
// 运行时：
//   - jsep 变体 + 普通变体（覆盖 WebGPU / 普通 SIMD 两条路径）
//
// 总计 ≈ 165 MB（22 + 44 + 88 + ~12MB runtime）
const KEEP_ENTRIES = [
  "/models/isnet_quint8",
  "/models/isnet_fp16",
  "/models/isnet",
  "/onnxruntime-web/ort-wasm-simd-threaded.jsep.wasm",
  "/onnxruntime-web/ort-wasm-simd-threaded.jsep.mjs",
  "/onnxruntime-web/ort-wasm-simd-threaded.wasm",
  "/onnxruntime-web/ort-wasm-simd-threaded.mjs",
];

const force = process.argv.includes("--force");

/** GET → Buffer，自动跟随重定向 */
function fetchBuffer(url, redirectCount = 0) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith("https") ? https : http;
    const req = lib.get(url, (res) => {
      if (
        res.statusCode &&
        res.statusCode >= 300 &&
        res.statusCode < 400 &&
        res.headers.location
      ) {
        if (redirectCount > 5) {
          reject(new Error("too many redirects"));
          return;
        }
        resolve(fetchBuffer(res.headers.location, redirectCount + 1));
        return;
      }
      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode} on ${url}`));
        return;
      }
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => resolve(Buffer.concat(chunks)));
      res.on("error", reject);
    });
    req.on("error", reject);
    req.setTimeout(120_000, () => {
      req.destroy(new Error("timeout"));
    });
  });
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

async function main() {
  console.log(`[fetch-imgly] version=${IMGLY_VERSION}`);
  console.log(`[fetch-imgly] CDN=${CDN_BASE}`);
  console.log(`[fetch-imgly] OUT=${OUT_DIR}`);
  await fsp.mkdir(OUT_DIR, { recursive: true });

  // 1) resources.json
  console.log(`[fetch-imgly] downloading resources.json ...`);
  const resJsonBuf = await fetchBuffer(CDN_BASE + "resources.json");
  await fsp.writeFile(path.join(OUT_DIR, "resources.json"), resJsonBuf);
  const allResources = JSON.parse(resJsonBuf.toString("utf-8"));

  // 2) 收集需要的 chunk hash
  const wanted = new Map(); // hash -> size
  for (const k of KEEP_ENTRIES) {
    const entry = allResources[k];
    if (!entry) {
      console.warn(`  [warn] entry ${k} not found in resources.json`);
      continue;
    }
    for (const c of entry.chunks || []) {
      if (!wanted.has(c.hash)) {
        wanted.set(c.hash, c.offsets[1] - c.offsets[0]);
      }
    }
  }

  const total = [...wanted.values()].reduce((a, b) => a + b, 0);
  console.log(
    `[fetch-imgly] need ${wanted.size} chunks, total ≈ ${fmtSize(total)}`
  );

  // 3) 并发下载（限制 4 路）
  const tasks = [...wanted.entries()];
  let done = 0;
  let bytesDone = 0;
  const skipExisting = !force;

  async function worker() {
    while (tasks.length > 0) {
      const [hash, size] = tasks.shift();
      const dest = path.join(OUT_DIR, hash);
      if (skipExisting) {
        try {
          const stat = await fsp.stat(dest);
          if (stat.size === size) {
            done++;
            bytesDone += size;
            console.log(
              `  [skip] ${hash.slice(0, 12)} (${fmtSize(size)})  [${done}/${wanted.size}]`
            );
            continue;
          }
        } catch {
          /* not exist */
        }
      }
      try {
        const buf = await fetchBuffer(CDN_BASE + hash);
        await fsp.writeFile(dest, buf);
        done++;
        bytesDone += size;
        console.log(
          `  [ok]   ${hash.slice(0, 12)} (${fmtSize(size)})  [${done}/${wanted.size}]  total ${fmtSize(bytesDone)}/${fmtSize(total)}`
        );
      } catch (e) {
        console.error(`  [err]  ${hash} -> ${e.message}`);
        throw e;
      }
    }
  }

  const concurrency = 4;
  await Promise.all(Array.from({ length: concurrency }, worker));

  console.log(
    `[fetch-imgly] done. ${wanted.size} chunks, ${fmtSize(bytesDone)} → ${OUT_DIR}`
  );
  console.log(`[fetch-imgly] you can now set publicPath: "/imgly/" in AssetEditor.tsx`);
}

main().catch((e) => {
  console.error("[fetch-imgly] FAILED:", e);
  process.exit(1);
});
