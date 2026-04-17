"""
ArtPipe AI图像生成客户端 v0.3
支持 Pollinations.ai (免费) + 可扩展后端
零外部依赖，纯标准库实现
"""
import base64
import json
import os
import time
from urllib.request import urlopen, Request
from urllib.parse import quote
from urllib.error import URLError, HTTPError


# ---- 后端配置 ----
BACKENDS = {
    "pollinations": {
        "name": "Pollinations.ai",
        "url_template": "https://image.pollinations.ai/prompt/{prompt}?width={width}&height={height}&seed={seed}&nologo=true&model=flux-anime&negative={negative}",
        "timeout": 60,
        "free": True,
    },
    "stability": {
        "name": "Stability AI",
        "url": "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
        "timeout": 120,
        "free": False,
        "env_key": "STABILITY_API_KEY",
    },
    "replicate": {
        "name": "Replicate",
        "timeout": 180,
        "free": False,
        "env_key": "REPLICATE_API_TOKEN",
    },
}


class AIGenerator:
    """AI图像生成器，支持多后端"""

    # 游戏角色专用的提示词模板
    STYLE_PROMPTS = {
        "pixel": "pixel art, retro game sprite, 16-bit style, clean pixels, no anti-aliasing, "
                 "flat colors, crisp edges, perfectly aligned pixel grid",
        "cartoon": "cartoon style, thick outlines, flat colors, cute proportions, game character, "
                   "smooth cel-shading, vibrant palette",
        "anime": "anime style, JRPG character, cel-shaded, vibrant colors, detailed, "
                 "beautiful face, dynamic pose, high quality illustration",
        "western": "western cartoon style, bold shapes, comic book style, game character, "
                   "strong silhouette, clear read",
        "dark": "dark fantasy style, gothic, dramatic lighting, moody atmosphere, game character, "
                "high contrast, rich shadows, ominous aura",
    }

    POSE_PROMPTS = {
        "idle": "standing idle pose, facing forward, neutral expression",
        "walk": "walking pose, mid-stride, dynamic",
        "run": "running pose, action, dynamic movement",
        "attack": "attack pose, weapon swung, action shot, dynamic",
        "hurt": "hurt pose, knocked back, pain expression",
        "die": "falling down, defeated pose, dramatic",
    }

    TYPE_PROMPTS = {
        "warrior": "warrior knight in heavy armor, sword and shield, battle-ready, "
                   "detailed armor plating, heroic stance",
        "mage": "wizard mage in flowing robes, holding magical staff, arcane symbols, "
                "glowing runes, mystical aura",
        "archer": "archer hunter with bow and arrows, forest ranger, hooded cloak, "
                  "agile build, quiver on back",
        "rogue": "rogue assassin in dark leather, dual daggers, stealthy, "
                 "hooded, shadow blending",
        "healer": "healer cleric in white robes, holy book, divine aura, "
                  "gentle expression, sacred symbols",
        "monster": "fantasy monster creature, fearsome, demonic, boss enemy, "
                   "intimidating, detailed texture",
        "npc": "friendly NPC villager, simple clothes, approachable, "
               "warm expression, casual stance",
    }

    # v0.3.9: 配色方案模板 — 按角色类型提供更精准的色彩描述
    COLOR_SCHEMES = {
        "warrior": "steel gray and crimson armor with gold trim accents",
        "mage": "deep purple robes with glowing cyan arcane runes and silver embroidery",
        "archer": "forest green and brown leather with copper buckle details",
        "rogue": "midnight black and dark crimson leather with silver blade gleam",
        "healer": "white and soft gold holy vestments with pale blue divine glow",
        "monster": "dark obsidian and toxic green with glowing red eyes",
        "npc": "warm earth tones, simple brown and cream village clothing",
    }

    # 负面提示词：综合通用质量排除 + 游戏精灵专用排除
    NEGATIVE_PROMPT = (
        "lowres, bad anatomy, bad hands, bad proportions, text, error, "
        "missing fingers, extra digit, fewer digits, cropped, worst quality, "
        "low quality, normal quality, jpeg artifacts, signature, watermark, "
        "username, blurry, deformed, disfigured, extra limbs, extra arms, "
        "mutated, ugly, duplicate, morbid, mutilated, out of frame, "
        "grainy, noisy, jpeg compression, "
        "3d render, realistic, photorealistic, photograph, oil painting, "
        "detailed background, complex background, gradient background, "
        "volumetric lighting, bokeh, lens flare, depth of field, "
        "multiple characters, partial body"
    )

    # 质量增强后缀 — 遵循 [quality → subject → framing → style → bg] 结构
    # v0.3.9: 改为 Flux 友好的自然语言描述（Flux 对句子式 prompt 效果更佳）
    QUALITY_SUFFIX = (
        "This is a full body character design sheet showing the character from the front view, "
        "facing the camera directly. The character is placed on a clean white background. "
        "The artwork is a masterpiece quality game asset with highly detailed clean lines, "
        "sharp focus, well-defined edges, and professional illustration quality suitable for a video game."
    )

    def __init__(self, backend="pollinations", api_key=None):
        self.backend = backend
        self.api_key = api_key
        self._last_request_time = 0

    def generate(self, prompt, style="cartoon", char_type="warrior",
                 width=512, height=512, seed=None, retry=3, pose=None):
        """
        生成AI角色图像

        Args:
            prompt: 用户描述
            style: 风格 (pixel/cartoon/anime/western/dark)
            char_type: 角色类型 (warrior/mage/archer/rogue/healer/monster/npc)
            width: 图像宽度
            height: 图像高度
            seed: 随机种子
            retry: 重试次数
            pose: 姿势 (idle/walk/run/attack/hurt/die)，若提供则加入prompt

        Returns:
            dict with keys:
                - image_base64: str (base64 encoded image)
                - image_bytes: bytes (raw image data)
                - prompt_used: str (actual prompt sent)
                - backend: str
                - generation_time: float
                - size: int (bytes)
            or None on failure
        """
        # 构建增强提示词
        full_prompt = self._build_prompt(prompt, style, char_type, pose)

        if seed is None:
            seed = int(time.time()) % 2147483647

        result = None
        for attempt in range(retry):
            try:
                if self.backend == "pollinations":
                    result = self._call_pollinations(full_prompt, width, height, seed)
                elif self.backend == "stability":
                    result = self._call_stability(full_prompt, width, height, seed)
                else:
                    result = self._call_pollinations(full_prompt, width, height, seed)

                if result and result.get("image_bytes"):
                    return result

            except Exception as e:
                print(f"[AIGenerator] Attempt {attempt+1}/{retry} failed: {e}")

            # 限速 + 退避
            if attempt < retry - 1:
                wait = 5 * (attempt + 1)
                print(f"[AIGenerator] Waiting {wait}s before retry...")
                time.sleep(wait)

        return None

    def _build_prompt(self, user_prompt, style, char_type, pose=None):
        """构建高质量游戏角色提示词
        v0.3.9: 采用 Flux 友好的自然语言描述 + 配色方案注入
        结构: [quality] → [style as sentence] → [char_type with colors] → [user_desc] → [pose] → [quality_suffix]
        """
        parts = []

        # 1. 质量标签前置（模型最先处理的部分权重最高）
        parts.append("masterpiece, best quality, highly detailed")

        # 2. 风格描述（转换为自然语言句子，Flux 更擅长理解完整句子）
        style_map = {
            "pixel": "The character is rendered in a retro pixel art style reminiscent of 16-bit era video games, with clean crisp pixels, no anti-aliasing, flat colors, and perfectly aligned pixel grid.",
            "cartoon": "The character is drawn in a vibrant cartoon style with thick bold outlines, flat cel-shaded colors, cute exaggerated proportions, and smooth shading typical of modern mobile games.",
            "anime": "The character is illustrated in a Japanese RPG anime style with cel-shading, vibrant saturated colors, beautiful detailed facial features, dynamic pose, and high quality manga-inspired linework.",
            "western": "The character is designed in a bold western cartoon style with strong silhouette, comic book inspired shapes, clear visual readability, and confident thick line art.",
            "dark": "The character is rendered in a dark fantasy gothic style with dramatic high-contrast lighting, moody shadows, rich atmospheric depth, and an ominous menacing aura.",
        }
        parts.append(style_map.get(style, style_map["cartoon"]))

        # 3. 角色类型 + 配色方案（v0.3.9: 合并为自然语言描述）
        type_desc = self.TYPE_PROMPTS.get(char_type, "")
        color_scheme = self.COLOR_SCHEMES.get(char_type, "")
        if type_desc and color_scheme:
            parts.append(f"The character is a {type_desc}, wearing {color_scheme}.")
        elif type_desc:
            parts.append(type_desc)

        # 4. 用户原始提示词
        parts.append(user_prompt)

        # 5. 姿势（转为自然语言）
        pose_map = {
            "idle": "The character is standing in an idle pose facing forward with a neutral relaxed expression.",
            "walk": "The character is captured mid-stride in a natural walking animation pose.",
            "run": "The character is in a dynamic running pose showing fast forward movement.",
            "attack": "The character is in a dramatic attack pose with weapon swung forward in an action shot.",
            "hurt": "The character is knocked backward showing pain and surprise.",
            "die": "The character is falling down in a dramatic defeated pose.",
        }
        if pose and pose in pose_map:
            parts.append(pose_map[pose])

        # 6. 质量增强后缀（自然语言）
        parts.append(self.QUALITY_SUFFIX)

        return ", ".join(parts)

    def _call_pollinations(self, prompt, width, height, seed):
        """调用 Pollinations.ai 免费API"""
        self._rate_limit()

        url = BACKENDS["pollinations"]["url_template"].format(
            prompt=quote(prompt),
            width=width,
            height=height,
            seed=seed,
            negative=quote(self.NEGATIVE_PROMPT),
        )

        start = time.time()
        req = Request(url, headers={"User-Agent": "ArtPipe/0.3.0"})
        resp = urlopen(req, timeout=BACKENDS["pollinations"]["timeout"])
        data = resp.read()
        elapsed = time.time() - start

        # 验证响应确实是图片
        content_type = resp.headers.get("Content-Type", "")
        if content_type and not content_type.startswith("image/"):
            err_msg = data[:200].decode("utf-8", errors="replace")
            raise ValueError(f"Pollinations returned non-image ({content_type}): {err_msg}")

        if len(data) < 5000:
            # Too small = error response
            err_msg = data[:200].decode("utf-8", errors="replace")
            raise ValueError(f"Pollinations returned error (size={len(data)}): {err_msg}")

        return {
            "image_bytes": data,
            "image_base64": base64.b64encode(data).decode("ascii"),
            "prompt_used": prompt,
            "backend": "pollinations",
            "generation_time": round(elapsed, 2),
            "size": len(data),
            "format": self._detect_format(data),
        }

    def _call_stability(self, prompt, width, height, seed):
        """调用 Stability AI API (需要 API Key)"""
        key = self.api_key or os.environ.get("STABILITY_API_KEY")
        if not key:
            raise ValueError("Stability AI requires STABILITY_API_KEY")

        self._rate_limit()

        url = BACKENDS["stability"]["url"]
        payload = json.dumps({
            "text_prompts": [{"text": prompt, "weight": 1}],
            "cfg_scale": 7,
            "width": width,
            "height": height,
            "seed": seed,
            "steps": 30,
        }).encode("utf-8")

        req = Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        })

        start = time.time()
        resp = urlopen(req, timeout=BACKENDS["stability"]["timeout"])
        result = json.loads(resp.read())
        elapsed = time.time() - start

        # Stability returns base64 in JSON
        if result.get("artifacts"):
            img_b64 = result["artifacts"][0]["base64"]
            img_bytes = base64.b64decode(img_b64)
            return {
                "image_bytes": img_bytes,
                "image_base64": img_b64,
                "prompt_used": prompt,
                "backend": "stability",
                "generation_time": round(elapsed, 2),
                "size": len(img_bytes),
                "format": "PNG",
            }

        raise ValueError("Unexpected Stability API response")

    def _rate_limit(self):
        """简单限速：请求间隔至少3秒"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 3:
            time.sleep(3 - elapsed)
        self._last_request_time = time.time()

    @staticmethod
    def _detect_format(data):
        """检测图片格式"""
        if data[:3] == b'\xff\xd8\xff':
            return "JPEG"
        elif data[:4] == b'\x89PNG':
            return "PNG"
        elif data[:4] == b'RIFF':
            return "WEBP"
        return "UNKNOWN"

    @staticmethod
    def get_backends():
        """获取可用后端列表"""
        result = {}
        for key, cfg in BACKENDS.items():
            result[key] = {
                "name": cfg["name"],
                "free": cfg.get("free", False),
                "available": cfg.get("free", False) or bool(os.environ.get(cfg.get("env_key", ""))),
            }
        return result
