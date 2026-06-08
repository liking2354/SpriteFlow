"""Phase 10 — 角色一致性回归测试（使用真实的 PromptBuilder + 内存 DB）

验证要点：
1. 同一角色 × 不同动作 → prompt 中包含角色描述不变
2. 同一角色 × 不同动作 → 动作描述随 action 变化
3. 字符标签在生成流程中保持一致
4. 边界条件（空 prompt、无角色层）不崩溃
"""

import pytest

from spriteflow.templates.db import TemplateDB
from spriteflow.templates.builder import PromptBuilder
from spriteflow.templates.models import (
    BlockCategory, LayerCategory, ActionType,
    SpriteSpec, PromptLayer, PromptBlock, CanvasSpec, AlignRule,
    CharacterTemplate, ActionTemplate, PromptAssembly,
)


# ============================ 测试数据 ============================

def _make_minimal_spec() -> SpriteSpec:
    """最小规格书：一个 FIXED 风格层 + CHARACTER + ACTION"""
    return SpriteSpec(
        id="SPEC01", name="Consistency Test Spec",
        canvas=CanvasSpec(width=64, height=64),
        align=AlignRule(),
        layers=[
            PromptLayer(
                id="L00", name="Style Layer", category=LayerCategory.FIXED,
                sort_order=0,
                blocks=[
                    PromptBlock(id="B00", name="style", category=BlockCategory.STYLE,
                                content="pixel art style", sort_order=0),
                ],
            ),
            PromptLayer(
                id="L01", name="Character Layer", category=LayerCategory.CHARACTER,
                sort_order=1,
                blocks=[
                    PromptBlock(id="B01", name="char_desc", category=BlockCategory.CUSTOM,
                                content="a brave knight", sort_order=0),
                ],
            ),
            PromptLayer(
                id="L02", name="Action Layer", category=LayerCategory.ACTION,
                sort_order=2,
                blocks=[
                    PromptBlock(id="B02", name="action_desc", category=BlockCategory.CUSTOM,
                                content="{action_prompt}", sort_order=0),
                ],
            ),
        ],
    )


def _make_knight() -> CharacterTemplate:
    return CharacterTemplate(
        id="C01", name="Knight", key="knight",
        class_type="warrior", build_type="medium",
        description="A brave knight in silver armor",
        color_scheme=["#C0C0C0", "#FF0000"],
        tags=["human", "melee"],
    )


def _make_mage() -> CharacterTemplate:
    return CharacterTemplate(
        id="C02", name="Mage", key="mage",
        class_type="mage", build_type="slim",
        description="A wise mage in blue robes",
        color_scheme=["#0000FF", "#800080"],
        tags=["human", "ranged"],
    )


def _make_actions() -> list[ActionTemplate]:
    return [
        ActionTemplate(
            id="A01", name="Idle", key="idle", action_type=ActionType.IDLE,
            prompt="standing still", directions=4, frames_per_direction=4, total_frames=16,
        ),
        ActionTemplate(
            id="A02", name="Walk", key="walk", action_type=ActionType.WALK,
            prompt="walking cycle", directions=4, frames_per_direction=8, total_frames=32,
        ),
        ActionTemplate(
            id="A03", name="Attack", key="attack", action_type=ActionType.ATTACK,
            prompt="slashing sword", directions=4, frames_per_direction=6, total_frames=24,
        ),
        ActionTemplate(
            id="A04", name="Cast Spell", key="cast", action_type=ActionType.CAST,
            prompt="casting magic with glow", directions=4, frames_per_direction=8, total_frames=32,
        ),
    ]


async def _setup_db(
    db: TemplateDB,
    spec: SpriteSpec | None = None,
    char: CharacterTemplate | None = None,
    action: ActionTemplate | None = None,
) -> None:
    """将测试数据写入内存 DB

    注意：必须先创建 layers（foreign key），再创建 spec（引用 layers）。
    """
    if spec:
        # 先创建 layers 和 blocks（满足 sprite_spec_layers 的外键约束）
        for layer in spec.layers:
            await db.create_layer(layer)
            for block in layer.blocks:
                await db.create_block(block, layer.id)
        # 再创建 spec（此时 layers 已存在）
        await db.create_spec(spec)
    if char:
        await db.create_character(char)
    if action:
        await db.create_action(action)


@pytest.fixture
async def db():
    """内存数据库 fixture"""
    db_inst = TemplateDB()
    await db_inst.connect()
    await db_inst.init_tables()
    yield db_inst
    await db_inst.close()


# ============================ 测试 ============================


class TestCharacterConsistency:
    """角色一致性：同一角色不同动作的 prompt 中包含一致的描述"""

    @pytest.mark.asyncio
    async def test_same_char_different_actions_share_desc(self, db):
        """骑士 × 待机/走路/攻击 → prompt 都包含 'knight' 和 'silver armor'"""
        spec = _make_minimal_spec()
        knight = _make_knight()
        actions = _make_actions()

        await _setup_db(db, spec, knight)
        for a in actions:
            await db.create_action(a)

        builder = PromptBuilder(db)
        prompts: dict[str, str] = {}

        for action in actions:
            result = await builder.assemble(PromptAssembly(
                spec_id=spec.id,
                character_template_id=knight.id,
                action_template_id=action.id,
            ))
            prompts[action.key] = result.final_prompt

        # 所有 prompt 必须包含角色核心描述
        for key, prompt in prompts.items():
            assert "knight" in prompt.lower(), f"action={key}: missing 'knight'\n{prompt}"
            assert "silver armor" in prompt.lower(), f"action={key}: missing 'silver armor'\n{prompt}"

    @pytest.mark.asyncio
    async def test_same_char_different_actions_different_action_prompt(self, db):
        """不同动作的 prompt 中动作描述不同"""
        spec = _make_minimal_spec()
        knight = _make_knight()
        actions = _make_actions()

        await _setup_db(db, spec, knight)
        for a in actions:
            await db.create_action(a)

        builder = PromptBuilder(db)
        prompts: dict[str, str] = {}

        for action in actions:
            result = await builder.assemble(PromptAssembly(
                spec_id=spec.id,
                character_template_id=knight.id,
                action_template_id=action.id,
            ))
            prompts[action.key] = result.final_prompt

        # walk/attack/cast 的 prompt 不应完全相同
        assert prompts["walk"] != prompts["idle"]
        assert prompts["walk"] != prompts["attack"]
        assert prompts["attack"] != prompts["cast"]

    @pytest.mark.asyncio
    async def test_different_chars_same_action_different_prompts(self, db):
        """不同角色 × 同一动作 → prompt 不同"""
        spec = _make_minimal_spec()
        knight = _make_knight()
        mage = _make_mage()
        action = _make_actions()[0]  # idle

        await _setup_db(db, spec, knight)
        await _setup_db(db, spec=None, char=mage)
        await db.create_action(action)

        builder = PromptBuilder(db)

        result_knight = await builder.assemble(PromptAssembly(
            spec_id=spec.id,
            character_template_id=knight.id,
            action_template_id=action.id,
        ))
        result_mage = await builder.assemble(PromptAssembly(
            spec_id=spec.id,
            character_template_id=mage.id,
            action_template_id=action.id,
        ))

        assert "knight" in result_knight.final_prompt.lower()
        assert "mage" in result_mage.final_prompt.lower()
        assert result_knight.final_prompt != result_mage.final_prompt

    @pytest.mark.asyncio
    async def test_action_prompt_describes_correct_action(self, db):
        """动作 prompt 侧重点随 action 变化"""
        spec = _make_minimal_spec()
        knight = _make_knight()
        actions = _make_actions()

        await _setup_db(db, spec, knight)
        for a in actions:
            await db.create_action(a)

        builder = PromptBuilder(db)

        for action in actions:
            result = await builder.assemble(PromptAssembly(
                spec_id=spec.id,
                character_template_id=knight.id,
                action_template_id=action.id,
            ))
            # action_name 应反映动作名称
            assert result.action_name == action.name, \
                f"Expected action_name={action.name}, got {result.action_name}"

    @pytest.mark.asyncio
    async def test_character_name_present(self, db):
        """character_name 字段包含角色名"""
        spec = _make_minimal_spec()
        knight = _make_knight()
        action = _make_actions()[1]  # walk

        await _setup_db(db, spec, knight)
        await db.create_action(action)

        builder = PromptBuilder(db)
        result = await builder.assemble(PromptAssembly(
            spec_id=spec.id,
            character_template_id=knight.id,
            action_template_id=action.id,
        ))

        assert result.character_name == knight.name


class TestPromptBuilderEdgeCases:
    """边界条件测试"""

    @pytest.mark.asyncio
    async def test_empty_action_prompt_not_break(self, db):
        """动作 prompt 为空时拼装不崩溃"""
        spec = _make_minimal_spec()
        knight = _make_knight()
        action = ActionTemplate(
            id="A99", name="Empty", key="empty",
            action_type=ActionType.IDLE,
            prompt="",  # 空 prompt
            directions=1, frames_per_direction=1, total_frames=1,
        )

        await _setup_db(db, spec, knight)
        await db.create_action(action)

        builder = PromptBuilder(db)
        result = await builder.assemble(PromptAssembly(
            spec_id=spec.id,
            character_template_id=knight.id,
            action_template_id=action.id,
        ))
        assert result.final_prompt is not None
        # 即使动作 prompt 为空，也应生成有效字符串
        assert len(result.final_prompt) > 0

    @pytest.mark.asyncio
    async def test_no_char_layer_no_crash(self, db):
        """没有 CHARACTER 层时不崩溃"""
        spec = SpriteSpec(
            id="SPEC02", name="No Char",
            canvas=CanvasSpec(width=64, height=64),
            align=AlignRule(),
            layers=[
                PromptLayer(
                    id="L99", name="BG Only", category=LayerCategory.FIXED,
                    sort_order=0,
                    blocks=[
                        PromptBlock(id="B99", name="bg", category=BlockCategory.BACKGROUND,
                                    content="dark background", sort_order=0),
                    ],
                ),
            ],
        )
        knight = _make_knight()
        action = _make_actions()[0]

        await _setup_db(db, spec, knight)
        await db.create_action(action)

        builder = PromptBuilder(db)
        result = await builder.assemble(PromptAssembly(
            spec_id=spec.id,
            character_template_id=knight.id,
            action_template_id=action.id,
        ))
        # 不应崩溃，即使没有 CHARACTER 层
        assert result.final_prompt

    @pytest.mark.asyncio
    async def test_override_fields_work(self, db):
        """override 字段生效"""
        spec = _make_minimal_spec()
        knight = _make_knight()
        action = _make_actions()[1]  # walk

        await _setup_db(db, spec, knight)
        await db.create_action(action)

        builder = PromptBuilder(db)
        result = await builder.assemble(PromptAssembly(
            spec_id=spec.id,
            character_template_id=knight.id,
            action_template_id=action.id,
            override_char_desc="a mysterious ninja",
            override_action_prompt="sneaking silently",
        ))
        assert "mysterious ninja" in result.final_prompt
        assert "sneaking silently" in result.final_prompt


class TestMultipleCharactersIsolation:
    """多角色隔离测试"""

    @pytest.mark.asyncio
    async def test_multiple_characters_independent(self, db):
        """多个角色在循环中各自独立，不互相污染"""
        spec = _make_minimal_spec()
        chars = [_make_knight(), _make_mage()]
        action = _make_actions()[2]  # attack

        await _setup_db(db, spec)
        for c in chars:
            await db.create_character(c)
        await db.create_action(action)

        builder = PromptBuilder(db)

        results = []
        for c in chars:
            result = await builder.assemble(PromptAssembly(
                spec_id=spec.id,
                character_template_id=c.id,
                action_template_id=action.id,
            ))
            results.append(result)

        assert results[0].final_prompt != results[1].final_prompt
        assert "knight" in results[0].final_prompt.lower()
        assert "mage" in results[1].final_prompt.lower()
        assert results[0].character_name == "Knight"
        assert results[1].character_name == "Mage"


class TestRouterRetry:
    """Phase 10: 路由重试逻辑"""

    def test_retry_config_exists(self):
        """验证 settings 中有重试配置"""
        from spriteflow.config import settings
        assert settings.generation_retry_count >= 1
        assert settings.generation_retry_delay_sec >= 0

    def test_error_categorization_recognizes_key_patterns(self):
        """验证错误分类函数能识别已知错误模式"""
        from spriteflow.api.generate import _categorize_error

        # API Key 缺失
        code, _ = _categorize_error(ValueError("Seedream Provider 缺少 ARK_API_KEY"))
        assert code == "AUTH_KEY_MISSING"

        # 内容安全
        code, _ = _categorize_error(RuntimeError("参考图被内容安全系统拦截（InputImageSensitiveContentDetected）"))
        assert code == "CONTENT_MODERATION_INPUT"

        code, _ = _categorize_error(RuntimeError("提示词触发内容安全过滤（PromptSensitiveContentDetected）"))
        assert code == "CONTENT_MODERATION_PROMPT"

        code, _ = _categorize_error(RuntimeError("生成结果触发内容安全过滤（OutputImageSensitiveContentDetected）"))
        assert code == "CONTENT_MODERATION_OUTPUT"

        # Provider 错误
        code, _ = _categorize_error(RuntimeError("Seedream API 错误 500: Internal Error"))
        assert code == "PROVIDER_ERROR"

        # 超时
        code, _ = _categorize_error(TimeoutError("Connection timeout"))
        assert code == "TIMEOUT"

        # 未知错误
        code, msg = _categorize_error(ValueError("some random error"))
        assert code == "UNKNOWN"
        assert "some random error" in msg
