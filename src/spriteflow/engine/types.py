"""端口类型系统 — 节点间数据流的强类型约束"""

from __future__ import annotations

from enum import Enum
from typing import Any


class PortType(Enum):
    """端口类型枚举，连线时校验类型匹配"""

    IMAGE = "IMAGE"              # 单张 RGBA 图（PIL.Image / np.array）
    IMAGE_BATCH = "IMAGE_BATCH"  # 一组图（8 方向、多帧）
    MASK = "MASK"                # 单通道遮罩
    SPRITESHEET = "SPRITESHEET"  # 拼好的精灵表 + 网格元数据
    PALETTE = "PALETTE"          # 调色板（颜色列表）
    VIDEO = "VIDEO"              # 视频/帧序列
    STRING = "STRING"            # 字符串
    INT = "INT"                  # 整数
    FLOAT = "FLOAT"              # 浮点数
    SEED = "SEED"                # 随机种子
    ASSET_REF = "ASSET_REF"      # 素材库引用（id）
    ANY = "ANY"                  # 通配，接受任意类型

    def is_compatible(self, other: PortType) -> bool:
        """判断两个端口类型是否兼容（可连线）"""
        if self is PortType.ANY or other is PortType.ANY:
            return True
        return self is other


class PortSpec:
    """端口声明：名称 + 类型 + 可选默认值"""

    def __init__(self, name: str, port_type: PortType, default: Any = None, required: bool = True):
        self.name = name
        self.port_type = port_type
        self.default = default
        self.required = required

    def __repr__(self) -> str:
        return f"PortSpec({self.name}: {self.port_type.value})"


class ParamSpec:
    """参数声明：名称 + 类型 + 约束 + 默认值"""

    def __init__(self, name: str, param_type: str, default: Any = None,
                 min_val: float | None = None, max_val: float | None = None,
                 choices: list[str] | None = None, required: bool = False):
        self.name = name
        self.param_type = param_type
        self.default = default
        self.min_val = min_val
        self.max_val = max_val
        self.choices = choices
        self.required = required

    def __repr__(self) -> str:
        return f"ParamSpec({self.name}: {self.param_type}={self.default})"

    def validate(self, value: Any) -> Any:
        """校验参数值是否在约束范围内"""
        if value is None:
            if self.required:
                raise ValueError(f"参数 '{self.name}' 是必填的")
            return self.default
        if self.min_val is not None and value < self.min_val:
            raise ValueError(f"参数 '{self.name}' 值 {value} 小于最小值 {self.min_val}")
        if self.max_val is not None and value > self.max_val:
            raise ValueError(f"参数 '{self.name}' 值 {value} 大于最大值 {self.max_val}")
        if self.choices is not None and value not in self.choices:
            raise ValueError(f"参数 '{self.name}' 值 '{value}' 不在可选范围 {self.choices} 内")
        return value


# ---- 便捷构造函数 ----

def Int(name: str, min_val: int | None = None, max_val: int | None = None,
        default: int | None = None, required: bool = False) -> ParamSpec:
    return ParamSpec(name, "int", default=default, min_val=min_val, max_val=max_val, required=required)


def Float(name: str, min_val: float | None = None, max_val: float | None = None,
          default: float | None = None, required: bool = False) -> ParamSpec:
    return ParamSpec(name, "float", default=default, min_val=min_val, max_val=max_val, required=required)


def Str(name: str, default: str | None = None, choices: list[str] | None = None,
        required: bool = False) -> ParamSpec:
    return ParamSpec(name, "str", default=default, choices=choices, required=required)


def Seed(name: str = "seed", default: int | None = None) -> ParamSpec:
    return ParamSpec(name, "seed", default=default)
