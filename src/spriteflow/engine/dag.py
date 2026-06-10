"""DAG 数据结构 — 构建、环检测、拓扑排序"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeDef:
    """DAG 中的节点定义"""

    id: str                              # DAG 内唯一标识
    type: str                            # 节点类型名（对应注册表）
    inputs: dict[str, str] = field(default_factory=dict)   # 端口名 → 上游引用 "node_id.port"
    params: dict[str, Any] = field(default_factory=dict)    # 参数值


@dataclass
class Edge:
    """节点间连线"""

    src_node: str   # 上游节点 id
    src_port: str   # 上游输出端口名
    dst_node: str   # 下游节点 id
    dst_port: str   # 下游输入端口名


class DAG:
    """有向无环图 — 管线图执行的核心数据结构"""

    def __init__(self) -> None:
        self.nodes: dict[str, NodeDef] = {}
        self.edges: list[Edge] = []

    def add_node(self, node_def: NodeDef) -> None:
        """添加节点"""
        if node_def.id in self.nodes:
            raise ValueError(f"节点 id 重复: '{node_def.id}'")
        self.nodes[node_def.id] = node_def

    def add_edge(self, edge: Edge) -> None:
        """添加连线"""
        if edge.src_node not in self.nodes:
            raise ValueError(f"上游节点不存在: '{edge.src_node}'")
        if edge.dst_node not in self.nodes:
            raise ValueError(f"下游节点不存在: '{edge.dst_node}'")
        self.edges.append(edge)

    def detect_cycle(self) -> bool:
        """检测图中是否存在环（DFS）"""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {nid: WHITE for nid in self.nodes}

        # 构建邻接表
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            adj[edge.src_node].append(edge.dst_node)

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for neighbor in adj[node]:
                if color[neighbor] == GRAY:
                    return True  # 环！
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        for nid in self.nodes:
            if color[nid] == WHITE:
                if dfs(nid):
                    return True
        return False

    def topological_sort(self) -> list[str]:
        """拓扑排序（Kahn's algorithm）— 返回节点执行顺序"""
        if self.detect_cycle():
            raise ValueError("DAG 存在环，无法拓扑排序")

        # 计算入度
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            adj[edge.src_node].append(edge.dst_node)
            in_degree[edge.dst_node] += 1

        # 入度为 0 的节点入队
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result: list[str] = []

        while queue:
            # 稳定排序：按添加顺序
            queue.sort(key=lambda nid: list(self.nodes.keys()).index(nid))
            current = queue.pop(0)
            result.append(current)

            for neighbor in adj[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.nodes):
            raise ValueError("拓扑排序不完整，图可能存在环")

        return result

    def get_upstream(self, node_id: str) -> dict[str, tuple[str, str]]:
        """获取节点的所有上游输入映射 {输入端口: (上游节点id, 上游输出端口)}"""
        result: dict[str, tuple[str, str]] = {}
        for edge in self.edges:
            if edge.dst_node == node_id:
                result[edge.dst_port] = (edge.src_node, edge.src_port)
        return result

    def get_downstream(self, node_id: str) -> list[str]:
        """获取节点的所有下游节点 id"""
        return list({edge.dst_node for edge in self.edges if edge.src_node == node_id})

    def validate(self) -> list[str]:
        """验证 DAG 结构合法性

        Returns:
            错误信息列表（空列表表示验证通过）
        """
        from .node import get_node_registry

        errors: list[str] = []
        registry = get_node_registry()

        # 检查节点类型是否注册
        for nid, node_def in self.nodes.items():
            if node_def.type not in registry:
                errors.append(f"节点 '{nid}' 的类型 '{node_def.type}' 未注册")

        # 检查环
        if self.detect_cycle():
            errors.append("DAG 存在环，无法执行")

        # 检查连线引用
        for edge in self.edges:
            if edge.src_node not in self.nodes:
                errors.append(f"连线引用了不存在的上游节点: '{edge.src_node}'")
            if edge.dst_node not in self.nodes:
                errors.append(f"连线引用了不存在的下游节点: '{edge.dst_node}'")

        return errors

    @classmethod
    def from_node_defs(cls, node_defs: list[NodeDef]) -> DAG:
        """从节点定义列表构建 DAG，自动解析 inputs 引用生成 Edge"""
        dag = cls()
        for nd in node_defs:
            dag.add_node(nd)

        for nd in node_defs:
            for port_name, ref in nd.inputs.items():
                # ref 格式: "node_id.port_name"
                if "." in ref:
                    src_id, src_port = ref.split(".", 1)
                else:
                    src_id, src_port = ref, "result"
                dag.add_edge(Edge(
                    src_node=src_id,
                    src_port=src_port,
                    dst_node=nd.id,
                    dst_port=port_name,
                ))

        return dag
