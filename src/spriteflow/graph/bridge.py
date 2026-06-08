"""管线图桥接层

把业务节点图（PipelineGraph）转换为引擎可执行的 DAG。

转换规则：
  每个 PipelineNode → 一个 NodeDef（业务节点已在 _NODE_REGISTRY 中注册）
  每个 GraphEdge → 一个 DAG Edge
  业务节点内部的展开（如 CharacterMaster → Text2Img+RemoveBG+SpriteAlign）
  发生在业务节点的 execute() 方法中，对 DAG 层透明。
"""

from __future__ import annotations

from ..engine.dag import DAG, NodeDef, Edge
from .models import PipelineGraphModel, PipelineNodeModel, GraphEdgeModel


# ── 节点端口/参数契约（与各业务节点的 INPUTS/OUTPUTS/PARAMS 保持一致） ──

NODE_CONTRACTS: dict[str, dict] = {
    "CharacterMaster": {
        "inputs": {},
        "outputs": {"image": "image"},
        "required_params": ["template_ids"],
    },
    "DirectionVariant": {
        "inputs": {"image": "image"},
        "outputs": {"images": "image_batch", "down": "image", "up": "image", "left": "image", "right": "image"},
        "required_params": ["template_ids"],
    },
    "AnimationSprite": {
        "inputs": {"image": "image"},
        "outputs": {"images": "image_batch"},
        "required_params": ["template_ids"],
    },
    "SkillVFX": {
        "inputs": {"image": "image"},
        "outputs": {"images": "image_batch"},
        "required_params": ["template_ids"],
    },
    "ImageFusion": {
        "inputs": {"images": "image_batch"},
        "outputs": {"image": "image"},
    },
}

# 允许无输入连线的节点（CharacterMaster 无输入，SkillVFX 的 image 输入为可选）
_NODES_ALLOWED_NO_INPUT: set[str] = {"CharacterMaster", "SkillVFX", "ImageFusion"}

# 纯前端展示节点 — 不在后端执行，校验和 DAG 构建时跳过
_VISUAL_ONLY_NODES: set[str] = {"ImageViewer", "GalleryViewer"}


def _detect_cycles(node_ids: set[str], edges: list[GraphEdgeModel]) -> list[list[str]]:
    """DFS 检测图中的循环依赖，返回所有发现的环"""
    adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for e in edges:
        if e.src_node in node_ids and e.dst_node in node_ids:
            adjacency[e.src_node].append(e.dst_node)

    cycles: list[list[str]] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in node_ids}
    parent: dict[str, str | None] = {nid: None for nid in node_ids}

    def dfs(u: str) -> None:
        color[u] = GRAY
        for v in adjacency.get(u, []):
            if color[v] == GRAY:
                # 找到环：从 v 回溯到 u
                cycle: list[str] = [v]
                cur = u
                while cur is not None and cur != v:
                    cycle.append(cur)
                    cur = parent.get(cur)
                cycle.append(v)
                cycle.reverse()
                cycles.append(cycle)
            elif color[v] == WHITE:
                parent[v] = u
                dfs(v)
        color[u] = BLACK

    for nid in node_ids:
        if color[nid] == WHITE:
            dfs(nid)

    return cycles


def validate_pipeline_graph(graph: PipelineGraphModel) -> list[str]:
    """校验管线图，返回错误列表（空列表表示通过）

    校验项：
      1. 图中没有重复节点 ID
      2. 图中所有连线引用已存在的节点
      3. 图中不存在循环依赖
      4. 各业务节点类型的必填参数完整性
      5. 需要输入的非根节点至少有一条入边
      6. 连线端口在源/目标节点的端口列表中
      7. 非孤立节点（有连线关系的节点）检查

    错误格式：[node_id] 错误描述
    """
    errors: list[str] = []

    if not graph.nodes:
        errors.append("[graph] 管线图为空，请至少添加一个节点")
        return errors

    # 0. 重复节点 ID 检查
    seen_ids: set[str] = set()
    for node in graph.nodes:
        if node.id in seen_ids:
            errors.append(f"[{node.id}] 节点 ID 重复: {node.id}")
        seen_ids.add(node.id)

    node_ids: set[str] = {n.id for n in graph.nodes}
    node_by_id: dict[str, PipelineNodeModel] = {n.id: n for n in graph.nodes}

    # 每个节点的入边计数
    incoming_count: dict[str, int] = {nid: 0 for nid in node_ids}

    # 1. 连线引用校验 + 端口兼容性
    for edge in graph.edges:
        if edge.src_node not in node_ids:
            errors.append(f"[{edge.id}] 源节点不存在: {edge.src_node}")
            continue
        if edge.dst_node not in node_ids:
            errors.append(f"[{edge.id}] 目标节点不存在: {edge.dst_node}")
            continue

        src_type = node_by_id[edge.src_node].type
        dst_type = node_by_id[edge.dst_node].type

        # 跳过涉及纯展示节点的边（它们在 DAG 中不参与执行）
        if src_type in _VISUAL_ONLY_NODES or dst_type in _VISUAL_ONLY_NODES:
            continue

        src_contract = NODE_CONTRACTS.get(src_type)
        dst_contract = NODE_CONTRACTS.get(dst_type)

        if src_contract and edge.src_port not in src_contract["outputs"]:
            errors.append(
                f"[{edge.dst_node}] 连线端口不存在: {edge.src_node}.{edge.src_port}"
                f"（{src_type} 没有输出端口 {edge.src_port}）"
            )
        if dst_contract and edge.dst_port not in dst_contract["inputs"]:
            errors.append(
                f"[{edge.dst_node}] 连线端口不存在: {edge.dst_node}.{edge.dst_port}"
                f"（{dst_type} 没有输入端口 {edge.dst_port}）"
            )

        # 端口类型兼容性检查
        if (src_contract and dst_contract
                and edge.src_port in src_contract["outputs"]
                and edge.dst_port in dst_contract["inputs"]):
            src_port_type = src_contract["outputs"][edge.src_port]
            dst_port_type = dst_contract["inputs"][edge.dst_port]
            if src_port_type != dst_port_type and src_port_type != "ANY" and dst_port_type != "ANY":
                errors.append(
                    f"[{edge.dst_node}] 端口类型不兼容: "
                    f"{edge.src_node}.{edge.src_port}({src_port_type}) → "
                    f"{edge.dst_node}.{edge.dst_port}({dst_port_type})"
                )

        incoming_count[edge.dst_node] += 1

    # 2. 循环依赖检测
    cycles = _detect_cycles(node_ids, graph.edges)
    for cycle in cycles:
        node_list = " → ".join(cycle)
        errors.append(f"[{cycle[0]}] 检测到循环依赖: {node_list}")

    # 3. 逐节点校验
    for node in graph.nodes:
        # 跳过纯前端展示节点（ImageViewer / GalleryViewer）
        if node.type in _VISUAL_ONLY_NODES:
            continue

        contract = NODE_CONTRACTS.get(node.type)
        if contract is None:
            errors.append(f"[{node.id}] 未知节点类型: {node.type}")
            continue

        # 3a. 必填参数
        for req_param in contract.get("required_params", []):
            val = node.params.get(req_param)
            if val is None or (isinstance(val, str) and val.strip() == ""):
                errors.append(
                    f"[{node.id}] 缺少必填参数: {req_param}"
                    f"（{node.type} 节点必须设置 {req_param}）"
                )

        # 3b. 输入端口检查
        input_ports = contract.get("inputs", {})
        if input_ports and node.type not in _NODES_ALLOWED_NO_INPUT:
            if incoming_count[node.id] == 0:
                ports_str = ", ".join(input_ports.keys())
                errors.append(
                    f"[{node.id}] 缺少输入连线（{node.type} 需要连接输入端口 {ports_str}）"
                )

    # 4. 孤立节点检测：需要输入但没有任何连线的节点
    edge_nodes: set[str] = set()
    for e in graph.edges:
        edge_nodes.add(e.src_node)
        edge_nodes.add(e.dst_node)
    for node in graph.nodes:
        contract = NODE_CONTRACTS.get(node.type)
        if contract is None:
            continue
        if node.id not in edge_nodes:
            has_inputs = bool(contract.get("inputs", {}))
            # 只标记需要输入的孤立节点；纯输出节点（如 CharacterMaster）可以独立运行
            if has_inputs:
                errors.append(
                    f"[{node.id}] 节点未连接任何连线（{node.type} 需要上游输入才能运行）"
                )

    return errors


def pipeline_graph_to_dag(graph: PipelineGraphModel) -> tuple[DAG | None, str, list[str]]:
    """将管线图转为引擎可执行的 DAG

    Args:
        graph: 管线图模型

    Returns:
        (dag, graph_name, errors) — 如果 errors 非空，dag 为 None

    在生成 DAG 前做基础校验（节点存在性、边引用合法性）。
    调用方应先用 validate_pipeline_graph() 做完整校验。
    """
    errors: list[str] = []

    if not graph.nodes:
        errors.append("[graph] 管线图为空，无法生成 DAG")
        return None, graph.name, errors

    node_ids: set[str] = {n.id for n in graph.nodes}

    dag = DAG()

    # 1. 添加节点（跳过纯前端展示节点）
    for pn in graph.nodes:
        if pn.type in _VISUAL_ONLY_NODES:
            continue

        # 解析上游连线 → inputs 映射 {port: "upstream_id.port"}
        node_inputs: dict[str, str] = {}
        for edge in graph.edges:
            if edge.dst_node == pn.id:
                # 跳过源端为展示节点的边（展示节点不产生输出）
                src_node_obj = next((n for n in graph.nodes if n.id == edge.src_node), None)
                if src_node_obj and src_node_obj.type in _VISUAL_ONLY_NODES:
                    continue
                node_inputs[edge.dst_port] = f"{edge.src_node}.{edge.src_port}"

        dag.add_node(NodeDef(
            id=pn.id,
            type=pn.type,
            inputs=node_inputs,
            params=pn.params,
        ))

    # 2. 添加连线（跳过涉及展示节点的边）
    for ge in graph.edges:
        if ge.src_node not in node_ids:
            errors.append(f"[{ge.id}] 源节点 {ge.src_node} 不存在，跳过该边")
            continue
        if ge.dst_node not in node_ids:
            errors.append(f"[{ge.id}] 目标节点 {ge.dst_node} 不存在，跳过该边")
            continue
        # 跳过源端或目标端为展示节点的边
        src_node_obj = next((n for n in graph.nodes if n.id == ge.src_node), None)
        dst_node_obj = next((n for n in graph.nodes if n.id == ge.dst_node), None)
        if (src_node_obj and src_node_obj.type in _VISUAL_ONLY_NODES) or \
           (dst_node_obj and dst_node_obj.type in _VISUAL_ONLY_NODES):
            continue
        dag.add_edge(Edge(
            src_node=ge.src_node,
            src_port=ge.src_port,
            dst_node=ge.dst_node,
            dst_port=ge.dst_port,
        ))

    if errors:
        return None, graph.name, errors

    return dag, graph.name, []
