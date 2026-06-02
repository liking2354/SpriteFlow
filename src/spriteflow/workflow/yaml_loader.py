"""YAML 工作流解析器 — 加载 YAML → 验证节点类型+连线 → 构建 DAG"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..engine.dag import DAG, NodeDef
from ..engine.node import get_node_registry


class WorkflowLoader:
    """YAML 工作流加载与验证"""

    @staticmethod
    def load(path: Path | str) -> tuple[DAG, str]:
        """从 YAML 文件加载工作流

        Args:
            path: YAML 文件路径

        Returns:
            (dag, workflow_name)
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"工作流文件不存在: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if not data or "nodes" not in data:
            raise ValueError(f"无效的工作流文件: {path}")

        workflow_name = data.get("name", path.stem)
        version = data.get("version", 1)

        node_defs = []
        for node_data in data["nodes"]:
            node_def = NodeDef(
                id=node_data["id"],
                type=node_data["type"],
                inputs=node_data.get("inputs", {}),
                params=node_data.get("params", {}),
            )
            node_defs.append(node_def)

        dag = DAG.from_node_defs(node_defs)
        return dag, workflow_name

    @staticmethod
    def load_from_dict(data: dict) -> tuple[DAG, str]:
        """从字典加载工作流"""
        if "nodes" not in data:
            raise ValueError("无效的工作流定义：缺少 nodes 字段")

        workflow_name = data.get("name", "unnamed")

        node_defs = []
        for node_data in data["nodes"]:
            node_def = NodeDef(
                id=node_data["id"],
                type=node_data["type"],
                inputs=node_data.get("inputs", {}),
                params=node_data.get("params", {}),
            )
            node_defs.append(node_def)

        dag = DAG.from_node_defs(node_defs)
        return dag, workflow_name

    @staticmethod
    def validate(dag: DAG) -> list[str]:
        """验证工作流 DAG

        Returns:
            错误信息列表（空列表表示验证通过）
        """
        errors: list[str] = []
        registry = get_node_registry()

        # 检查节点类型是否注册
        for nid, node_def in dag.nodes.items():
            if node_def.type not in registry:
                errors.append(f"节点 '{nid}' 的类型 '{node_def.type}' 未注册")

        # 检查环
        if dag.detect_cycle():
            errors.append("工作流存在环，无法执行")

        # 检查连线引用
        for edge in dag.edges:
            if edge.src_node not in dag.nodes:
                errors.append(f"连线引用了不存在的上游节点: '{edge.src_node}'")
            if edge.dst_node not in dag.nodes:
                errors.append(f"连线引用了不存在的下游节点: '{edge.dst_node}'")

        return errors
