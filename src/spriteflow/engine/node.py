"""节点契约 — Node ABC + @node 装饰器"""

from __future__ import annotations

import inspect
import functools
from typing import Any, Callable

from .types import PortType, PortSpec, ParamSpec, Int, Float, Str, Seed


class Node:
    """节点基类：声明式契约 + execute 纯函数

    子类需定义：
      - INPUTS: dict[str, PortType]  输入端口
      - PARAMS: list[ParamSpec]       参数规格
      - OUTPUTS: dict[str, PortType]  输出端口
      - CATEGORY: str                 分类
      - execute(inputs, params, ctx)   执行逻辑
    """

    INPUTS: dict[str, PortType] = {}
    PARAMS: list[ParamSpec] = []
    OUTPUTS: dict[str, PortType] = {}
    CATEGORY: str = "uncategorized"

    # 运行时由注册表填充
    _node_type: str = ""

    @property
    def node_type(self) -> str:
        return self._node_type or self.__class__.__name__

    def execute(self, inputs: dict, params: dict, ctx: Any) -> dict:
        """纯函数：相同输入必产相同输出（缓存的前提）"""
        raise NotImplementedError

    def get_param_defaults(self) -> dict[str, Any]:
        """获取参数默认值"""
        return {p.name: p.default for p in self.PARAMS if p.default is not None}

    def validate_params(self, params: dict) -> dict:
        """校验并补全参数"""
        result = self.get_param_defaults()
        result.update(params)
        for spec in self.PARAMS:
            result[spec.name] = spec.validate(result.get(spec.name))
        return result

    def __repr__(self) -> str:
        return f"Node({self.node_type}, inputs={list(self.INPUTS)}, outputs={list(self.OUTPUTS)})"


# ---- 全局节点注册表 ----

_NODE_REGISTRY: dict[str, type[Node]] = {}


def get_node_registry() -> dict[str, type[Node]]:
    """获取节点注册表"""
    return dict(_NODE_REGISTRY)


def register_node(name: str, cls: type[Node]) -> None:
    """注册节点到全局注册表"""
    _NODE_REGISTRY[name] = cls
    cls._node_type = name


def create_node(node_type: str) -> Node:
    """根据类型名创建节点实例"""
    if node_type not in _NODE_REGISTRY:
        raise KeyError(f"未注册的节点类型: '{node_type}'，可用类型: {list(_NODE_REGISTRY)}")
    return _NODE_REGISTRY[node_type]()


# ---- @node 装饰器 — 轻量级节点定义方式 ----

def node(
    name: str | None = None,
    category: str = "uncategorized",
    inputs: dict[str, PortType] | None = None,
    outputs: dict[str, PortType] | None = None,
):
    """将函数包装为节点

    用法:
        @node(category="generate", inputs={"prompt": PortType.STRING}, outputs={"image": PortType.IMAGE})
        def text2img(prompt, seed=42, **kwargs):
            ...
            return {"image": img}
    """

    def decorator(fn: Callable) -> type[Node]:
        node_name = name or fn.__name__

        # 从函数签名提取参数规格
        param_specs: list[ParamSpec] = []
        sig = inspect.signature(fn)
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "ctx", "kwargs"):
                continue
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                continue
            # 判断参数类型
            ann = param.annotation
            default = param.default if param.default is not inspect.Parameter.empty else None

            if ann is inspect.Parameter.empty:
                # 无注解，根据默认值推断
                if isinstance(default, int):
                    param_specs.append(Int(param_name, default=default))
                elif isinstance(default, float):
                    param_specs.append(Float(param_name, default=default))
                elif isinstance(default, str):
                    param_specs.append(Str(param_name, default=default))
                else:
                    param_specs.append(Str(param_name, default=default))
            elif ann is int:
                param_specs.append(Int(param_name, default=default))
            elif ann is float:
                param_specs.append(Float(param_name, default=default))
            elif ann is str:
                param_specs.append(Str(param_name, default=default))
            else:
                param_specs.append(Str(param_name, default=default))

        # 构建动态 Node 子类
        _inputs = inputs or {}
        _outputs = outputs or {}

        class FunctionNode(Node):
            INPUTS = _inputs
            PARAMS = param_specs
            OUTPUTS = _outputs
            CATEGORY = category
            _node_type = node_name

            def execute(self, inputs_dict: dict, params_dict: dict, ctx: Any) -> dict:
                # 合并 inputs 和 params 为函数参数
                kwargs = {**inputs_dict, **params_dict}
                result = fn(**kwargs, ctx=ctx)
                if isinstance(result, dict):
                    return result
                # 单值返回，映射到第一个输出端口
                if _outputs:
                    first_key = next(iter(_outputs))
                    return {first_key: result}
                return {"result": result}

        FunctionNode.__name__ = node_name
        FunctionNode.__qualname__ = node_name

        # 注册
        register_node(node_name, FunctionNode)
        return FunctionNode

    return decorator
