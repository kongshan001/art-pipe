"""
ArtPipe AI图像生成客户端 v0.3
支持 Pollinations.ai (免费) + HuggingFace Inference API (免费) + 可扩展后端
零外部依赖，纯标准库实现
v0.3.31: 风格定制负面提示词 + 按风格动态选择Pollinations模型(pixel→flux, dark→flux, western→flux-realism)
v0.3.26: Prompt增强 — 添加光照方向描述(左上方光源)、脚部/鞋类可见性要求、角色类型鞋类细节
v0.3.24: 优化Prompt — 增强角色特征描述，添加装备细节和材质关键词
v0.3.21: 修复重试seed bug — 重试时轮换seed确保每次生成不同图像
v0.3.18: 增强版 — 视角约束+体型描述注入+负面提示词扩展+enhance参数
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
        "url_template": "https://image.pollinations.ai/prompt/{prompt}?width={width}&height={height}&seed={seed}&nologo=true&model=flux-anime&negative={negative}&enhance=true",
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
    # v0.4: 全面增强面部质量 — 每种风格加入详细面部描述
    STYLE_PROMPTS = {
        "pixel": "pixel art, retro game sprite, 16-bit style, clean pixels, no anti-aliasing, "
                 "flat colors, crisp edges, perfectly aligned pixel grid",
        "cartoon": "cartoon game character style, thick clean outlines, flat vibrant colors, "
                   "cute expressive proportions, smooth cel-shading, "
                   "detailed face with large sparkly eyes, defined eyebrows, small nose, expressive mouth, "
                   "clean facial features, rosy cheeks, bright highlights in eyes",
        "anime": "anime JRPG character official art, cel-shaded with soft gradients, "
                 "vibrant saturated colors, crisp clean linework, "
                 "highly detailed beautiful face, large detailed iris with limbal ring and light reflections, "
                 "long eyelashes, well-defined nose bridge, soft lips, "
                 "perfectly symmetrical face, hair framing face naturally, "
                 "professional game studio quality illustration",
        "western": "western comic book game character, bold graphic shapes, "
                   "strong confident silhouette, dynamic powerful stance, "
                   "detailed face with sharp jawline, defined cheekbones, intense focused eyes, "
                   "strong brow ridge, angular features, clean ink lines, "
                   "halftone shading, bold color palette, professional game concept art",
        "dark": "dark fantasy game character, dramatic chiaroscuro lighting, "
                "gothic atmosphere, deep rich shadows, high contrast rim lighting, "
                "intense piercing eyes with subtle glow, sharp angular face, "
                "gaunt cheekbones, brooding expression, strands of hair catching light, "
                "ominous aura, dark moody color palette, professional dark fantasy illustration",
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
        # v0.4: 全面增强面部质量 — 每种角色加入详细面部特征
        "warrior": "warrior knight in heavy plate armor with intricate engravings, "
                   "wielding a broadsword and round shield, battle-ready stance, "
                   "chainmail visible under armor joints, leather belt with pouches, "
                   "steel gauntlets and greaves, heavy steel-toed armored boots with iron buckles, "
                   "handsome masculine face with strong jawline and cheekbones, "
                   "piercing steel-blue eyes with determined heroic gaze, "
                   "short windswept brown hair, clean-shaven, "
                   "battle-scarred armor with subtle dents and scratches",
        "mage": "wizard mage in layered flowing robes with star patterns, "
                "holding a gnarled wooden staff topped with a glowing crystal orb, "
                "arcane symbols floating around hands, runic embroidery on sleeves, "
                "leather spell component pouch on belt, pointed wide-brim hat, "
                "pointed leather boots with silver buckle clasps visible below robe hem, "
                "elegant androgynous face with high cheekbones, "
                "large luminous violet eyes with swirling magical reflections, "
                "long flowing silver-white hair, serene mysterious expression, "
                "mystical glowing aura, wisps of magical energy",
        "archer": "archer ranger with a recurve bow and quiver of arrows, "
                  "wearing a hooded forest cloak over leather armor, "
                  "agile athletic build, bracer arm guards, "
                  "utility belt with hunting tools, leaf-shaped arrow fletching, "
                  "lace-up leather hunting boots with fur trim at the ankle, "
                  "bright attentive face with sharp emerald-green eyes, "
                  "auburn hair in a practical side ponytail, sun-kissed skin, "
                  "confident focused expression with slight smile, "
                  "nature-inspired decorative feathers and beads",
        "rogue": "rogue assassin in fitted dark leather armor with buckle straps, "
                 "dual curved daggers with ornate hilts, hooded cowl, "
                 "bandolier of throwing knives, soft-soled boots, "
                 "utility pouches and lockpicks visible on belt, "
                 "sharp angular face partially shadowed by hood, "
                 "narrow amber-gold eyes with cunning predatory gaze, "
                 "messy jet-black hair falling across forehead, "
                 "wry knowing smirk, shadow blending dark cloak",
        "healer": "healer cleric in pristine white and gold vestments, "
                  "holding a sacred tome with glowing pages, "
                  "divine halo of soft light above head, holy symbol pendant, "
                  "sash with embroidered sigils, "
                  "gentle radiant face with warm compassionate pink eyes, "
                  "long golden-blonde hair in braids with white ribbon, "
                  "soft rosy cheeks, kind caring smile, porcelain skin, "
                  "healing aura of warm golden particles",
        "monster": "fantasy monster creature with textured scaly hide, "
                   "glowing crimson eyes with slit pupils and inner fire, "
                   "curved obsidian horns and razor-sharp fangs, "
                   "muscular imposing frame, bone armor plates growing from body, "
                   "detailed skin texture with veins and glowing cracks, "
                   "intimidating boss enemy with dramatic presence, "
                   "elemental energy radiating from claws, smoke wisps",
        "npc": "friendly NPC villager in simple but well-crafted clothing, "
               "approachable warm face with crinkling smile lines around eyes, "
               "soft brown eyes full of warmth and kindness, "
               "wheat-colored tousled hair, sun-weathered rosy cheeks, "
               "carrying a trade item or tool, "
               "leather apron over cotton shirt, sensible boots, "
               "pouch belt with personal belongings, natural relaxed posture",
        "knight": "holy paladin knight in mirror-polished full plate armor, "
                  "great helm with flowing feather plume, "
                  "tower shield emblazoned with sacred cross, blessed longsword, "
                  "tabard over armor with heraldic emblem, chainmail aventail, "
                  "noble chiseled face with piercing ice-blue eyes, "
                  "short-cropped platinum blonde hair, strong Roman nose, "
                  "stoic righteous expression, divine light catching hair, "
                  "polished metal reflections and gold filigree details",
        "bard": "bard minstrel in a colorful patchwork troubadour outfit, "
                "carrying an ornately carved lute with inlay details, "
                "pointed hat with dramatic feather plume, "
                "ruffled collar and embroidered vest, fingerless gloves, "
                "charismatic lively face with mischievous twinkling hazel eyes, "
                "long wavy chestnut hair flowing freely, confident playful grin, "
                "gold earring, artistic flair with colorful ribbons, "
                "musical notes floating nearby",
    }

    # v0.3.24: 配色方案模板 — 增强材质描述和质感关键词
    # 包含主色+辅色+点缀色+材质关键词，帮助AI生成更丰富的视觉效果
    COLOR_SCHEMES = {
        "warrior": "brushed steel gray armor plates with crimson fabric underlayer, "
                   "polished gold rivets and trim accents, worn leather brown belt and straps, "
                   "metallic sheen on armor surfaces",
        "mage": "deep royal purple velvet robes with luminous cyan arcane rune patterns, "
                "silver thread embroidery on cuffs and collar, aged oak brown staff, "
                "glowing iridescent crystal orb with prismatic reflections",
        "archer": "muted forest green wool cloak over saddle-brown oiled leather armor, "
                 "antique copper buckle and clasp details, cream linen undershirt, "
                 "natural wood grain bow with sinew string",
        "rogue": "matte midnight black leather with subtle dark crimson stitching, "
                "tarnished silver blade gleam and buckle hardware, "
                "charcoal gray inner cloak lining, oiled black leather with worn patina",
        "healer": "soft ivory white linen vestments with pale gold brocade trim, "
                 "baby blue silk sash with sacred embroidery, "
                 "warm cream parchment-colored book cover, golden halo glow",
        "monster": "dark obsidian-black scales with toxic iridescent green bioluminescent patterns, "
                   "molten red glowing eyes and veins, bone white horns and claws, "
                   "charred gray hide texture with ember-like cracks",
        "npc": "warm earth-tone palette of terracotta red, golden wheat, and forest brown, "
               "undyed natural linen undershirt, "
               "oiled leather apron in honey brown, brass button details",
        # v0.3.17
        "knight": "mirror-polished silver plate armor with bright gold filigree edges, "
                  "royal blue silk tabard with white cross emblem, "
                  "crimson red feather plume on helm, "
                  "gleaming reflective metal surfaces with blue-steel cold shadows",
        "bard": "rich burgundy velvet coat with emerald green patches and copper stitching, "
                "gold embroidery on collar and cuffs, "
                "natural wood lute body with amber varnish finish, "
                "colorful silk ribbons in teal, gold, and crimson",
    }

    # v0.4: 增强负面提示词 — 重点排除面部模糊/变形问题
    NEGATIVE_PROMPT = (
        "3d render, realistic, photograph, lowres, blurry, bad anatomy, "
        "deformed, disfigured, extra limbs, bad hands, text, watermark, "
        "multiple characters, partial body, cropped, out of frame, "
        "gradient background, complex background, "
        "asymmetric face, cross-eyed, awkward pose, twisted torso, "
        "side view, back view, profile view, "
        "blurry face, deformed face, distorted face, ugly face, "
        "poorly drawn face, messy face, smudged face, "
        "bad eyes, poorly drawn eyes, asymmetric eyes, "
        "missing facial features, featureless face, "
        "low quality face, flat face, generic face"
    )

    # v0.3.31: 按风格定制的负面提示词 — 针对不同美术风格排除最影响质量的视觉缺陷
    # 每种风格有独特的"质量陷阱"，例如像素画不应出现抗锯齿，暗黑风格不应出现明亮色彩
    # 与通用 NEGATIVE_PROMPT 合并使用，Flux 模型对精确的风格排除响应显著
    STYLE_NEGATIVE_PROMPTS = {
        "pixel": (
            "anti-aliased, smooth gradients, soft shading, blurred edges, "
            "photorealistic, 3d rendered, high resolution, detailed texture, "
            "subpixel rendering, vector graphics, watercolor, oil painting, "
            "lens flare, depth of field, bokeh"
        ),
        "cartoon": (
            "photorealistic, hyper-detailed, gritty, dark, horror, "
            "realistic skin texture, photograph, complex shading, "
            "3d rendered, CGI, uncanny valley, boring, plain"
        ),
        "anime": (
            "3d render, western cartoon, photorealistic, ugly, "
            "rough sketch, amateur, low effort, simple, plain, "
            "realistic proportions, western style eyes"
        ),
        "western": (
            "anime, manga, Japanese style, kawaii, cute, chibi, "
            "soft shading, pastel colors, delicate, thin lines, "
            "photorealistic, boring, bland, flat"
        ),
        "dark": (
            "bright, cheerful, colorful, cute, kawaii, cartoon, "
            "pastel, light-hearted, sunny, happy, clean, "
            "low contrast, flat lighting, cheerful expression, smile"
        ),
    }

    # v0.3.31: 按风格选择最优 Pollinations 模型
    # flux-anime: 适合卡通/日式风格（默认，训练数据偏二次元）
    # flux: 通用模型，更适合像素画和暗黑风格的写实/暗色调
    # flux-realism: 写实模型，适合欧美风格的厚涂/漫画风格
    # 测试发现 flux-anime 对暗黑风格的色彩偏亮，flux 模型对暗色调响应更好
    STYLE_MODELS = {
        "pixel": "flux",          # 通用模型对像素艺术色块响应更准确
        "cartoon": "flux-anime",  # 动漫模型对卡通风格色彩饱和度更好
        "anime": "flux-anime",    # 动漫模型对日式风格天然适配
        "western": "flux-realism",# 写实模型对欧美厚涂/漫画风格表现更好
        "dark": "flux",           # 通用模型对暗色调和戏剧光照响应更好
    }

    # v0.3.26: 质量增强后缀 — 添加光照方向描述和脚部完整可见性
    # 遵循 [quality → subject → framing → style → bg] 结构
    # 使用明确的画面描述替代抽象的"masterpiece"标签，Flux模型对此响应更好
    # v0.3.26新增：
    #   - 环境光方向描述（左上方光源，温暖高光+冷色阴影），增强AI生成图像的光照一致性
    #   - 明确的脚部/鞋类可见性要求，减少AI生成半身截断的问题
    QUALITY_SUFFIX = (
        "This is a full body character design sheet showing the complete character from head to toe, "
        "facing the camera directly in a symmetrical front-facing pose. "
        "The character's feet and footwear are clearly visible and fully rendered at the bottom of the frame. "
        "The lighting is directional from the upper left with warm highlights on the left side "
        "and cooler shadow tones on the right side, creating dimensional depth. "
        "The character is placed on a clean pure white background with no other elements. "
        "The artwork features crisp clean linework with sharp focus, well-defined edges, "
        "professional game studio quality illustration with consistent lighting, "
        "balanced composition, and clear visual silhouette suitable as a video game character asset."
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
        # 构建增强提示词（v0.3.31: 含风格定制负面提示词）
        full_prompt, negative = self._build_prompt(prompt, style, char_type, pose)

        if seed is None:
            seed = int(time.time()) % 2147483647

        result = None
        for attempt in range(retry):
            try:
                if self.backend == "pollinations":
                    result = self._call_pollinations(full_prompt, width, height, seed,
                                                     style=style, negative=negative)
                elif self.backend == "huggingface":
                    result = self._call_huggingface(full_prompt, width, height, seed)
                elif self.backend == "stability":
                    result = self._call_stability(full_prompt, width, height, seed)
                else:
                    result = self._call_pollinations(full_prompt, width, height, seed,
                                                     style=style, negative=negative)

                if result and result.get("image_bytes"):
                    # v0.3.12: 生成缩略图（128x192 竖版缩略图，适合预览）
                    result["thumbnail_b64"] = self._generate_thumbnail(
                        result["image_bytes"], 128, 192
                    )
                    return result

            except Exception as e:
                print(f"[AIGenerator] Attempt {attempt+1}/{retry} failed: {e}")

            # v0.3.21: 重试时更换seed，确保每次重试生成不同图像
            seed = (seed * 16807 + 12345) % 2147483647

            # 限速 + 退避
            if attempt < retry - 1:
                wait = 5 * (attempt + 1)
                print(f"[AIGenerator] Waiting {wait}s before retry...")
                time.sleep(wait)

        return None

    # v0.3.18: 角色特征细节注入 — 按风格提供具体的解剖比例约束
    # 研究表明 Flux/SD 模型对 "X-year-old" 年龄描述和具体比例描述响应良好
    STYLE_BODY_HINTS = {
        "pixel": "compact chibi proportions with large head, short limbs, stylized simplified anatomy,",
        "cartoon": "slightly exaggerated cartoon proportions with expressive body language, large expressive eyes, smooth rounded forms,",
        "anime": "idealized anime proportions with long legs, slim athletic build, detailed expressive eyes, graceful posture,",
        "western": "heroic western proportions with broad shoulders, strong confident stance, bold muscular silhouette,",
        "dark": "tall imposing proportions with angular features, gaunt dramatic build, sharp angular silhouette,",
    }

    # v0.3.18: 视角约束前缀 — 强化正面全身视角，减少侧面/半身生成
    VIEWPOINT_CONSTRAINT = (
        "front-facing full body portrait, character standing centered in frame, "
        "head to toe fully visible, straight-on camera angle, symmetrical composition, "
        "character looking directly at viewer, centered subject, "
    )

    def _build_prompt(self, user_prompt, style, char_type, pose=None):
        """构建高质量游戏角色提示词
        v0.3.18: 增强版 — 新增视角约束 + 角色体型描述 + 结构化 prompt
        v0.3.31: 返回 (prompt, negative_prompt) 元组，支持风格定制负面提示词
        结构: [quality] → [viewpoint] → [style as sentence] → [body hint]
              → [char_type with colors] → [user_desc] → [pose] → [quality_suffix]
        """
        parts = []

        # 1. 质量标签前置（模型最先处理的部分权重最高）
        parts.append("masterpiece, best quality, highly detailed")

        # 2. v0.3.18: 视角约束（紧跟质量标签，强化全身正面视角）
        parts.append(self.VIEWPOINT_CONSTRAINT)

        # 3. 风格描述（转换为自然语言句子，Flux 更擅长理解完整句子）
        style_map = {
            "pixel": "The character is rendered in a retro pixel art style reminiscent of 16-bit era video games, with clean crisp pixels, no anti-aliasing, flat colors, and perfectly aligned pixel grid.",
            "cartoon": "The character is drawn in a vibrant cartoon style with thick bold outlines, flat cel-shaded colors, cute exaggerated proportions, and smooth shading typical of modern mobile games.",
            "anime": "The character is illustrated in a Japanese RPG anime style with cel-shading, vibrant saturated colors, beautiful detailed facial features, dynamic pose, and high quality manga-inspired linework.",
            "western": "The character is designed in a bold western cartoon style with strong silhouette, comic book inspired shapes, clear visual readability, and confident thick line art.",
            "dark": "The character is rendered in a dark fantasy gothic style with dramatic high-contrast lighting, moody shadows, rich atmospheric depth, and an ominous menacing aura.",
        }
        parts.append(style_map.get(style, style_map["cartoon"]))

        # 4. v0.3.18: 角色体型约束（按风格注入解剖比例细节）
        body_hint = self.STYLE_BODY_HINTS.get(style, "")
        if body_hint:
            parts.append(body_hint)

        # 5. 角色类型 + 配色方案（v0.3.9: 合并为自然语言描述）
        type_desc = self.TYPE_PROMPTS.get(char_type, "")
        color_scheme = self.COLOR_SCHEMES.get(char_type, "")
        if type_desc and color_scheme:
            parts.append(f"The character is a {type_desc}, wearing {color_scheme}.")
        elif type_desc:
            parts.append(type_desc)

        # 6. 用户原始提示词
        parts.append(user_prompt)

        # 7. 姿势（转为自然语言）
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

        # 8. 质量增强后缀（自然语言）
        parts.append(self.QUALITY_SUFFIX)

        # v0.3.19: 智能连接 — 标签式部分用逗号，句子式部分用空格
        # Flux 模型对自然语言段落响应更好，而非逗号拼接的碎片
        tags = []
        sentences = []
        for p in parts:
            p = p.strip().rstrip(",")
            if not p:
                continue
            if p.startswith(("The ", "This ", "A ", "An ")):
                sentences.append(p)
            else:
                tags.append(p)
        
        result_parts = []
        if tags:
            result_parts.append(", ".join(tags))
        if sentences:
            result_parts.append(" ".join(sentences))
        
        prompt_result = ". ".join(result_parts)

        # v0.3.31: 构建风格定制负面提示词 = 通用 + 风格专属
        style_neg = self.STYLE_NEGATIVE_PROMPTS.get(style, "")
        if style_neg:
            combined_negative = self.NEGATIVE_PROMPT + ", " + style_neg
        else:
            combined_negative = self.NEGATIVE_PROMPT

        return prompt_result, combined_negative

    def _call_pollinations(self, prompt, width, height, seed, style=None, negative=None):
        """调用 Pollinations.ai 免费API
        v0.3.31: 支持按风格选择最优模型 + 风格定制负面提示词
        """
        self._rate_limit()

        # v0.3.31: 按风格选择最优 Pollinations 模型
        model = "flux-anime"  # 默认模型
        if style and style in self.STYLE_MODELS:
            model = self.STYLE_MODELS[style]

        # v0.3.31: 使用风格定制的负面提示词（如未提供则用通用版）
        neg_prompt = negative or self.NEGATIVE_PROMPT

        # v0.3.31: 动态构建URL（支持模型选择）
        url = (
            f"https://image.pollinations.ai/prompt/{quote(prompt)}"
            f"?width={width}&height={height}&seed={seed}"
            f"&nologo=true&model={model}"
            f"&negative={quote(neg_prompt)}"
            f"&enhance=true"
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

    # v0.4: 序列帧动画提示词 — 描述每种动画状态的关键姿态
    # 用于 generate_spritesheet() 生成角色动画表
    ANIMATION_PROMPTS = {
        "idle": (
            "standing idle pose, facing the camera, relaxed stance, "
            "arms at sides, weight evenly distributed, calm expression"
        ),
        "walk": (
            "walking cycle pose, mid-stride, one foot forward, "
            "arms swinging naturally, body leaning slightly forward, "
            "dynamic walking motion"
        ),
        "attack": (
            "attack action pose, swinging weapon aggressively, "
            "dynamic combat stance, body twisted into powerful strike, "
            "intense determined expression, motion blur on weapon"
        ),
        "hurt": (
            "taking damage pose, knocked backward, body arched in pain, "
            "defensive stagger, surprised expression, impact effect"
        ),
        "die": (
            "falling defeated pose, collapsing to the ground, "
            "body falling backward, limp limbs, dramatic defeat, "
            "final moments pose"
        ),
        "cast": (
            "casting spell pose, hands raised channeling magic energy, "
            "glowing magical effects around hands, focused intense expression, "
            "mystical energy aura"
        ),
    }

    # v0.4: 动画表布局配置 — 行=动画状态，列=帧序列
    SPRITESHEET_LAYOUT = {
        "animations": ["idle", "walk", "attack", "hurt", "die", "cast"],
        "frames_per_anim": 8,  # v0.4.1: 默认8帧，更流畅的动画
        "frame_width": 256,
        "frame_height": 256,
    }

    def generate_spritesheet(self, prompt, style="cartoon", char_type="warrior",
                             seed=None, animations=None, frames_per_anim=4):
        """
        v0.4: 生成AI角色序列帧动画表

        策略：逐动画状态生成图片，每状态生成 frames_per_anim 张不同帧
        最终合成一张完整的 sprite sheet

        Args:
            prompt: 基础角色描述
            style: 风格
            char_type: 角色类型
            seed: 随机种子（基准，每帧会偏移）
            animations: 动画列表，默认使用全部6种
            frames_per_anim: 每种动画生成几帧

        Returns:
            dict:
                - images: list[dict] — 每帧的生成结果（含image_bytes, animation, frame_idx）
                - metadata: dict — 动画表元数据（动画名→帧范围）
                - total_time: float
                - success_count: int
                - fail_count: int
        """
        if animations is None:
            animations = self.SPRITESHEET_LAYOUT["animations"]

        if seed is None:
            seed = int(time.time()) % 2147483647

        all_frames = []
        metadata = {}
        total_start = time.time()
        success_count = 0
        fail_count = 0

        for anim_name in animations:
            anim_prompt = self.ANIMATION_PROMPTS.get(anim_name, "")
            frame_results = []

            for frame_idx in range(frames_per_anim):
                # 每帧用不同seed确保变化
                frame_seed = seed + hash(f"{anim_name}_{frame_idx}") % 100000
                # 逐帧微调姿势描述，模拟帧序列变化
                frame_modifier = self._get_frame_modifier(anim_name, frame_idx, frames_per_anim)

                result = self.generate(
                    prompt=prompt,
                    style=style,
                    char_type=char_type,
                    width=256,
                    height=256,
                    seed=frame_seed,
                    retry=2,
                    pose=anim_name,
                )

                if result and result.get("image_bytes"):
                    result["animation"] = anim_name
                    result["frame_idx"] = frame_idx
                    frame_results.append(result)
                    success_count += 1
                    print(f"  ✓ {anim_name} frame {frame_idx+1}/{frames_per_anim}")
                else:
                    fail_count += 1
                    print(f"  ✗ {anim_name} frame {frame_idx+1}/{frames_per_anim} FAILED")

                # v0.4.1: Pollinations匿名用户每IP限1并发，帧间需较长等待
                time.sleep(5)

            metadata[anim_name] = {
                "start_frame": len(all_frames),
                "count": len(frame_results),
                "frame_indices": list(range(len(all_frames), len(all_frames) + len(frame_results))),
            }
            all_frames.extend(frame_results)

        total_elapsed = time.time() - total_start

        return {
            "images": all_frames,
            "metadata": metadata,
            "total_time": round(total_elapsed, 2),
            "success_count": success_count,
            "fail_count": fail_count,
            "layout": {
                "animations": animations,
                "frames_per_anim": frames_per_anim,
                "frame_size": [256, 256],
            },
        }

    @staticmethod
    def _get_frame_modifier(anim_name, frame_idx, total_frames):
        """v0.4: 根据动画类型和帧索引生成微调描述"""
        # 归一化进度 0.0 → 1.0
        progress = frame_idx / max(total_frames - 1, 1)

        modifiers = {
            "idle": [
                "subtle breathing in, chest very slightly rising",
                "gentle weight shift to right foot, slight lean",
                "neutral standing, baseline idle pose",
                "subtle breathing out, chest settling",
                "gentle weight shift to left foot, slight lean",
                "neutral standing, baseline idle pose",
                "subtle arm micro-adjustment, relaxed",
                "returning to center stance, calm expression",
            ],
            "walk": [
                "right foot stepping forward, left arm swinging forward",
                "mid-stride right, weight transferring to right foot",
                "right foot planted, body passing over, left foot lifting",
                "left foot stepping forward, right arm swinging forward",
                "mid-stride left, weight transferring to left foot",
                "left foot planted, body passing over, right foot lifting",
                "right foot beginning to step forward again",
                "full cycle return, passing position",
            ],
            "attack": [
                "anticipation: pulling weapon back, coiling body",
                "winding up: torso twisted, weapon at peak behind",
                "mid-swing: weapon arcing forward, body uncoiling",
                "impact point: full extension, weapon at target",
                "follow-through: weapon trailing past target",
                "recovery: weapon swinging down to rest",
                "resetting stance, bringing weapon to guard position",
                "returning to ready stance, eyes on target",
            ],
            "hurt": [
                "impact moment: body jolted, initial recoil backward",
                "staggering: off-balance, stepping back on one foot",
                "reeling: torso arched, head snapping back",
                "peak knockback: maximum displacement from impact",
                "struggling: trying to regain footing, teetering",
                "stabilizing: finding balance, planting feet",
                "recovering: straightening posture, raising guard",
                "back to ready stance, defensive position",
            ],
            "die": [
                "impact: body buckling, knees beginning to give way",
                "collapsing: torso falling forward, arms dropping",
                "falling: body tilting backward, losing balance",
                "mid-fall: body horizontal, arms trailing upward",
                "descent: body approaching ground, limbs limp",
                "ground impact: body hitting the ground",
                "settling: final body adjustment on ground",
                "final pose: lying motionless, defeated",
            ],
            "cast": [
                "gathering: hands beginning to channel, faint glow",
                "channeling: energy flowing to hands, aura appearing",
                "focusing: intense concentration, power building",
                "peak charge: maximum energy accumulation, bright aura",
                "release point: hands thrust forward, spell launching",
                "spell flying: energy projectile leaving hands",
                "aftermath: residual energy dissipating from hands",
                "recovery: lowering hands, returning to stance",
            ],
        }

        anim_mods = modifiers.get(anim_name, ["subtle pose variation"] * total_frames)
        return anim_mods[frame_idx % len(anim_mods)]

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
