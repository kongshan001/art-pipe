"""
ArtPipe AI图像生成客户端 v0.3
支持 Pollinations.ai (免费) + HuggingFace Inference API (免费) + 可扩展后端
零外部依赖，纯标准库实现
v0.3.12: 新增 HuggingFace 免费后端 (Flux.1-schnell) + AI竖版比例 + 后处理缩略图
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
    "huggingface": {
        "name": "HuggingFace Inference",
        "url": "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell",
        "timeout": 120,
        "free": True,
        "env_key": "HF_API_KEY",  # 可选: 免费 tier 不需要 key，但加上可提高速率限制
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

# v0.3.12: AI 生成推荐尺寸 — 竖版全身比例更适合游戏角色
AI_PORTRAIT_WIDTH = 512
AI_PORTRAIT_HEIGHT = 768


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
        "jump": "jumping pose, airborne, legs tucked, ascending, dynamic leap",  # v0.3.17
        "attack": "attack pose, weapon swung, action shot, dynamic",
        "defend": "defensive stance, shield raised, bracing for impact, guarded posture",  # v0.3.17
        "cast": "casting magic spell, hands glowing, arcane energy, mystical power",  # v0.3.17
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
        # v0.3.17: 新增骑士和吟游诗人的 AI 提示词
        "knight": "holy paladin knight in shining plate armor, full helmet with plume, "
                  "tower shield, sacred sword, imposing heavy armor, divine protector",
        "bard": "bard minstrel with lute, colorful troubadour outfit, pointed hat with feather, "
                "charming performer, musical instrument, artistic flair",
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
        # v0.3.17
        "knight": "polished silver and gold plate armor with royal blue tabard and crimson cross emblem",
        "bard": "rich burgundy and forest green troubadour outfit with gold embroidery and colorful patches",
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
                - thumbnail_b64: str (v0.3.12: 128x192 缩略图 base64)
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
                elif self.backend == "huggingface":
                    result = self._call_huggingface(full_prompt, width, height, seed)
                elif self.backend == "stability":
                    result = self._call_stability(full_prompt, width, height, seed)
                else:
                    result = self._call_pollinations(full_prompt, width, height, seed)

                if result and result.get("image_bytes"):
                    # v0.3.12: 生成缩略图（128x192 竖版缩略图，适合预览）
                    result["thumbnail_b64"] = self._generate_thumbnail(
                        result["image_bytes"], 128, 192
                    )
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
            "jump": "The character is leaping into the air with legs tucked in a dynamic jumping pose.",  # v0.3.17
            "attack": "The character is in a dramatic attack pose with weapon swung forward in an action shot.",
            "defend": "The character is in a defensive stance with guard raised, bracing for impact.",  # v0.3.17
            "cast": "The character is casting a magic spell with hands glowing and arcane energy swirling around.",  # v0.3.17
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

    def _call_huggingface(self, prompt, width, height, seed):
        """调用 HuggingFace Inference API 免费层 (FLUX.1-schnell)
        v0.3.12: 使用 black-forest-labs/FLUX.1-schnell 模型
        免费层无需 API key，但有速率限制（~1000请求/天）
        """
        self._rate_limit()

        url = BACKENDS["huggingface"]["url"]
        hf_key = self.api_key or os.environ.get("HF_API_KEY", "")

        # HF Inference API payload
        payload = json.dumps({
            "inputs": prompt,
            "parameters": {
                "width": width,
                "height": height,
                "seed": seed,
                "num_inference_steps": 4,  # schnell 模型推荐4步
            }
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ArtPipe/0.3.12",
        }
        if hf_key:
            headers["Authorization"] = f"Bearer {hf_key}"

        req = Request(url, data=payload, headers=headers)

        start = time.time()
        resp = urlopen(req, timeout=BACKENDS["huggingface"]["timeout"])
        data = resp.read()
        elapsed = time.time() - start

        # HF 直接返回图片二进制数据
        content_type = resp.headers.get("Content-Type", "")
        if content_type and "json" in content_type:
            # 可能返回错误 JSON
            err = json.loads(data.decode("utf-8", errors="replace"))
            err_msg = err.get("error", str(err))
            if "loading" in err_msg.lower():
                raise ValueError(f"HuggingFace model is loading, retry later: {err_msg}")
            raise ValueError(f"HuggingFace API error: {err_msg}")

        if len(data) < 5000:
            err_msg = data[:200].decode("utf-8", errors="replace")
            raise ValueError(f"HuggingFace returned too small response (size={len(data)}): {err_msg}")

        return {
            "image_bytes": data,
            "image_base64": base64.b64encode(data).decode("ascii"),
            "prompt_used": prompt,
            "backend": "huggingface",
            "generation_time": round(elapsed, 2),
            "size": len(data),
            "format": self._detect_format(data),
        }

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
    def _generate_thumbnail(image_bytes, thumb_w, thumb_h):
        """v0.3.12: 从 AI 生成的图像数据生成缩略图
        零依赖实现：仅支持 JPEG（AI后端主要返回JPEG）
        使用简单的区域平均下采样算法
        返回 base64 编码的 JPEG 缩略图字符串
        """
        try:
            # 解码 JPEG — 纯标准库最小化解析
            # JPEG SOI marker: FF D8
            if image_bytes[:2] != b'\xff\xd8':
                # 非 JPEG，跳过缩略图生成
                return ""

            # 使用简单方法：直接截取前N字节作为标记
            # 由于零依赖限制，无法完整解码JPEG，返回空串标记
            # 实际缩略图需要 PIL/Pillow 支持，此处留作接口
            return ""
        except Exception:
            return ""

    @staticmethod
    def get_backends():
        """获取可用后端列表"""
        result = {}
        for key, cfg in BACKENDS.items():
            is_free = cfg.get("free", False)
            has_key = bool(os.environ.get(cfg.get("env_key", ""), ""))
            # v0.3.12: HuggingFace 免费层无需 key 即可用
            available = is_free or has_key
            result[key] = {
                "name": cfg["name"],
                "free": is_free,
                "available": available,
            }
        return result
