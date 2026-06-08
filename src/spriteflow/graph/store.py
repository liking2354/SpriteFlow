"""管线图持久化存储 — JSON 文件 CRUD

目录结构:
    graphs/
    ├── index.json       ← 元数据索引，快速列出所有图
    └── {id}.json        ← 单个管线图的完整定义
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from .models import (
    PipelineGraphModel,
    GraphIndex,
    GraphIndexEntry,
)


class GraphStore:
    """管线图的文件系统存储

    用法:
        store = GraphStore()
        graph = store.load("abc123")
        graphs = store.list()
        store.save(graph)
        store.delete("abc123")
    """

    def __init__(self, graphs_dir: Path | None = None) -> None:
        self._dir = Path(graphs_dir) if graphs_dir else settings.project_root / "graphs"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / "index.json"

    # ── CRUD ──────────────────────────────────────────

    def list(self, tag: str | None = None) -> list[GraphIndexEntry]:
        """列出所有图（按更新时间倒序），可选标签过滤"""
        index = self._load_index()
        entries = index.graphs
        if tag:
            entries = [e for e in entries if tag in e.tags]
        entries.sort(key=lambda e: e.updated_at, reverse=True)
        return entries

    def load(self, graph_id: str) -> PipelineGraphModel | None:
        """加载单个管线图"""
        path = self._dir / f"{graph_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return PipelineGraphModel(**data)

    def save(self, graph: PipelineGraphModel) -> PipelineGraphModel:
        """创建或更新管线图"""
        graph.updated_at = datetime.now(timezone.utc).isoformat()

        # 写入图文件
        path = self._dir / f"{graph.id}.json"
        path.write_text(
            graph.model_dump_json(indent=2, exclude_none=False),
            encoding="utf-8",
        )

        # 更新索引
        self._upsert_index(graph)
        return graph

    def delete(self, graph_id: str) -> bool:
        """删除管线图，返回是否成功"""
        path = self._dir / f"{graph_id}.json"
        if not path.exists():
            return False
        path.unlink()
        self._remove_from_index(graph_id)
        return True

    # ── 搜索 ──────────────────────────────────────────

    def search(self, query: str) -> list[GraphIndexEntry]:
        """按名称/描述模糊搜索"""
        q = query.lower()
        return [
            e for e in self.list()
            if q in e.name.lower() or q in e.description.lower()
        ]

    # ── 索引维护 ──────────────────────────────────────

    def _load_index(self) -> GraphIndex:
        if not self._index_path.exists():
            return GraphIndex()
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            return GraphIndex(**data)
        except Exception:
            # 索引损坏时重建
            return self._rebuild_index()

    def _save_index(self, index: GraphIndex) -> None:
        self._index_path.write_text(
            index.model_dump_json(indent=2, exclude_none=False),
            encoding="utf-8",
        )

    def _upsert_index(self, graph: PipelineGraphModel) -> None:
        index = self._load_index()
        entry = GraphIndexEntry(
            id=graph.id,
            name=graph.name,
            description=graph.description,
            tags=graph.tags,
            node_count=len(graph.nodes),
            updated_at=graph.updated_at,
        )

        # 替换或追加
        for i, e in enumerate(index.graphs):
            if e.id == graph.id:
                index.graphs[i] = entry
                break
        else:
            index.graphs.append(entry)

        self._save_index(index)

    def _remove_from_index(self, graph_id: str) -> None:
        index = self._load_index()
        index.graphs = [e for e in index.graphs if e.id != graph_id]
        self._save_index(index)

    def _rebuild_index(self) -> GraphIndex:
        """从 graph JSON 文件重建 index"""
        entries = []
        for path in sorted(self._dir.glob("*.json")):
            if path.name == "index.json":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entries.append(GraphIndexEntry(
                    id=data.get("id", path.stem),
                    name=data.get("name", ""),
                    description=data.get("description", ""),
                    tags=data.get("tags", []),
                    node_count=len(data.get("nodes", [])),
                    updated_at=data.get("updated_at", ""),
                ))
            except Exception:
                continue
        index = GraphIndex(graphs=entries)
        self._save_index(index)
        return index
