"""端到端测试：视频抽帧 + 精灵表打包"""
import asyncio
import os
import shutil
import subprocess
import tempfile

from PIL import Image

from spriteflow.nodes.extract_frames import ExtractFramesNode, _find_ffmpeg
from spriteflow.nodes.pack_spritesheet import PackSpritesheetNode
from spriteflow.engine.context import Context
from spriteflow.engine.cache import CacheManager


async def test_extract_frames_and_pack():
    tmp = tempfile.mkdtemp()
    try:
        # ---- 1. 生成合成测试视频（4帧彩色方块） ----
        frames_dir = os.path.join(tmp, "frames")
        os.makedirs(frames_dir)

        colors = [(255, 0, 0, 255), (0, 255, 0, 255),
                  (0, 0, 255, 255), (255, 255, 0, 255)]
        for i, color in enumerate(colors):
            img = Image.new("RGBA", (80, 80), color)
            img.save(os.path.join(frames_dir, f"frame_{i:04d}.png"))

        ffmpeg = _find_ffmpeg()
        video_path = os.path.join(tmp, "test.mp4")
        cmd = [
            ffmpeg, "-y", "-framerate", "8",
            "-i", os.path.join(frames_dir, "frame_%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            video_path,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        print(f"[1/3] 测试视频: {os.path.getsize(video_path)} bytes ✓")

        # ---- 2. 测试 ExtractFrames（无 rembg / 无 align，纯抽帧） ----
        class MockStorage:
            async def download(self, uri):
                with open(video_path, "rb") as f:
                    return f.read()

        ctx = Context(cache=CacheManager(), storage=MockStorage(), run_id="test_ef")
        node = ExtractFramesNode()
        result = await node.execute({}, {
            "video_asset_id": "test_video",
            "fps": 8,
            "max_frames": 4,
            "remove_bg": False,
            "align": False,
        }, ctx)

        frames = result["frames"]
        assert len(frames) == 4, f"expected 4 frames, got {len(frames)}"
        assert isinstance(frames[0], Image.Image)
        print(f"[2/3] ExtractFrames: {len(frames)} 帧, 首帧尺寸 {frames[0].size} ✓")

        # ---- 3. 测试 PackSpritesheet（Godot 格式） ----
        pack = PackSpritesheetNode()
        pack_ctx = Context(cache=CacheManager(), run_id="test_pack")
        pack_result = await pack.execute({"frames": frames}, {
            "columns": 2,
            "cell_width": 64,
            "cell_height": 64,
            "padding": 2,
            "format": "godot",
            "save_asset": False,
        }, pack_ctx)

        sheet = pack_result["spritesheet"]
        expected_w = 2 * 64 + 3 * 2  # 2 cells + 3 paddings
        expected_h = 2 * 64 + 3 * 2
        assert sheet.size == (expected_w, expected_h), \
            f"spritesheet size {sheet.size} != ({expected_w}, {expected_h})"

        import json
        atlas = json.loads(pack_result["atlas_json"])
        assert len(atlas["frames"]) == 4
        assert atlas["meta"]["format"] == "RGBA8888"
        assert atlas["meta"]["size"]["w"] == expected_w
        print(f"[3/3] PackSpritesheet: {sheet.size}, godot atlas {len(atlas['frames'])} frames ✓")

        print("\n✅ 全链路测试通过（视频抽帧 → 精灵表打包 → Godot atlas）")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(test_extract_frames_and_pack())
