"""Prompt 拼装引擎 — 三层 Prompt 动态组合 + 预览"""

from __future__ import annotations

from .models import (
    SpriteSpec, PromptLayer, CharacterTemplate, ActionTemplate,
    PromptAssembly, PromptAssemblyResult, PromptLayerInfo, BlockInfo,
    LayerCategory, BlockCategory,
)
from .db import TemplateDB


class PromptBuilder:
    """三层 Prompt 拼装引擎

    拼装顺序（按图层的 sort_order，同层内按 block.sort_order）：
      1. FIXED 层        — 永不变化的风格定义
      2. SPEC_DEFAULT 层 — Spec 级别的默认 Prompt
      3. CHARACTER 层    — 角色定义
      4. ACTION 层       — 动作定义
      5. CONSTRAINT 层   — 包围盒/比例约束
      6. CUSTOM 层       — 自定义附加层

    每个 Character/Action 生成时只需替换 Layer 3 和 Layer 4。
    """

    # 图层拼接顺序
    _LAYER_ORDER = [
        LayerCategory.FIXED,
        LayerCategory.SPEC_DEFAULT,
        LayerCategory.CHARACTER,
        LayerCategory.ACTION,
        LayerCategory.CONSTRAINT,
        LayerCategory.CUSTOM,
    ]

    def __init__(self, db: TemplateDB):
        self._db = db

    async def assemble(
        self,
        req: PromptAssembly,
    ) -> PromptAssemblyResult:
        """拼装完整 Prompt"""

        # 1. 加载 Spec → 获取其关联的图层
        spec = await self._db.get_spec(req.spec_id)
        if not spec:
            raise ValueError(f"规格书不存在: {req.spec_id}")

        # 2. 加载角色模板
        char = await self._db.get_character(req.character_template_id) if req.character_template_id else None

        # 3. 加载动作模板
        action = await self._db.get_action(req.action_template_id) if req.action_template_id else None

        # 4. 收集所有图层，合并为有序列表
        all_layers_dict: dict[str, PromptLayer] = {}
        for layer in spec.layers:
            if layer.enabled:
                all_layers_dict[layer.id] = layer

        # 注入 Character 图层
        if char:
            char_layer = self._make_character_layer(char)
            all_layers_dict[char_layer.id] = char_layer

        # 注入 Action 图层
        if action:
            action_layer = self._make_action_layer(action)
            all_layers_dict[action_layer.id] = action_layer

        # 5. 按 category 排序
        ordered_layers = sorted(
            all_layers_dict.values(),
            key=lambda l: self._category_order(l.category),
        )

        # 6. 拼接
        parts: list[str] = []
        negative_parts: list[str] = []
        layer_infos: list[PromptLayerInfo] = []

        for layer in ordered_layers:
            blocks = sorted(layer.blocks, key=lambda b: b.sort_order) if layer.blocks else []
            # 如果没有 blocks 但有 name/content，构造一个虚拟 block
            if not blocks and layer.name:
                from .models import PromptBlock
                blocks = [PromptBlock(
                    name=layer.name,
                    content=layer.name,
                    category=BlockCategory.CUSTOM,
                    enabled=True,
                )]

            layer_combined_parts = []
            block_infos: list[BlockInfo] = []
            for block in blocks:
                if not block.enabled:
                    continue
                block_infos.append(BlockInfo(
                    block_name=block.name,
                    category=block.category,
                    content=block.content,
                    enabled=True,
                ))
                if block.category == BlockCategory.NEGATIVE:
                    negative_parts.append(block.content)
                else:
                    layer_combined_parts.append(block.content)

            combined = "\n".join(layer_combined_parts)
            if combined.strip():
                parts.append(combined.strip())

            layer_infos.append(PromptLayerInfo(
                layer_name=layer.name,
                category=layer.category,
                blocks=block_infos,
                combined=combined,
            ))

        # 7. 附加额外图层
        if req.extra_layers:
            parts.extend(req.extra_layers)
            layer_infos.append(PromptLayerInfo(
                layer_name="额外附加层",
                category=LayerCategory.CUSTOM,
                blocks=[BlockInfo(block_name="extra", category=BlockCategory.CUSTOM, content=t, enabled=True)
                         for t in req.extra_layers],
                combined="\n".join(req.extra_layers),
            ))

        if req.extra_negative:
            negative_parts.append(req.extra_negative)

        final_prompt = "\n\n".join(parts)
        final_negative = "\n".join(negative_parts)

        # 8. 如果提供了 overrides，替换相应部分
        if req.override_char_desc and char:
            final_prompt = final_prompt.replace(char.description, req.override_char_desc)
        if req.override_action_prompt and action:
            final_prompt = final_prompt.replace(action.prompt, req.override_action_prompt)

        return PromptAssemblyResult(
            layers=layer_infos,
            final_prompt=final_prompt,
            final_negative=final_negative,
            spec_id=req.spec_id,
            character_name=char.name if char else "",
            action_name=action.name if action else "",
        )

    @staticmethod
    def _make_character_layer(char: CharacterTemplate) -> PromptLayer:
        from .models import PromptBlock
        from datetime import datetime
        now = datetime.now().isoformat()
        desc = char.description
        if char.color_scheme:
            desc += "\nColor palette: " + ", ".join(char.color_scheme)
        if char.build_type:
            desc += f"\n{char.build_type} build."

        return PromptLayer(
            id=f"_char_{char.id}",
            name=f"角色：{char.name}",
            category=LayerCategory.CHARACTER,
            blocks=[PromptBlock(
                id=f"_char_block_{char.id}",
                name=char.name,
                content=desc,
                category=BlockCategory.CUSTOM,
                sort_order=0,
                enabled=True,
                created_at=now, updated_at=now,
            )],
            sort_order=self._category_order(LayerCategory.CHARACTER),
            enabled=True,
            created_at=now, updated_at=now,
        )

    @staticmethod
    def _make_action_layer(action: ActionTemplate) -> PromptLayer:
        from .models import PromptBlock
        from datetime import datetime
        now = datetime.now().isoformat()
        direction_text = (
            f"{action.directions} directions. {action.frames_per_direction} frames per direction."
            if action.directions > 1 else ""
        )
        full_action = f"{action.prompt}\n{direction_text}".strip()

        return PromptLayer(
            id=f"_action_{action.id}",
            name=f"动作：{action.name}",
            category=LayerCategory.ACTION,
            blocks=[PromptBlock(
                id=f"_action_block_{action.id}",
                name=action.name,
                content=full_action,
                category=BlockCategory.CUSTOM,
                sort_order=0,
                enabled=True,
                created_at=now, updated_at=now,
            )],
            sort_order=self._category_order(LayerCategory.ACTION),
            enabled=True,
            created_at=now, updated_at=now,
        )

    @staticmethod
    def _category_order(cat: LayerCategory) -> int:
        try:
            return PromptBuilder._LAYER_ORDER.index(cat)
        except ValueError:
            return 99

    # ---- 辅助方法：预置模板初始化 ----

    @staticmethod
    def build_default_spec(name: str = "16-bit RPG Chibi", description: str = "") -> SpriteSpec:
        """创建默认规格书（含预置固定图层）"""
        from datetime import datetime
        from .models import CanvasSpec, AlignRule, SpriteFormat

        now = datetime.now().isoformat()
        spec = SpriteSpec(
            name=name,
            description=description or "标准 16-bit RPG 俯视 45° 角色规格",
            canvas=CanvasSpec(width=64, height=64, target_height_px=48, target_width_px=28, max_colors=24, outline_style="dark"),
            align=AlignRule(auto_center=True, auto_crop=True, bottom_align=True, detect_threshold=32, padding=8),
            default_format=SpriteFormat.GODOT,
            created_at=now, updated_at=now,
        )

        # 预置 3 个固定图层
        from .models import PromptBlock

        # Layer 1: 风格层 (FIXED)
        style_layer = PromptLayer(
            id=f"layer_style_{spec.id}",
            name="固定风格层",
            category=LayerCategory.FIXED,
            description="所有角色共用的风格定义 — 永不变化",
            sort_order=0,
            enabled=True,
            created_at=now, updated_at=now,
            blocks=[
                PromptBlock(
                    id=f"block_style1_{spec.id}", name="画风",
                    content="16-bit pixel art. Top-down RPG character. 45-degree game camera.",
                    category=BlockCategory.STYLE, sort_order=0, enabled=True, created_at=now, updated_at=now,
                ),
                PromptBlock(
                    id=f"block_style2_{spec.id}", name="比例",
                    content="Chibi proportions. Character occupies approximately 75% of sprite height.",
                    category=BlockCategory.PROPORTION, sort_order=1, enabled=True, created_at=now, updated_at=now,
                ),
                PromptBlock(
                    id=f"block_style3_{spec.id}", name="质量",
                    content="Clean silhouette. Readable game sprite. Uniform lighting. Prepared for RPG sprite animation.",
                    category=BlockCategory.QUALITY, sort_order=2, enabled=True, created_at=now, updated_at=now,
                ),
            ],
        )

        # Layer 2: 背景/约束层 (CONSTRAINT)
        constraint_layer = PromptLayer(
            id=f"layer_constraint_{spec.id}",
            name="固定约束层",
            category=LayerCategory.CONSTRAINT,
            description="背景和输出约束",
            sort_order=4,
            enabled=True,
            created_at=now, updated_at=now,
            blocks=[
                PromptBlock(
                    id=f"block_const1_{spec.id}", name="背景",
                    content="White background #FFFFFF. No shadow. No text. No UI. No border.",
                    category=BlockCategory.BACKGROUND, sort_order=0, enabled=True, created_at=now, updated_at=now,
                ),
                PromptBlock(
                    id=f"block_const2_{spec.id}", name="尺寸约束",
                    content="Consistent sprite scale. Keep exact sprite size. Keep exact character proportions. Keep exact pixel density. Consistent bounding box. Character fits inside a 48×48 sprite area. No frame exceeds the character boundary.",
                    category=BlockCategory.CONSTRAINT, sort_order=1, enabled=True, created_at=now, updated_at=now,
                ),
            ],
        )

        # Layer 3: 负面提示词 (NEGATIVE)
        negative_layer = PromptLayer(
            id=f"layer_negative_{spec.id}",
            name="负面提示词层",
            category=LayerCategory.CUSTOM,
            description="排除不需要的元素",
            sort_order=5,
            enabled=True,
            created_at=now, updated_at=now,
            blocks=[
                PromptBlock(
                    id=f"block_neg1_{spec.id}", name="负面词",
                    content="blurry, low quality, realistic, 3D render, photographic, distorted face, bad anatomy, extra limbs, watermark, signature, text, logo, border, shadow, dark background, noisy, jpeg artifacts",
                    category=BlockCategory.NEGATIVE, sort_order=0, enabled=True, created_at=now, updated_at=now,
                ),
            ],
        )

        spec.layers = [style_layer, constraint_layer, negative_layer]
        return spec

    @staticmethod
    def build_default_characters() -> list[CharacterTemplate]:
        """预置 6 个标准 RPG 职业"""
        from datetime import datetime
        now = datetime.now().isoformat()
        return [
            CharacterTemplate(
                id="preset_warrior", name="剑士", key="warrior",
                description="Heavy plate armor knight. Broadsword and shield. Muscular build. Red and gold color scheme.",
                color_scheme=["#C0392B", "#F1C40F", "#7F8C8D", "#2C3E50"],
                build_type="muscular", class_type="warrior",
                created_at=now, updated_at=now,
            ),
            CharacterTemplate(
                id="preset_mage", name="法师", key="mage",
                description="Robed spellcaster. Staff with glowing crystal. Slim build. Blue and purple color scheme. Flowing cape.",
                color_scheme=["#8E44AD", "#3498DB", "#F4F6F7", "#2C3E50"],
                build_type="slim", class_type="mage",
                created_at=now, updated_at=now,
            ),
            CharacterTemplate(
                id="preset_assassin", name="刺客", key="assassin",
                description="Light leather armor rogue. Dual daggers. Lean agile build. Dark green and black color scheme. Hooded.",
                color_scheme=["#27AE60", "#1E1E1E", "#7F8C8D", "#2C3E50"],
                build_type="lean", class_type="assassin",
                created_at=now, updated_at=now,
            ),
            CharacterTemplate(
                id="preset_priest", name="牧师", key="priest",
                description="Healer cleric. Holy staff. White robes with gold trim. Gentle build. Healing aura glow.",
                color_scheme=["#F4F6F7", "#F1C40F", "#3498DB", "#2C3E50"],
                build_type="average", class_type="priest",
                created_at=now, updated_at=now,
            ),
            CharacterTemplate(
                id="preset_archer", name="弓箭手", key="archer",
                description="Ranger archer. Longbow. Leather cuirass. Athletic build. Green and brown forest camouflage.",
                color_scheme=["#27AE60", "#8B4513", "#7F8C8D", "#2C3E50"],
                build_type="athletic", class_type="archer",
                created_at=now, updated_at=now,
            ),
            CharacterTemplate(
                id="preset_boss", name="魔王", key="boss",
                description="Massive demon lord. Oversized greatsword. Intimidating build. Dark red and black. Fiery aura.",
                color_scheme=["#C0392B", "#1E1E1E", "#E67E22", "#2C3E50"],
                build_type="massive", class_type="boss",
                created_at=now, updated_at=now,
            ),
        ]

    @staticmethod
    def build_default_actions() -> list[ActionTemplate]:
        """预置 7 个标准动作"""
        from datetime import datetime
        from .models import ActionType
        now = datetime.now().isoformat()
        return [
            ActionTemplate(
                id="preset_idle", name="待机动画", key="idle",
                action_type=ActionType.IDLE,
                prompt="4 directions idle animation. 4 frames per direction. Hover idle: slight floating movement, hair drifting, cloth drifting.",
                directions=4, frames_per_direction=4, total_frames=16,
                created_at=now, updated_at=now,
            ),
            ActionTemplate(
                id="preset_walk", name="走路动画", key="walk",
                action_type=ActionType.WALK,
                prompt="4 directions walking animation. 4 frames per direction. Walk pose A → transition → walk pose B → transition.",
                directions=4, frames_per_direction=4, total_frames=16,
                created_at=now, updated_at=now,
            ),
            ActionTemplate(
                id="preset_run", name="跑步动画", key="run",
                action_type=ActionType.RUN,
                prompt="4 directions running animation. 4 frames per direction. Running pose with leg extension, forward lean.",
                directions=4, frames_per_direction=4, total_frames=16,
                created_at=now, updated_at=now,
            ),
            ActionTemplate(
                id="preset_cast", name="施法动画", key="cast",
                action_type=ActionType.CAST,
                prompt="4 directions casting animation. 4 frames per direction. Idle → raise hand → casting with magic glow → release.",
                directions=4, frames_per_direction=4, total_frames=16,
                created_at=now, updated_at=now,
            ),
            ActionTemplate(
                id="preset_attack", name="攻击动画", key="attack",
                action_type=ActionType.ATTACK,
                prompt="4 directions attack animation. 4 frames per direction. Wind up → strike → follow through → recover.",
                directions=4, frames_per_direction=4, total_frames=16,
                created_at=now, updated_at=now,
            ),
            ActionTemplate(
                id="preset_hit", name="受击动画", key="hit",
                action_type=ActionType.HIT,
                prompt="4 directions hit reaction. 4 frames per direction. Impact frame with flash → recoil → stagger → recover.",
                directions=4, frames_per_direction=4, total_frames=16,
                created_at=now, updated_at=now,
            ),
            ActionTemplate(
                id="preset_death", name="死亡动画", key="death",
                action_type=ActionType.DEATH,
                prompt="4 directions death animation. 4 frames per direction. Collapse → fall → settle → fade with dissolve effect.",
                directions=4, frames_per_direction=4, total_frames=16,
                created_at=now, updated_at=now,
            ),
        ]

    @staticmethod
    def build_default_vfx() -> list:
        """预置 4 个技能特效"""
        from datetime import datetime
        from .models import VFXTemplate
        now = datetime.now().isoformat()
        return [
            VFXTemplate(
                id="preset_fireball", name="火球术", key="fireball",
                vfx_type="projectile",
                prompt="16-bit pixel art. Magic fireball projectile. Glowing orange core. Flame trail. Impact explosion. Transparent-friendly black background.",
                frames=8, canvas_width=128, canvas_height=128,
                created_at=now, updated_at=now,
            ),
            VFXTemplate(
                id="preset_icespike", name="冰锥术", key="ice_spike",
                vfx_type="projectile",
                prompt="16-bit pixel art. Ice spike projectile. Sharp crystalline shards. Frost trail. Blue-white glow. Transparent-friendly black background.",
                frames=8, canvas_width=128, canvas_height=128,
                created_at=now, updated_at=now,
            ),
            VFXTemplate(
                id="preset_lightning", name="闪电", key="lightning",
                vfx_type="aoe",
                prompt="16-bit pixel art. Lightning strike. Intense white-yellow bolt from top. Electric arcs. Flash frame. Transparent-friendly black background.",
                frames=8, canvas_width=128, canvas_height=128,
                created_at=now, updated_at=now,
            ),
            VFXTemplate(
                id="preset_explosion", name="念力爆破", key="psychic_explosion",
                vfx_type="explosion",
                prompt="16-bit pixel art. Psychic explosion. Expanding purple energy ring. Particle burst. Screen shake effect. Transparent-friendly black background.",
                frames=12, canvas_width=128, canvas_height=128,
                created_at=now, updated_at=now,
            ),
        ]
