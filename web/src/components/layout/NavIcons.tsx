/** 侧边栏 SVG 图标 — 16×16 行内 SVG，无外部依赖 */
import type { ReactNode } from "react";

const SIZE = 16;
const stroke = "currentColor";
const attrs = (d: string) => ({
  width: SIZE, height: SIZE, viewBox: "0 0 24 24",
  fill: "none", stroke, strokeWidth: 1.8, strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const, children: <path d={d} />,
});

export const navIcons: Record<string, ReactNode> = {
  generate: (
    <svg {...attrs("M12 3l2 5h5l-4 3 1.5 5L12 13l-4.5 3L9 11l-4-3h5z")} />
  ),
  video: (
    <svg {...attrs("M15 10l4.5-2.5v9L15 14M4 6h9a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V8a2 2 0 012-2z")} />
  ),
  editor: (
    <svg {...attrs("M12 20h9M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4L16.5 3.5z")} />
  ),
  spritesheet: (
    <svg {...attrs("M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z")} />
  ),
  videoFrames: (
    <svg {...attrs("M22 8l-6-6H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z M14 2v6h6 M10 9l-2 2 2 2 M14 9l2 2-2 2")} />
  ),
  workflows: (
    <svg {...attrs("M4 4h6v6H4zM14 4h2v2h4v4h-2v2h-4v-4h2V6h-2v2H4V4z")} />
  ),
  assets: (
    <svg {...attrs("M19 3H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V5a2 2 0 00-2-2z M8.5 10a1.5 1.5 0 100-3 1.5 1.5 0 000 3z M21 15l-5-5L5 21")} />
  ),
  templates: (
    <svg {...attrs("M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8")} />
  ),
  graph: (
    <svg {...attrs("M18 20V10M12 20V4M6 20v-6")} />
  ),
  nodes: (
    <svg {...attrs("M12 2l9 4.5v11L12 22l-9-4.5v-11z M12 22V12 M12 12l9-4.5 M12 12L3 7.5")} />
  ),
  routing: (
    <svg {...attrs("M5 12h14M12 5l7 7-7 7")} />
  ),
};
