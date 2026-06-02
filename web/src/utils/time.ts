/** 时间格式化工具 */

/** "x 秒前 / x 分钟前 / x 小时前 / x 天前 / 日期" */
export function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (!t) return "";
  const diff = Math.max(0, Date.now() - t);
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d`;
  return new Date(iso).toLocaleDateString();
}

/**
 * 已完成任务的耗时（秒）。两个时间都需要存在。
 */
export function durationSeconds(
  startISO?: string | null,
  endISO?: string | null
): number | null {
  if (!startISO || !endISO) return null;
  const s = new Date(startISO).getTime();
  const e = new Date(endISO).getTime();
  if (!s || !e || e < s) return null;
  return Math.max(0, Math.round((e - s) / 1000));
}

/**
 * 友好显示秒数：< 60 显示 "12.3s"；>= 60 显示 "1m 23s"。
 * 用来显示生成耗时。
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s ? `${m}m ${s}s` : `${m}m`;
}

/**
 * React Hook：从一个起始时间起，每秒重渲染，返回当前已经经过的秒数。
 * 注意：组件卸载时自动清理。
 */
import { useEffect, useState } from "react";

export function useElapsedSeconds(startISO?: string | null, active = true): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active || !startISO) return;
    const tick = () => setNow(Date.now());
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [active, startISO]);
  if (!startISO) return 0;
  const s = new Date(startISO).getTime();
  if (!s) return 0;
  return Math.max(0, Math.floor((now - s) / 1000));
}
