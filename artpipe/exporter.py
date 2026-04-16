"""
ArtPipe 资产导出器 v0.3
将生成的角色数据导出为多种游戏引擎格式
零外部依赖，纯标准库实现
"""
import base64
import json
import time


class AssetExporter:
    """角色资产导出器，支持多种游戏引擎格式"""

    def __init__(self, char_data):
        self.data = char_data

    def export_all(self):
        """导出所有支持的格式"""
        exports = {}

        # SpriteSheet PNG 导出
        spritesheet = self.data.get("spritesheet", {})
        if spritesheet:
            exports["spritesheet"] = {
                "format": "png",
                "width": spritesheet.get("frame_width", 64),
                "height": spritesheet.get("frame_height", 80),
                "total_frames": spritesheet.get("total_frames", 0),
                "cols": spritesheet.get("cols", 8),
                "rows": spritesheet.get("rows", 0),
                "frame_map": spritesheet.get("frame_map", {}),
                "png_base64": spritesheet.get("png_base64", ""),
            }

        # Spine 格式导出
        skeleton = self.data.get("skeleton", {})
        animations = self.data.get("animations", {})
        if skeleton:
            exports["spine"] = {
                "format": "spine_json",
                "version": "4.1",
                "skeleton": {
                    "hash": self.data.get("id", ""),
                    "spine": "4.1.23",
                    "x": 0,
                    "y": -self.data.get("canvas_size", {}).get("height", 80),
                    "width": self.data.get("canvas_size", {}).get("width", 64),
                    "height": self.data.get("canvas_size", {}).get("height", 80),
                },
                "bones": self._format_spine_bones(skeleton),
                "slots": self._format_spine_slots(skeleton),
                "animations": self._format_spine_animations(animations),
            }

        # Unity 格式导出
        exports["unity"] = {
            "format": "unity_json",
            "name": self.data.get("id", "character"),
            "textureWidth": spritesheet.get("cols", 8) * spritesheet.get("frame_width", 64),
            "textureHeight": spritesheet.get("rows", 0) * spritesheet.get("frame_height", 80),
            "frames": self._format_unity_frames(spritesheet),
            "animations": {
                name: {
                    "frames": list(range(
                        info.get("start", 0),
                        info.get("start", 0) + info.get("count", 0)
                    )),
                    "fps": animations.get(name, {}).get("fps", 8),
                    "loop": animations.get(name, {}).get("loop", True),
                }
                for name, info in spritesheet.get("frame_map", {}).items()
            },
        }

        # Godot 格式导出
        exports["godot"] = {
            "format": "godot_tres",
            "resource_type": "SpriteFrames",
            "animations": [
                {
                    "name": name,
                    "speed": animations.get(name, {}).get("fps", 8),
                    "loop": animations.get(name, {}).get("loop", True),
                    "frames": self._format_godot_frames(name, spritesheet),
                }
                for name in spritesheet.get("frame_map", {})
            ],
        }

        return exports

    def _format_spine_bones(self, skeleton):
        """格式化 Spine 骨骼数据"""
        if not skeleton:
            return []
        bones = skeleton.get("bones", [])
        result = []
        for bone in bones:
            entry = {"name": bone["name"]}
            if bone.get("parent"):
                entry["parent"] = bone["parent"]
            entry["x"] = bone.get("x", 0)
            entry["y"] = bone.get("y", 0)
            result.append(entry)
        return result

    def _format_spine_slots(self, skeleton):
        """格式化 Spine 插槽数据"""
        if not skeleton:
            return []
        return skeleton.get("slots", [])

    def _format_spine_animations(self, animations):
        """格式化 Spine 动画数据"""
        result = {}
        for name, info in animations.items():
            result[name] = {
                "slots": {},
                "bones": {},
                "duration": info.get("frame_count", 1) / max(info.get("fps", 8), 1),
            }
        return result

    def _format_unity_frames(self, spritesheet):
        """格式化 Unity 帧数据"""
        frame_w = spritesheet.get("frame_width", 64)
        frame_h = spritesheet.get("frame_height", 80)
        cols = spritesheet.get("cols", 8)
        total = spritesheet.get("total_frames", 0)
        sheet_w = cols * frame_w

        frames = []
        for i in range(total):
            col = i % cols
            row = i // cols
            frames.append({
                "frame": {"x": col * frame_w, "y": row * frame_h, "w": frame_w, "h": frame_h},
                "rotated": False,
                "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, "w": frame_w, "h": frame_h},
                "sourceSize": {"w": frame_w, "h": frame_h},
            })
        return frames

    def _format_godot_frames(self, anim_name, spritesheet):
        """格式化 Godot 帧数据"""
        frame_w = spritesheet.get("frame_width", 64)
        frame_h = spritesheet.get("frame_height", 80)
        cols = spritesheet.get("cols", 8)
        frame_map = spritesheet.get("frame_map", {})
        sheet_w = cols * frame_w

        info = frame_map.get(anim_name, {})
        start = info.get("start", 0)
        count = info.get("count", 0)

        frames = []
        for i in range(start, start + count):
            col = i % cols
            row = i // cols
            frames.append({
                "x": col * frame_w,
                "y": row * frame_h,
                "width": frame_w,
                "height": frame_h,
            })
        return frames
