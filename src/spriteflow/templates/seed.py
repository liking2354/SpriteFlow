"""预置模板数据 — 初始化时自动注入"""

from __future__ import annotations

from datetime import datetime

from .models import PromptTemplate, PromptSlot, SlotType, TemplateType

now = datetime.now().isoformat()

SPEC_ID = "preset_spec_default"
CHAR_WARRIOR = "preset_char_warrior"
CHAR_MAGE = "preset_char_mage"
CHAR_ASSASSIN = "preset_char_assassin"
CHAR_PRIEST = "preset_char_priest"
CHAR_ARCHER = "preset_char_archer"
CHAR_BOSS = "preset_char_boss"
CHAR_CUSTOM = "preset_char_custom"
DIR_DOWN = "preset_dir_down"
DIR_UP = "preset_dir_up"
DIR_LEFT = "preset_dir_left"
DIR_RIGHT = "preset_dir_right"
ACT_IDLE = "preset_act_idle"
ACT_WALK = "preset_act_walk"
ACT_RUN = "preset_act_run"
ACT_CAST = "preset_act_cast"
ACT_ATTACK = "preset_act_attack"
ACT_HIT = "preset_act_hit"
VFX_FIREBALL = "preset_vfx_fireball"

PRESET_TEMPLATES: list[PromptTemplate] = [
    # ── 项目规格模版 ──
    PromptTemplate(
        id=SPEC_ID, name="16-bit RPG Chibi 规格", type=TemplateType.SPEC,
        text="16-bit pixel art. Top-down RPG character. 45-degree game camera. "
             "Chibi proportions. Character occupies approximately 75% of sprite height. "
             "Clean silhouette. Readable game sprite. Uniform lighting. "
             "Prepared for RPG sprite animation. "
             "White background #FFFFFF. No shadow. No text. No UI. No border. "
             "Consistent sprite scale. Keep exact sprite size. "
             "Negative: blurry, low quality, realistic, 3D render, photographic, "
             "distorted face, bad anatomy, extra limbs, watermark, signature, "
             "text, logo, border, shadow, dark background, noisy, jpeg artifacts. "
             "Character: {character_desc}",
        slots=[
            PromptSlot(name="character_desc", type=SlotType.INPUT,
                       label="角色描述", placeholder="如: Heavy plate armor knight...",
                       default="A fantasy game character."),
        ],
    ),

    # ── 角色模版（6 预设 + 1 自定义） ──
    PromptTemplate(
        id=CHAR_WARRIOR, name="剑士", type=TemplateType.CHARACTER,
        text="Character: {character_desc}. Color palette: {color_palette}. {build}.",
        slots=[
            PromptSlot(name="character_desc", type=SlotType.INPUT, label="角色描述",
                       default="Heavy plate armor knight. Broadsword and shield. Muscular build. Red and gold color scheme."),
            PromptSlot(name="color_palette", type=SlotType.INPUT, label="配色",
                       default="#C0392B, #F1C40F, #7F8C8D, #2C3E50"),
            PromptSlot(name="build", type=SlotType.DROPDOWN, label="体型",
                       options=["muscular", "slim", "athletic", "lean", "average", "massive"],
                       default="muscular"),
        ],
    ),
    PromptTemplate(
        id=CHAR_MAGE, name="法师", type=TemplateType.CHARACTER,
        text="Character: {character_desc}. Color palette: {color_palette}. {build}.",
        slots=[
            PromptSlot(name="character_desc", type=SlotType.INPUT, label="角色描述",
                       default="Robed spellcaster. Staff with glowing crystal. Slim build. Blue and purple color scheme. Flowing cape."),
            PromptSlot(name="color_palette", type=SlotType.INPUT, label="配色",
                       default="#8E44AD, #3498DB, #F4F6F7, #2C3E50"),
            PromptSlot(name="build", type=SlotType.DROPDOWN, label="体型",
                       options=["muscular", "slim", "athletic", "lean", "average", "massive"],
                       default="slim"),
        ],
    ),
    PromptTemplate(
        id=CHAR_ASSASSIN, name="刺客", type=TemplateType.CHARACTER,
        text="Character: {character_desc}. Color palette: {color_palette}. {build}.",
        slots=[
            PromptSlot(name="character_desc", type=SlotType.INPUT, label="角色描述",
                       default="Light leather armor rogue. Dual daggers. Lean agile build. Dark green and black color scheme. Hooded."),
            PromptSlot(name="color_palette", type=SlotType.INPUT, label="配色",
                       default="#27AE60, #1E1E1E, #7F8C8D, #2C3E50"),
            PromptSlot(name="build", type=SlotType.DROPDOWN, label="体型",
                       options=["muscular", "slim", "athletic", "lean", "average", "massive"],
                       default="lean"),
        ],
    ),
    PromptTemplate(
        id=CHAR_PRIEST, name="牧师", type=TemplateType.CHARACTER,
        text="Character: {character_desc}. Color palette: {color_palette}. {build}.",
        slots=[
            PromptSlot(name="character_desc", type=SlotType.INPUT, label="角色描述",
                       default="Healer cleric. Holy staff. White robes with gold trim. Gentle build. Healing aura glow."),
            PromptSlot(name="color_palette", type=SlotType.INPUT, label="配色",
                       default="#F4F6F7, #F1C40F, #3498DB, #2C3E50"),
            PromptSlot(name="build", type=SlotType.DROPDOWN, label="体型",
                       options=["muscular", "slim", "athletic", "lean", "average", "massive"],
                       default="average"),
        ],
    ),
    PromptTemplate(
        id=CHAR_ARCHER, name="弓箭手", type=TemplateType.CHARACTER,
        text="Character: {character_desc}. Color palette: {color_palette}. {build}.",
        slots=[
            PromptSlot(name="character_desc", type=SlotType.INPUT, label="角色描述",
                       default="Ranger archer. Longbow. Leather cuirass. Athletic build. Green and brown forest camouflage."),
            PromptSlot(name="color_palette", type=SlotType.INPUT, label="配色",
                       default="#27AE60, #8B4513, #7F8C8D, #2C3E50"),
            PromptSlot(name="build", type=SlotType.DROPDOWN, label="体型",
                       options=["muscular", "slim", "athletic", "lean", "average", "massive"],
                       default="athletic"),
        ],
    ),
    PromptTemplate(
        id=CHAR_BOSS, name="魔王", type=TemplateType.CHARACTER,
        text="Character: {character_desc}. Color palette: {color_palette}. {build}.",
        slots=[
            PromptSlot(name="character_desc", type=SlotType.INPUT, label="角色描述",
                       default="Massive demon lord. Oversized greatsword. Intimidating build. Dark red and black. Fiery aura."),
            PromptSlot(name="color_palette", type=SlotType.INPUT, label="配色",
                       default="#C0392B, #1E1E1E, #E67E22, #2C3E50"),
            PromptSlot(name="build", type=SlotType.DROPDOWN, label="体型",
                       options=["muscular", "slim", "athletic", "lean", "average", "massive"],
                       default="massive"),
        ],
    ),
    PromptTemplate(
        id=CHAR_CUSTOM, name="自定义角色", type=TemplateType.CHARACTER,
        text="Character: {character_desc}. Color palette: {color_palette}. {build}.",
        slots=[
            PromptSlot(name="character_desc", type=SlotType.INPUT, label="角色描述",
                       placeholder="描述你的自定义角色...", default="A unique fantasy character."),
            PromptSlot(name="color_palette", type=SlotType.INPUT, label="配色",
                       placeholder="#FFFFFF, #000000, #FF0000, #00FF00",
                       default="#FFFFFF, #000000"),
            PromptSlot(name="build", type=SlotType.DROPDOWN, label="体型",
                       options=["muscular", "slim", "athletic", "lean", "average", "massive"],
                       default="average"),
        ],
    ),

    # ── 方向模版（4 预设，每个模板只描述单一方向） ──
    PromptTemplate(
        id=DIR_DOWN, name="向下", type=TemplateType.DIRECTION,
        text="Down-facing: character facing forward (south). "
             "Front view. Consistent design.",
        slots=[],
    ),
    PromptTemplate(
        id=DIR_UP, name="向上", type=TemplateType.DIRECTION,
        text="Up-facing: character facing away back (north). "
             "Rear view. Consistent design.",
        slots=[],
    ),
    PromptTemplate(
        id=DIR_LEFT, name="向左", type=TemplateType.DIRECTION,
        text="Left-facing: character facing left (west). "
             "Side view. Consistent design.",
        slots=[],
    ),
    PromptTemplate(
        id=DIR_RIGHT, name="向右", type=TemplateType.DIRECTION,
        text="Right-facing: character facing right (east). "
             "Side view. Consistent design.",
        slots=[],
    ),

    # ── 动作模版（6 预设） ──
    PromptTemplate(
        id=ACT_IDLE, name="待机动画", type=TemplateType.ACTION,
        text="{action_desc}. {direction}. {frames_spec}, horizontal sprite sheet single row. "
             "Hover idle: slight floating movement, hair drifting, cloth drifting.",
        slots=[
            PromptSlot(name="action_desc", type=SlotType.INPUT, label="动作描述",
                       default="idle animation"),
            PromptSlot(name="direction", type=SlotType.INPUT, label="朝向说明",
                       default="same facing direction as reference image"),
            PromptSlot(name="frames_spec", type=SlotType.INPUT, label="帧规格",
                       default="4 frames"),
        ],
    ),
    PromptTemplate(
        id=ACT_WALK, name="走路动画", type=TemplateType.ACTION,
        text="{action_desc}. {direction}. {frames_spec}, horizontal sprite sheet single row. "
             "Walk pose A → transition → walk pose B → transition.",
        slots=[
            PromptSlot(name="action_desc", type=SlotType.INPUT, label="动作描述",
                       default="walking animation"),
            PromptSlot(name="direction", type=SlotType.INPUT, label="朝向说明",
                       default="same facing direction as reference image"),
            PromptSlot(name="frames_spec", type=SlotType.INPUT, label="帧规格",
                       default="4 frames"),
        ],
    ),
    PromptTemplate(
        id=ACT_RUN, name="跑步动画", type=TemplateType.ACTION,
        text="{action_desc}. {direction}. {frames_spec}, horizontal sprite sheet single row. "
             "Running pose with leg extension, forward lean.",
        slots=[
            PromptSlot(name="action_desc", type=SlotType.INPUT, label="动作描述",
                       default="running animation"),
            PromptSlot(name="direction", type=SlotType.INPUT, label="朝向说明",
                       default="same facing direction as reference image"),
            PromptSlot(name="frames_spec", type=SlotType.INPUT, label="帧规格",
                       default="4 frames"),
        ],
    ),
    PromptTemplate(
        id=ACT_CAST, name="施法动画", type=TemplateType.ACTION,
        text="{action_desc}. {direction}. {frames_spec}, horizontal sprite sheet single row. "
             "Idle → raise hand → casting with magic glow → release.",
        slots=[
            PromptSlot(name="action_desc", type=SlotType.INPUT, label="动作描述",
                       default="casting animation"),
            PromptSlot(name="direction", type=SlotType.INPUT, label="朝向说明",
                       default="same facing direction as reference image"),
            PromptSlot(name="frames_spec", type=SlotType.INPUT, label="帧规格",
                       default="4 frames"),
        ],
    ),
    PromptTemplate(
        id=ACT_ATTACK, name="攻击动画", type=TemplateType.ACTION,
        text="{action_desc}. {direction}. {frames_spec}, horizontal sprite sheet single row. "
             "Wind up → strike → follow through → recover.",
        slots=[
            PromptSlot(name="action_desc", type=SlotType.INPUT, label="动作描述",
                       default="attack animation"),
            PromptSlot(name="direction", type=SlotType.INPUT, label="朝向说明",
                       default="same facing direction as reference image"),
            PromptSlot(name="frames_spec", type=SlotType.INPUT, label="帧规格",
                       default="4 frames"),
        ],
    ),
    PromptTemplate(
        id=ACT_HIT, name="受击动画", type=TemplateType.ACTION,
        text="{action_desc}. {direction}. {frames_spec}, horizontal sprite sheet single row. "
             "Impact frame with flash → recoil → stagger → recover.",
        slots=[
            PromptSlot(name="action_desc", type=SlotType.INPUT, label="动作描述",
                       default="hit reaction animation"),
            PromptSlot(name="direction", type=SlotType.INPUT, label="朝向说明",
                       default="same facing direction as reference image"),
            PromptSlot(name="frames_spec", type=SlotType.INPUT, label="帧规格",
                       default="4 frames"),
        ],
    ),

    # ── 特效模版（1 预设） ──
    PromptTemplate(
        id=VFX_FIREBALL, name="火球术", type=TemplateType.VFX,
        text="16-bit pixel art. Magic {vfx_name} effect. {vfx_type} type. "
             "{vfx_desc}. Transparent-friendly black background.",
        slots=[
            PromptSlot(name="vfx_name", type=SlotType.INPUT, label="特效名称",
                       default="fireball"),
            PromptSlot(name="vfx_type", type=SlotType.DROPDOWN, label="特效类型",
                       options=["projectile", "aoe", "buff", "self_cast", "explosion"],
                       default="projectile"),
            PromptSlot(name="vfx_desc", type=SlotType.INPUT, label="特效描述",
                       default="Glowing orange core. Flame trail. Impact explosion."),
            PromptSlot(name="frames", type=SlotType.INPUT, label="帧数",
                       default="8"),
        ],
    ),
]

PRESET_BY_ID: dict[str, PromptTemplate] = {t.id: t for t in PRESET_TEMPLATES}
