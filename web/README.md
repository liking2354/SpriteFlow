# SpriteFlow Web

SpriteFlow 前端控制台（React + Vite + TypeScript + Tailwind + i18next）。

## 功能

- **快捷生图**：4 种 Seedream 能力（文生图 / 图生图 / 多图融合 / 组图生成）+ 流式 SSE
- **工作流**：选 YAML → 提交 → 实时查看节点状态、缓存命中
- **素材库**：网格浏览、source/tags 筛选、上传、详情/血缘抽屉
- **节点库**：所有可用节点的 schema 浏览
- **能力路由**：capability → provider 映射查看

## 主题与国际化

- **暗/亮主题** 一键切换（视觉规范：暗色优先 + 玻璃态）
- **5 种强调色**：蓝（默认）/ 紫 / 青 / 粉 / 琥珀
- **中英文** 切换（zh-CN / en-US）
- 设置全部持久化到 localStorage

## 启动

### 开发模式（前后端分离）

```bash
# 终端 1：启动后端
python3 -m spriteflow serve

# 终端 2：启动前端
cd web
pnpm install        # 或 npm install
pnpm dev            # 访问 http://localhost:5173
```

Vite 代理已配置 `/api` → `http://127.0.0.1:8000`，无需关心跨域。

### 生产模式（同端口）

```bash
cd web && pnpm build           # 产出 web/dist
python3 -m spriteflow serve    # 直接访问 http://localhost:8000
```

FastAPI 会自动挂载 `web/dist` 为静态目录。

## 目录结构

```
web/
├── src/
│   ├── api/              # 后端 API client + 类型
│   ├── components/
│   │   ├── layout/       # 顶栏 / 侧栏 / 状态栏
│   │   └── ui/           # 通用组件（Button/Card/Field/Segment...）
│   ├── i18n/             # 国际化（zh-CN/en-US）
│   ├── pages/            # 5 个页面
│   ├── stores/           # Zustand 状态（主题/语言）
│   └── styles/           # 全局 CSS + token
├── tailwind.config.ts
└── vite.config.ts
```
