/**
 * 管线图入口页面 — 重定向到管理列表
 * 保留该文件是为了兼容旧路由 /graph
 */
import { Navigate } from "react-router-dom";

export function GraphPage() {
  return <Navigate to="/graphs" replace />;
}
