"""执行上下文 — 节点通过 ctx 访问基础设施"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cache import CacheManager


@dataclass
class Context:
    """节点执行上下文，由执行器注入

    提供节点需要的基础设施访问：
    - cache: 内容寻址缓存
    - router: 能力路由器（按需）
    - storage: 存储后端（按需）
    - logger: 日志记录
    - run_id: 当前执行 id
    """

    cache: CacheManager = field(default_factory=CacheManager)
    router: Any = None       # CapabilityRouter，运行时注入
    storage: Any = None      # StorageBackend，运行时注入
    db: Any = None           # AssetDB，运行时注入
    template_db: Any = None  # TemplateDB，运行时注入（业务节点拼装 prompt 用）
    run_id: str = ""
    _outputs: dict[str, dict[str, Any]] = field(default_factory=dict)  # node_id → {port: value}
    _input_hashes: dict[str, dict[str, str]] = field(default_factory=dict)  # node_id → {port: hash}
    _node_inputs: dict[str, dict[str, Any]] = field(default_factory=dict)  # node_id → node 执行输入快照（prompt/params 等）

    def set_node_output(self, node_id: str, outputs: dict[str, Any]) -> None:
        """存储节点输出"""
        self._outputs[node_id] = outputs

    def get_node_output(self, node_id: str) -> dict[str, Any]:
        """获取节点输出"""
        if node_id not in self._outputs:
            raise KeyError(f"节点 '{node_id}' 尚未执行，输出不可用")
        return self._outputs[node_id]

    def set_input_hashes(self, node_id: str, hashes: dict[str, str]) -> None:
        """存储节点输入哈希"""
        self._input_hashes[node_id] = hashes

    def get_input_hashes(self, node_id: str) -> dict[str, str]:
        """获取节点输入哈希"""
        return self._input_hashes.get(node_id, {})

    def set_node_inputs(self, node_id: str, inputs: dict[str, Any]) -> None:
        """存储节点执行输入快照（prompt/params 等，用于执行记录审查）"""
        self._node_inputs[node_id] = inputs

    def get_node_inputs(self, node_id: str) -> dict[str, Any]:
        """获取节点执行输入快照"""
        return self._node_inputs.get(node_id, {})

    def log(self, message: str) -> None:
        """简易日志"""
        print(f"[SpriteFlow:{self.run_id}] {message}")
