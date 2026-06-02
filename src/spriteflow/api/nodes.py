"""节点 API — 列出可用节点 + schema"""

from __future__ import annotations

from fastapi import APIRouter

from ..engine.node import get_node_registry

router = APIRouter()


@router.get("/nodes")
async def list_nodes():
    """列出所有可用节点及其 schema"""
    registry = get_node_registry()
    result = []
    for name, cls in registry.items():
        instance = cls()
        result.append({
            "type": name,
            "category": instance.CATEGORY,
            "inputs": {k: v.value for k, v in instance.INPUTS.items()},
            "outputs": {k: v.value for k, v in instance.OUTPUTS.items()},
            "params": [
                {
                    "name": p.name,
                    "type": p.param_type,
                    "default": p.default,
                    "required": p.required,
                    "min": p.min_val,
                    "max": p.max_val,
                    "choices": p.choices,
                }
                for p in instance.PARAMS
            ],
        })
    return result
