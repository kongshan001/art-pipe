"""
ArtPipe 角色生成引擎 v0.3
支持三种渲染模式: procedural(程序化) / ai(AI生成) / hybrid(混合)
纯Python实现，零外部依赖
"""
import hashlib
import json
import math
import time
from .png_writer import create_png, create_spritesheet


class SeededRNG:
    """确定性随机数生成器"""
    def __init__(self, seed):
        self.seed = seed

    def next(self):
        self.seed = (self.seed * 16807 + 0) % 2147483647
        return (self.seed - 1) / 2147483646

    def range(self, lo, hi):
        return lo + self.next() * (hi - lo)

    def int_range(self, lo, hi):
        return int(self.range(lo, hi + 1))

    def pick(self, lst):
        return lst[self.int_range(0, len(lst) - 1)]


# ---- 风格配置 ----
STYLES = {
    "pixel": {
        "name": "像素风",
        "pixel_size": 4,
        "outline": True,
        "outline_color": (20, 20, 20),
        "saturation": 0.85,
        "palette_type": "retro",
    },
    "cartoon": {
        "name": "卡通手绘",
        "pixel_size": 1,
        "outline": True,
        "outline_color": (40, 30, 30),
        "saturation": 1.2,
        "palette_type": "vibrant",
    },
    "anime": {
        "name": "日式RPG",
        "pixel_size": 1,
        "outline": True,
        "outline_color": (60, 40, 50),
        "saturation": 1.1,
        "palette_type": "soft",
    },
    "western": {
        "name": "欧美写实",
        "pixel_size": 1,
        "outline": False,
        "outline_color": None,
        "saturation": 0.9,
        "palette_type": "muted",
    },
    "dark": {
        "name": "暗黑奇幻",
        "pixel_size": 1,
        "outline": True,
        "outline_color": (10, 5, 15),
        "saturation": 0.7,
        "palette_type": "dark",
    },
}

# ---- 调色板 ----
PALETTES = {
    "retro": [(233,74,56),(56,135,233),(56,193,118),(255,200,60),(200,80,200)],
    "vibrant": [(255,82,82),(64,196,255),(105,240,174),(255,213,79),(186,104,200)],
    "soft": [(255,154,162),(162,210,255),(162,255,200),(255,230,153),(210,162,255)],
    "muted": [(180,130,110),(110,150,180),(130,170,130),(180,170,120),(150,130,160)],
    "dark": [(140,40,50),(50,80,140),(60,120,80),(140,120,50),(100,50,120)],
}

# ---- 角色类型配置 ----
# v0.3.7: 增加面部表情(face_type)和体型比例(body_ratio/leg_ratio/arm_ratio)
# v0.3.9: 增加可选配件池(accessories) — 每次生成时随机选取0~2个配件
# face_type: "serious"=严肃(横线嘴+平眉), "cute"=可爱(微笑+弯眉),
#            "fierce"=凶猛(怒眉+龇牙), "gentle"=温柔(微笑+淡眉), "plain"=普通
# accessories: 该类型可选的配件列表，绘制时根据 seed 随机挑选
#   belt=腰带(身体中部横条纹), shoulder_pads=肩甲(肩膀处方形),
#   scarf=围巾(脖子处飘逸带), earing=耳环(头部侧面小点),
#   belt_pouch=腰包(侧面小方块), collar=衣领(脖子处环绕线)
CHAR_TYPES = {
    "warrior": {
        "name": "战士", "head_ratio": 0.18, "body_w": 0.35,
        "has_shield": True, "weapon": "sword",
        "face_type": "serious",
        "body_ratio": 1.15,  # 宽壮躯干
        "leg_ratio": 0.90,   # 短粗腿
        "arm_ratio": 1.10,   # 粗壮手臂
        "accessories": ["belt", "shoulder_pads", "scarf", "belt_pouch"],
    },
    "mage": {
        "name": "法师", "head_ratio": 0.20, "body_w": 0.28,
        "has_robe": True, "weapon": "staff",
        "face_type": "gentle",
        "body_ratio": 0.90,  # 纤细身体
        "leg_ratio": 1.15,   # 修长腿
        "arm_ratio": 0.95,   # 细长手臂
        "accessories": ["scarf", "collar", "earing"],
    },
    "archer": {
        "name": "弓箭手", "head_ratio": 0.19, "body_w": 0.25,
        "has_hood": True, "weapon": "bow",
        "face_type": "serious",
        "body_ratio": 0.92,  # 精瘦身体
        "leg_ratio": 1.10,   # 长腿（灵活）
        "arm_ratio": 1.15,   # 长臂（拉弓）
        "accessories": ["belt", "belt_pouch", "scarf", "earing"],
    },
    "rogue": {
        "name": "盗贼", "head_ratio": 0.17, "body_w": 0.22,
        "has_cape": True, "weapon": "dagger",
        "face_type": "fierce",
        "body_ratio": 0.85,  # 窄小身材
        "leg_ratio": 1.10,   # 灵活长腿
        "arm_ratio": 1.05,   # 匀称手臂
        "accessories": ["belt", "earing", "scarf", "belt_pouch"],
    },
    "healer": {
        "name": "治疗师", "head_ratio": 0.20, "body_w": 0.30,
        "has_wings": False, "weapon": "book",
        "face_type": "gentle",
        "body_ratio": 0.95,  # 正常体型
        "leg_ratio": 1.00,   # 正常腿
        "arm_ratio": 0.95,   # 纤细手臂
        "accessories": ["collar", "scarf", "earing"],
    },
    "monster": {
        "name": "怪物", "head_ratio": 0.30, "body_w": 0.40,
        "is_monster": True, "weapon": "claw",
        "face_type": "fierce",
        "body_ratio": 1.20,  # 宽大躯干
        "leg_ratio": 0.80,   # 粗短腿
        "arm_ratio": 1.20,   # 粗壮长臂
        "accessories": ["shoulder_pads"],
    },
    "npc": {
        "name": "NPC", "head_ratio": 0.20, "body_w": 0.26,
        "is_plain": True, "weapon": "none",
        "face_type": "cute",
        "body_ratio": 1.00,  # 标准体型
        "leg_ratio": 1.00,   # 标准腿
        "arm_ratio": 1.00,   # 标准手臂
        "accessories": ["scarf", "collar", "belt", "earing"],
    },
}

# v0.3.11: 发型配置 — 每个角色类型可选的发型池
# hair_styles: 该类型可选的发型列表，生成时根据 seed 随机选择
#   "short"     = 短发（头顶薄层）
#   "medium"    = 中发（覆盖头顶+侧面）
#   "long"      = 长发（延伸到肩部+背后）
#   "spiky"     = 刺猬头（多个三角尖刺）
#   "ponytail"  = 马尾（头顶+单根马尾垂下）
#   "mohawk"    = 莫西干（中央一条竖起的发型）
#   "bald"      = 光头（不画头发）
#   "side_part" = 偏分（一侧多一侧少的刘海）
HAIR_STYLES = {
    "warrior": ["short", "medium", "spiky", "mohawk"],
    "mage": ["long", "medium", "ponytail"],
    "archer": ["short", "medium", "side_part", "ponytail"],
    "rogue": ["short", "spiky", "side_part"],
    "healer": ["long", "medium", "ponytail", "side_part"],
    "monster": ["spiky", "bald"],
    "npc": ["short", "medium", "side_part", "long"],
}


class CharacterEngine:
    """服务端角色生成引擎"""

    CANVAS_W = 64
    CANVAS_H = 80

    def __init__(self):
        pass

    def hash_prompt(self, prompt):
        h = hashlib.md5(prompt.encode("utf-8")).hexdigest()
        return int(h, 16) % 2147483646 + 1

    def parse_prompt(self, prompt):
        """从自然语言提示词提取角色属性"""
        prompt_lower = prompt.lower()
        
        # 检测风格
        style = "cartoon"
        style_keywords = {
            "pixel": ["像素", "pixel", "8-bit", "8bit", "复古", "retro"],
            "cartoon": ["卡通", "cartoon", "手绘", "cute", "可爱"],
            "anime": ["日式", "anime", "rpg", "二次元", "jrpg"],
            "western": ["欧美", "western", "写实", "realistic"],
            "dark": ["暗黑", "dark", "哥特", "gothic", "恶魔", "demon"],
        }
        for s, kws in style_keywords.items():
            if any(kw in prompt_lower for kw in kws):
                style = s
                break

        # 检测类型（按优先级匹配，匹配到即停止）
        char_type = "warrior"
        type_keywords = {
            "mage": ["法师", "魔法师", "巫师", "mage", "wizard", "魔法", "少女", "术士", "sorcerer"],
            "monster": ["怪物", "史莱姆", "monster", "slime", "恶魔", "boss", "demon"],
            "archer": ["弓箭手", "猎人", "archer", "hunter", "弓"],
            "rogue": ["盗贼", "刺客", "rogue", "assassin", "thief", "匕首", "忍者", "ninja"],
            "healer": ["治疗", "牧师", "healer", "priest", "cleric", "修女", "僧侣"],
            "npc": ["村民", "商人", "npc", "villager", "店员", "老爷爷", "老奶奶"],
            "warrior": ["战士", "武士", "骑士", "warrior", "knight", "剑", "勇者"],
        }
        for t, kws in type_keywords.items():
            if any(kw in prompt_lower for kw in kws):
                char_type = t
                break

        # 检测颜色
        color = None
        color_map = {
            "red": (220, 60, 60), "红": (220, 60, 60),
            "blue": (60, 100, 220), "蓝": (60, 100, 220),
            "green": (60, 180, 80), "绿": (60, 180, 80),
            "yellow": (230, 200, 50), "黄": (230, 200, 50),
            "purple": (150, 60, 200), "紫": (150, 60, 200),
            "white": (230, 230, 230), "白": (230, 230, 230),
            "black": (40, 40, 45), "黑": (40, 40, 45),
            "gold": (220, 180, 50), "金": (220, 180, 50),
            "silver": (190, 195, 200), "银": (190, 195, 200),
        }
        for kw, rgb in color_map.items():
            if kw in prompt_lower:
                color = rgb
                break

        return {"style": style, "char_type": char_type, "color": color}

    def generate(self, prompt, style=None, char_type=None, seed=None,
                 render_mode="procedural", ai_backend="pollinations",
                 ai_width=512, ai_height=768):
        """
        核心生成接口：prompt → 完整角色资产包
        
        render_mode:
            "procedural" - 纯程序化渲染（v0.2默认，零延迟）
            "ai"         - AI图像生成（返回AI生成图+程序化骨骼/导出）
            "hybrid"     - 混合模式（AI图像作为参考，增强程序化渲染配色）
        """
        parsed = self.parse_prompt(prompt)
        
        s = style or parsed["style"]
        ct = char_type or parsed["char_type"]
        
        if seed is None:
            seed = self.hash_prompt(prompt)
        
        rng = SeededRNG(seed)
        style_cfg = STYLES.get(s, STYLES["cartoon"])
        type_cfg = CHAR_TYPES.get(ct, CHAR_TYPES["warrior"])
        
        # 生成调色板（v0.3.2: 增强色彩和谐度）
        base_palette = list(PALETTES[style_cfg["palette_type"]])
        if parsed["color"]:
            base_palette[0] = parsed["color"]
        # Fisher-Yates 洗牌保持随机性
        for i in range(len(base_palette) - 1, 0, -1):
            j = rng.int_range(0, i)
            base_palette[i], base_palette[j] = base_palette[j], base_palette[i]
        # 色彩和谐度优化：基于主色生成互补/类似色增强
        base_palette = self._harmonize_palette(base_palette, rng)
        
        char_id = f"char_{int(time.time())}_{seed % 10000}"
        
        # ---- 渲染模式分支 ----
        ai_result = None
        if render_mode in ("ai", "hybrid"):
            ai_result = self._generate_ai_image(
                prompt, s, ct, seed, ai_backend, ai_width, ai_height
            )
        
        # 程序化渲染（ai模式也做，保证spritesheet可用）
        animations = self._render_all_frames(rng, style_cfg, type_cfg, base_palette, ct)
        skeleton = self._generate_skeleton(type_cfg, base_palette)
        
        # 构建返回数据
        result = {
            "id": char_id,
            "prompt": prompt,
            "seed": seed,
            "style": s,
            "style_name": style_cfg["name"],
            "char_type": ct,
            "char_type_name": type_cfg["name"],
            "render_mode": render_mode,
            "canvas_size": {"width": self.CANVAS_W, "height": self.CANVAS_H},
            "palette": [list(c) for c in base_palette],
            "animations": {},
            "skeleton": skeleton,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        
        # AI图像数据
        if ai_result:
            result["ai_image"] = {
                "image_base64": ai_result["image_base64"],
                "prompt_used": ai_result["prompt_used"],
                "backend": ai_result["backend"],
                "generation_time": ai_result["generation_time"],
                "size": ai_result["size"],
                "format": ai_result.get("format", "JPEG"),
                "width": ai_width,
                "height": ai_height,
            }
            # v0.3.12: 缩略图（如果有）
            if ai_result.get("thumbnail_b64"):
                result["ai_image"]["thumbnail_b64"] = ai_result["thumbnail_b64"]
        
        # 附加各动画的帧数据（v0.3.3: 逐动画FPS，不同动画速度不同）
        anim_fps = {
            "idle": 4,    # 呼吸：慢节奏
            "walk": 10,   # 步行：中速
            "run": 14,    # 奔跑：快速
            "jump": 10,   # 跳跃：中速
            "attack": 12, # 攻击：快速挥砍
            "defend": 6,  # 防御：慢速稳定（v0.3.8）
            "hurt": 8,    # 受击：中等反应
            "die": 6,     # 死亡：慢速倒下
        }
        for anim_name, frames in animations.items():
            result["animations"][anim_name] = {
                "frame_count": len(frames),
                "fps": anim_fps.get(anim_name, 8),
                "loop": anim_name != "die",
            }
        
        # SpriteSheet PNG
        all_frames = []
        frame_map = {}
        for anim_name, frames in animations.items():
            frame_map[anim_name] = {"start": len(all_frames), "count": len(frames)}
            all_frames.extend(frames)
        
        cols = 8
        # v0.3.10: 传入frame_map用于PNG tEXt元数据嵌入
        spritesheet_png = create_spritesheet(all_frames, cols, self.CANVAS_W, self.CANVAS_H, frame_map=frame_map)
        
        result["spritesheet"] = {
            "png_base64": self._to_base64(spritesheet_png),
            "total_frames": len(all_frames),
            "cols": cols,
            "rows": (len(all_frames) + cols - 1) // cols,
            "frame_width": self.CANVAS_W,
            "frame_height": self.CANVAS_H,
            "frame_map": frame_map,
        }
        
        return result
    
    def _generate_ai_image(self, prompt, style, char_type, seed, backend, width, height):
        """调用AI图像生成"""
        try:
            from .sd_client import AIGenerator
            gen = AIGenerator(backend=backend)
            result = gen.generate(
                prompt=prompt, style=style, char_type=char_type,
                width=width, height=height, seed=seed, retry=3,
            )
            return result
        except Exception as e:
            print(f"[Engine] AI generation failed: {e}")
            return None

    def _harmonize_palette(self, palette, rng):
        """v0.3.5: 基于HSV色彩理论的真正色相和谐算法
        计算主色色相后，根据和谐模式旋转次要色的色相角度：
        - 类似色(analogous): ±30° 色相偏移，温暖协调
        - 三角色(triadic): ±120° 色相偏移，活泼对比
        - 分裂互补(split-complementary): ±150° 色相偏移，戏剧张力
        """
        if not palette or len(palette) < 2:
            return palette

        # --- 完整 RGB → HSV 转换 ---
        def rgb_to_hsv(r, g, b):
            r, g, b = r / 255.0, g / 255.0, b / 255.0
            mx, mn = max(r, g, b), min(r, g, b)
            diff = mx - mn
            # 色相 H (0~360)
            if diff == 0:
                h = 0
            elif mx == r:
                h = (60 * ((g - b) / diff) + 360) % 360
            elif mx == g:
                h = (60 * ((b - r) / diff) + 120) % 360
            else:
                h = (60 * ((r - g) / diff) + 240) % 360
            # 饱和度 S
            s = 0 if mx == 0 else diff / mx
            # 明度 V
            v = mx
            return h, s, v

        def hsv_to_rgb(h, s, v):
            h = h % 360
            c = v * s
            x = c * (1 - abs((h / 60) % 2 - 1))
            m = v - c
            if h < 60:
                r, g, b = c, x, 0
            elif h < 120:
                r, g, b = x, c, 0
            elif h < 180:
                r, g, b = 0, c, x
            elif h < 240:
                r, g, b = 0, x, c
            elif h < 300:
                r, g, b = x, 0, c
            else:
                r, g, b = c, 0, x
            return (
                min(255, max(0, int((r + m) * 255))),
                min(255, max(0, int((g + m) * 255))),
                min(255, max(0, int((b + m) * 255))),
            )

        # 提取主色HSV
        primary = palette[0]
        p_h, p_s, p_v = rgb_to_hsv(*primary)

        result = [primary]  # 主色保持不变

        # 用RNG选择和谐模式（避免所有角色用同一模式）
        harmony_modes = ["analogous", "triadic", "split_comp"]
        # 类似色概率50%，三角色30%，分裂互补20%
        roll = rng.next()
        if roll < 0.5:
            mode = "analogous"
        elif roll < 0.8:
            mode = "triadic"
        else:
            mode = "split_comp"

        for i in range(1, len(palette)):
            r, g, b = palette[i]
            h, s, v = rgb_to_hsv(r, g, b)

            # 根据和谐模式旋转色相
            if mode == "analogous":
                # 类似色：向主色色相方向旋转，偏移 ±25°
                hue_offset = (rng.next() - 0.5) * 50  # -25° ~ +25°
                new_h = p_h + hue_offset
                # 饱和度微调：保持原色饱和度但略微向主色靠拢
                new_s = s * 0.7 + p_s * 0.3
                # 明度保持原值但略微收敛
                new_v = v * 0.85 + p_v * 0.15
            elif mode == "triadic":
                # 三角色：偏移 ±120° 产生互补对比
                sign = 1 if rng.next() > 0.5 else -1
                hue_offset = sign * 120 + (rng.next() - 0.5) * 20  # ±10°抖动
                new_h = p_h + hue_offset
                # 三角色模式降低饱和度以避免过于刺眼
                new_s = min(s, p_s) * 0.85
                new_v = v * 0.8 + p_v * 0.2
            else:
                # 分裂互补：偏移 ±150°
                sign = 1 if rng.next() > 0.5 else -1
                hue_offset = sign * 150 + (rng.next() - 0.5) * 20
                new_h = p_h + hue_offset
                new_s = s * 0.6 + p_s * 0.4
                new_v = v * 0.75 + p_v * 0.25

            result.append(hsv_to_rgb(new_h, new_s, new_v))

        return result

    def _render_all_frames(self, rng, style_cfg, type_cfg, palette, char_type_key="warrior"):
        """渲染7种动画的帧（v0.3.11: 传入char_type_key用于发型选择）"""
        animations = {}
        
        # v0.3.11: 在所有帧之前一次性选择发型和纹理（保证帧间一致性）
        hair_pool = HAIR_STYLES.get(char_type_key, ["short", "medium"])
        hair_style = hair_pool[rng.int_range(0, len(hair_pool) - 1)]
        texture_patterns = ["solid", "horizontal_stripe", "checkerboard", "diamond", "v_stripe"]
        cloth_texture = texture_patterns[rng.int_range(0, len(texture_patterns) - 1)]
        
        anim_configs = {
            "idle":   {"frames": 4},
            "walk":   {"frames": 6},
            "run":    {"frames": 6},
            "jump":   {"frames": 6},  # v0.3.2: 跳跃动画
            "attack": {"frames": 6},
            "defend": {"frames": 5},  # v0.3.8: 防御动画
            "hurt":   {"frames": 3},
            "die":    {"frames": 6},
        }
        
        for anim_name, cfg in anim_configs.items():
            frames = []
            for f in range(cfg["frames"]):
                t = f / max(cfg["frames"] - 1, 1)
                # 计算当前帧的肢体姿态参数
                pose = self._calc_pose(anim_name, t)
                # 每帧独立渲染（含肢体偏移）
                frame = self._render_character(rng, style_cfg, type_cfg, palette, f, anim_name, pose, char_type_key, hair_style, cloth_texture)
                # 后处理：特殊效果
                if anim_name == "hurt" and int(t * 4) % 2 == 0:
                    # 受击白闪效果
                    frame = self._apply_flash(frame, 80)
                elif anim_name == "die":
                    # 死亡渐隐
                    alpha = max(0, int(255 * (1 - t)))
                    frame = self._apply_alpha(frame, alpha)
                frames.append(frame)
            animations[anim_name] = frames
        
        return animations
    
    def _calc_pose(self, anim, t):
        """根据动画类型和时间计算各肢体偏移量
        返回一个 pose dict，包含：
            left_leg_dx, left_leg_dy  — 左腿偏移
            right_leg_dx, right_leg_dy — 右腿偏移
            left_arm_dx, left_arm_dy   — 左臂偏移
            right_arm_dx, right_arm_dy — 右臂偏移（武器侧）
            body_dy                    — 身体整体Y偏移
            head_dy                    — 头部Y偏移
            weapon_angle               — 武器旋转角度（用于攻击）
        """
        pose = {
            "left_leg_dx": 0, "left_leg_dy": 0,
            "right_leg_dx": 0, "right_leg_dy": 0,
            "left_arm_dx": 0, "left_arm_dy": 0,
            "right_arm_dx": 0, "right_arm_dy": 0,
            "body_dy": 0, "head_dy": 0,
            "weapon_angle": 0,
            "body_scale_x": 1.0,  # v0.3.8: 胸腔横向缩放（呼吸）
        }
        
        if anim == "idle":
            # v0.3.8: 增强呼吸动画 — 浮动+胸腔扩张+手臂微摆
            breath = math.sin(t * math.pi * 2)
            pose["body_dy"] = int(breath * 1.5)
            pose["head_dy"] = int(breath * 1.5)
            # 胸腔横向缩放：吸气膨胀，呼气收缩（±6%）
            pose["body_scale_x"] = 1.0 + breath * 0.06
            # 手臂随呼吸微微摆动（延迟0.3弧度）
            arm_sway = math.sin(t * math.pi * 2 + 0.3)
            pose["left_arm_dy"] = round(arm_sway * 1.5)
            pose["right_arm_dy"] = round(arm_sway * 1.5)
            
        elif anim == "walk":
            # 腿交替迈步 + 轻微身体上下浮动
            phase = t * math.pi * 2
            pose["left_leg_dx"] = int(math.sin(phase) * 2)
            pose["left_leg_dy"] = -int(abs(math.sin(phase)) * 2)
            pose["right_leg_dx"] = int(math.sin(phase + math.pi) * 2)
            pose["right_leg_dy"] = -int(abs(math.sin(phase + math.pi)) * 2)
            pose["body_dy"] = -int(abs(math.sin(phase * 2)) * 1)
            pose["head_dy"] = pose["body_dy"]
            # 手臂自然摆动（与腿反向）
            pose["left_arm_dx"] = int(math.sin(phase + math.pi) * 1)
            pose["right_arm_dx"] = int(math.sin(phase) * 1)
            
        elif anim == "run":
            # 更大幅度的腿交替 + 身体前倾
            phase = t * math.pi * 2
            pose["left_leg_dx"] = int(math.sin(phase) * 3)
            pose["left_leg_dy"] = -int(abs(math.sin(phase)) * 3)
            pose["right_leg_dx"] = int(math.sin(phase + math.pi) * 3)
            pose["right_leg_dy"] = -int(abs(math.sin(phase + math.pi)) * 3)
            pose["body_dy"] = -int(abs(math.sin(phase * 2)) * 2)
            pose["head_dy"] = pose["body_dy"]
            pose["left_arm_dx"] = int(math.sin(phase + math.pi) * 2)
            pose["right_arm_dx"] = int(math.sin(phase) * 2)
            pose["left_arm_dy"] = -int(abs(math.sin(phase + math.pi)) * 1)
            pose["right_arm_dy"] = -int(abs(math.sin(phase)) * 1)
            
        elif anim == "jump":
            # v0.3.2: 跳跃动画 - 蹲→起跳→滞空→落地
            # t: 0~0.15蹲, 0.15~0.35起跳上升, 0.35~0.65滞空, 0.65~1.0下落落地
            if t < 0.15:
                # 蹲下蓄力
                squat = t / 0.15  # 0→1
                pose["body_dy"] = int(squat * 3)
                pose["head_dy"] = int(squat * 2)
                pose["left_leg_dx"] = -1
                pose["right_leg_dx"] = 1
                pose["left_leg_dy"] = int(squat * 1)
                pose["right_leg_dy"] = int(squat * 1)
            elif t < 0.35:
                # 起跳上升（身体上升，腿收起）
                lift = (t - 0.15) / 0.2  # 0→1
                pose["body_dy"] = -int(lift * 8)
                pose["head_dy"] = -int(lift * 8)
                pose["left_arm_dy"] = -int(lift * 3)
                pose["right_arm_dy"] = -int(lift * 3)
                pose["left_leg_dy"] = -int(lift * 2)
                pose["right_leg_dy"] = -int(lift * 2)
            elif t < 0.65:
                # 滞空最高点（展开姿态）
                pose["body_dy"] = -8
                pose["head_dy"] = -8
                pose["left_arm_dx"] = -3
                pose["left_arm_dy"] = -3
                pose["right_arm_dx"] = 3
                pose["right_arm_dy"] = -3
                pose["left_leg_dy"] = -2
                pose["right_leg_dy"] = -2
            else:
                # 下落并落地
                fall = (t - 0.65) / 0.35  # 0→1
                pose["body_dy"] = -int(8 * (1 - fall))
                pose["head_dy"] = -int(8 * (1 - fall))
                pose["left_arm_dx"] = -int(3 * (1 - fall))
                pose["right_arm_dx"] = int(3 * (1 - fall))
                if fall > 0.7:
                    # 着地缓冲
                    cushion = (fall - 0.7) / 0.3
                    pose["body_dy"] = int(cushion * 2)
                    pose["head_dy"] = int(cushion * 1)
                    pose["left_leg_dy"] = int(cushion * 1)
                    pose["right_leg_dy"] = int(cushion * 1)
        
        elif anim == "attack":
            # 攻击：右臂（武器侧）前伸 → 收回（v0.3.6: 身体前冲+头部后仰分离）
            # t: 0=蓄力, 0.4=挥出, 1.0=收回
            if t < 0.4:
                # 蓄力阶段：武器后拉，身体微微后坐
                swing = t / 0.4  # 0→1
                pose["right_arm_dx"] = -int(swing * 3)
                pose["right_arm_dy"] = -int(swing * 2)
                pose["weapon_angle"] = -swing * 0.5
                pose["body_dy"] = int(swing * 1)  # 后坐
                pose["head_dy"] = int(swing * 1)  # 头随身体
            else:
                # 挥出阶段：快速前刺，身体前冲但头部保持
                swing = (t - 0.4) / 0.6  # 0→1
                retract = max(0, 1 - swing * 1.5)
                pose["right_arm_dx"] = int(5 * (1 - retract))
                pose["right_arm_dy"] = -int(3 * (1 - retract))
                pose["body_dy"] = -int(swing * 2)  # 身体前冲（独立于头部）
                pose["head_dy"] = int(max(0, 1 - swing * 2))  # 头部略微后仰后恢复
                pose["weapon_angle"] = (1 - retract) * 1.0
            # 前冲时左腿后蹬
            if t > 0.3:
                pose["left_leg_dx"] = -2
                pose["right_leg_dx"] = 1
            
        elif anim == "hurt":
            # 受击：整体后仰
            pose["body_dy"] = int(t * 2)
            pose["head_dy"] = int(t * 3)
            pose["left_arm_dx"] = int(t * 2)
            pose["right_arm_dx"] = int(t * 2)
            
        elif anim == "defend":
            # v0.3.8: 防御动画 — 重心下沉+手臂护身+微颤抖
            if t < 0.25:
                # 准备阶段：重心下移，手臂举起
                prep = t / 0.25  # 0→1
                pose["body_dy"] = int(prep * 3)
                pose["head_dy"] = int(prep * 2)
                pose["left_arm_dx"] = -int(prep * 2)
                pose["left_arm_dy"] = -int(prep * 4)
                pose["right_arm_dx"] = int(prep * 1)
                pose["right_arm_dy"] = -int(prep * 3)
                pose["left_leg_dy"] = int(prep * 1)
                pose["right_leg_dy"] = int(prep * 1)
            else:
                # 稳定防御姿态（带轻微颤抖感）
                hold = (t - 0.25) / 0.75
                tremor = round(math.sin(hold * math.pi * 8) * 1.2)
                pose["body_dy"] = 3 + tremor
                pose["head_dy"] = 2
                pose["left_arm_dx"] = -2
                pose["left_arm_dy"] = -4
                pose["right_arm_dx"] = 1
                pose["right_arm_dy"] = -3
                pose["left_leg_dy"] = 1
                pose["right_leg_dy"] = 1
                # 微微张腿（更稳的防御站姿）
                pose["left_leg_dx"] = -1
                pose["right_leg_dx"] = 1
        
        elif anim == "die":
            # 死亡：身体下沉
            pose["body_dy"] = int(t * 8)
            pose["head_dy"] = int(t * 10)
            pose["left_arm_dx"] = int(t * 2)
            pose["right_arm_dx"] = int(t * 2)
            pose["left_leg_dx"] = int(t * 1)
            pose["right_leg_dx"] = int(t * -1)
        
        return pose

    def _render_character(self, rng, style_cfg, type_cfg, palette, frame_idx, anim, pose=None, char_type_key="warrior", hair_style="short", cloth_texture="solid"):
        """渲染单帧角色像素数据（v0.3.11: 多发型系统+服装纹理）"""
        W, H = self.CANVAS_W, self.CANVAS_H
        ps = style_cfg["pixel_size"]
        
        # 无 pose 时使用默认（无偏移）
        if pose is None:
            pose = {
                "left_leg_dx": 0, "left_leg_dy": 0,
                "right_leg_dx": 0, "right_leg_dy": 0,
                "left_arm_dx": 0, "left_arm_dy": 0,
                "right_arm_dx": 0, "right_arm_dy": 0,
                "body_dy": 0, "head_dy": 0,
                "weapon_angle": 0,
                "body_scale_x": 1.0,
            }
        
        # v0.3.9: 根据 seed 随机选择0~2个配件
        available_acc = type_cfg.get("accessories", [])
        chosen_acc = []
        if available_acc:
            # 洗牌后取前N个（N由seed决定）
            acc_pool = list(available_acc)
            for i in range(len(acc_pool) - 1, 0, -1):
                j = rng.int_range(0, i)
                acc_pool[i], acc_pool[j] = acc_pool[j], acc_pool[i]
            # 随机选择0~2个（70%概率选1个，20%选2个，10%不选）
            roll = rng.next()
            if roll < 0.70:
                n_acc = 1
            elif roll < 0.90:
                n_acc = 2
            else:
                n_acc = 0
            chosen_acc = acc_pool[:n_acc]
        
        # 创建空白画布 (RGBA)
        canvas = [[(0,0,0,0) for _ in range(W)] for _ in range(H)]
        
        cx, cy = W // 2, H // 2
        skin = palette[0] if not type_cfg.get("is_monster") else (palette[3])
        body_color = palette[1]
        accent = palette[2]
        hair_color = palette[3]
        outline = style_cfg.get("outline_color")
        
        # v0.3.9: 预计算颜色分层 — 深色/中间色/高光
        body_dark = (max(0, body_color[0]-30), max(0, body_color[1]-30), max(0, body_color[2]-30))
        body_light = (min(255, body_color[0]+20), min(255, body_color[1]+20), min(255, body_color[2]+20))
        accent_dark = (max(0, accent[0]-25), max(0, accent[1]-25), max(0, accent[2]-25))
        accent_light = (min(255, accent[0]+30), min(255, accent[1]+30), min(255, accent[2]+30))
        
        # 根据类型调整比例（v0.3.7: 应用体型比例差异化）
        head_r = int(H * type_cfg.get("head_ratio", 0.19) / 2)
        body_ratio = type_cfg.get("body_ratio", 1.0)
        leg_ratio = type_cfg.get("leg_ratio", 1.0)
        arm_ratio = type_cfg.get("arm_ratio", 1.0)
        body_w = int(W * type_cfg.get("body_w", 0.25) * body_ratio)
        body_h = int(H * 0.35 * body_ratio)
        # v0.3.8: 呼吸缩放宽度（仅影响身体矩形绘制，不影响肢体定位）
        body_draw_w = int(body_w * pose.get("body_scale_x", 1.0))
        leg_h = int(H * 0.2 * leg_ratio)
        
        # 应用 body_dy/head_dy 独立偏移（v0.3.6修复：body_dy 真正影响躯干位置）
        body_dy = pose["body_dy"]
        head_dy = pose["head_dy"]
        
        # 头部位置：仅受 head_dy 影响
        head_cy = cy - body_h // 2 - head_r + 2 + head_dy
        # 身体位置：基础位置 + body_dy 独立偏移（不再跟随头部head_dy）
        body_top_base = cy - body_h // 2 + 2 + 1  # 颈部基准位置
        body_top = body_top_base + body_dy
        body_bot = body_top + body_h
        leg_top = body_bot + 1
        
        # ---- 绘制头部 ----
        face_type = type_cfg.get("face_type", "plain")
        for y in range(max(0, head_cy - head_r), min(H, head_cy + head_r)):
            for x in range(max(0, cx - head_r), min(W, cx + head_r)):
                dx, dy = x - cx, y - head_cy
                if dx*dx + dy*dy <= head_r*head_r:
                    canvas[y][x] = (*skin, 255)
                    
                    # ---- v0.3.7: 增强面部细节 ----
                    # 眉毛区域（眼睛上方1-2像素）
                    brow_y = -ps - 1
                    brow_zone_y = dy == brow_y or dy == brow_y - 1
                    brow_inner = abs(dx) >= head_r//3 and abs(dx) <= head_r//2
                    
                    if brow_zone_y and brow_inner:
                        if face_type == "fierce":
                            # 怒眉：内低外高（向内倾斜）
                            brow_offset = 1 if dx > 0 else -1
                            if dy == brow_y and abs(dx) <= head_r//2 - 1:
                                canvas[y][x] = (max(0, skin[0]-80), max(0, skin[1]-80), max(0, skin[2]-80), 255)
                            elif dy == brow_y - 1 and abs(dx) >= head_r//3 + 1:
                                canvas[y][x] = (max(0, skin[0]-60), max(0, skin[1]-60), max(0, skin[2]-60), 255)
                        elif face_type == "gentle":
                            # 温柔淡眉：浅色短横线
                            if dy == brow_y and abs(dx) >= head_r//3 + 1 and abs(dx) <= head_r//2 - 2:
                                canvas[y][x] = (max(0, skin[0]-30), max(0, skin[1]-30), max(0, skin[2]-30), 255)
                        elif face_type == "serious":
                            # 严肃平眉：深色横线
                            if dy == brow_y:
                                canvas[y][x] = (max(0, skin[0]-70), max(0, skin[1]-70), max(0, skin[2]-70), 255)
                        elif face_type == "cute":
                            # 可爱弯眉：弧形短眉
                            brow_curve = 1 if abs(dx) <= head_r//3 + 2 else 0
                            if dy == brow_y - brow_curve:
                                canvas[y][x] = (max(0, skin[0]-50), max(0, skin[1]-50), max(0, skin[2]-50), 255)
                    
                    # 眼睛（v0.3.2: 虹膜+瞳孔+高光三层结构）
                    eye_zone_y = abs(dy) <= ps
                    eye_zone_x = abs(dx) >= head_r//3 and abs(dx) <= head_r//2
                    if eye_zone_y and eye_zone_x:
                        # 虹膜：使用accent颜色的暗色调
                        iris_color = (min(255, accent[0]+30), min(255, accent[1]+30), min(255, accent[2]+30))
                        canvas[y][x] = (*iris_color, 255)
                        # 瞳孔：眼睛中心偏内的一格（缩小dx范围）
                        if abs(dx) >= head_r//3 + max(1, ps//2) and abs(dx) <= head_r//2 - max(1, ps//2):
                            canvas[y][x] = (15, 15, 25, 255)
                    # 眼睛高光（右上方小白点，让眼睛有神）
                    if dy == -ps//2 and dx == head_r//3 + max(1, ps//2):
                        canvas[y][x] = (255, 255, 255, 255)
                    if dy == -ps//2 and dx == -(head_r//3 + max(1, ps//2)):
                        canvas[y][x] = (255, 255, 255, 255)
                    
                    # 鼻子（v0.3.7: 微小像素鼻子，增加面部立体感）
                    if dy == 1 and dx == 0:
                        # 鼻尖：比肤色略深的单像素点
                        nose_color = (max(0, skin[0]-25), max(0, skin[1]-15), max(0, skin[2]-15))
                        canvas[y][x] = (*nose_color, 255)
                    if dy == 0 and dx == 0:
                        # 鼻梁高光：比肤色略亮的单像素点
                        nose_hl = (min(255, skin[0]+15), min(255, skin[1]+15), min(255, skin[2]+10))
                        canvas[y][x] = (*nose_hl, 255)
                    
                    # 嘴巴（v0.3.7: 按face_type绘制不同嘴型）
                    mouth_y = head_r//3 + 1
                    if dy >= mouth_y and dy <= mouth_y + 1 and abs(dx) <= head_r//4:
                        if face_type == "cute" or face_type == "gentle":
                            # 微笑：弧形嘴巴（下凹弧线）
                            if dy == mouth_y and abs(dx) <= head_r//5:
                                canvas[y][x] = (200, 90, 90, 255)
                            # 微笑弧角（两端上翘）
                            if dy == mouth_y - 1 and (abs(dx) == head_r//5 or abs(dx) == head_r//5 + 1):
                                canvas[y][x] = (200, 90, 90, 255)
                        elif face_type == "fierce":
                            # 龇牙/怒嘴：横向一字嘴+可选尖牙
                            if dy == mouth_y and abs(dx) <= head_r//4:
                                canvas[y][x] = (160, 50, 50, 255)
                            # 尖牙（怪物和盗贼特有）
                            if dy == mouth_y + 1 and abs(dx) == head_r//5:
                                canvas[y][x] = (240, 240, 230, 255)
                        elif face_type == "serious":
                            # 严肃直线嘴
                            if dy == mouth_y and abs(dx) <= head_r//5:
                                canvas[y][x] = (170, 70, 70, 255)
                        else:
                            # 普通小嘴
                            if dy == mouth_y and abs(dx) <= head_r//6:
                                canvas[y][x] = (180, 80, 80, 255)
                    
                    # 腮红（v0.3.7: cute/gentle类型增加淡粉色腮红）
                    if (face_type == "cute" or face_type == "gentle"):
                        blush_y = head_r//4
                        if dy == blush_y and (abs(dx) == head_r//2 + 1 or abs(dx) == head_r//2 + 2):
                            blush_color = (min(255, skin[0]+40), min(255, skin[1]-10), min(255, skin[2]-20))
                            if canvas[y][x][3] > 0:
                                old_r, old_g, old_b, old_a = canvas[y][x]
                                canvas[y][x] = (
                                    (old_r + blush_color[0]) // 2,
                                    (old_g + blush_color[1]) // 2,
                                    (old_b + blush_color[2]) // 2,
                                    old_a
                                )
        
        # ---- v0.3.11: 多发型渲染系统 ----
        # 发型由 _render_all_frames 在帧循环前一次性选定
        # 头发深色（阴影层）
        hair_dark = (max(0, hair_color[0]-40), max(0, hair_color[1]-40), max(0, hair_color[2]-40))
        # 头发高光
        hair_light = (min(255, hair_color[0]+30), min(255, hair_color[1]+30), min(255, hair_color[2]+30))

        if hair_style != "bald":
            if hair_style == "short":
                # 短发：头顶薄层（覆盖头部上半部分）
                for y in range(max(0, head_cy - head_r - ps), head_cy - head_r//3):
                    for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps)):
                        dx, dy = x - cx, y - head_cy
                        if dx*dx + (dy+ps)*(dy+ps) <= (head_r+ps)*(head_r+ps) and dy < -head_r//3:
                            canvas[y][x] = (*hair_color, 255)
                # 刘海高光
                hl_y = max(0, head_cy - head_r - ps + 1)
                for x in range(max(0, cx - head_r//2), min(W, cx + head_r//2)):
                    if 0 <= hl_y < H and canvas[hl_y][x][3] == 0:
                        canvas[hl_y][x] = (*hair_light, 255)

            elif hair_style == "medium":
                # 中发：覆盖头顶+两侧到耳朵位置
                for y in range(max(0, head_cy - head_r - ps), head_cy + head_r//4):
                    for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps)):
                        dx, dy = x - cx, y - head_cy
                        # 椭圆形头发覆盖
                        hair_rx = head_r + ps
                        hair_ry = head_r + ps
                        if dx*dx + (dy+ps)*(dy+ps) <= hair_rx*hair_ry and dy < 0:
                            canvas[y][x] = (*hair_color, 255)
                        # 两侧延伸
                        elif abs(dy) <= head_r//3 and abs(dx) >= head_r - ps and abs(dx) <= head_r + ps:
                            canvas[y][x] = (*hair_dark, 255)
                # 顶部高光弧线
                hl_y = max(0, head_cy - head_r - ps + 1)
                for x in range(max(0, cx - head_r//2), min(W, cx + head_r//2)):
                    if 0 <= hl_y < H:
                        dx = x - cx
                        if dx*dx <= (head_r//2)*(head_r//2):
                            canvas[hl_y][x] = (*hair_light, 255)

            elif hair_style == "long":
                # 长发：覆盖头顶+延伸到肩部背后
                # 头顶部分
                for y in range(max(0, head_cy - head_r - ps), head_cy + head_r//3):
                    for x in range(max(0, cx - head_r - ps*2), min(W, cx + head_r + ps*2)):
                        dx, dy = x - cx, y - head_cy
                        hair_rx = head_r + ps*2
                        hair_ry = head_r + ps
                        if dx*dx + (dy+ps)*(dy+ps) <= hair_rx*hair_ry and dy < 0:
                            canvas[y][x] = (*hair_color, 255)
                # 两侧长发垂下到肩部
                hair_drop_top = head_cy
                hair_drop_bot = min(H, body_top + body_h // 3)
                for y in range(hair_drop_top, hair_drop_bot):
                    # 左侧
                    for x in range(max(0, cx - head_r - ps*2), max(0, cx - head_r + ps)):
                        if 0 <= x < W:
                            canvas[y][x] = (*hair_dark, 255)
                    # 右侧
                    for x in range(min(W, cx + head_r - ps), min(W, cx + head_r + ps*2)):
                        if 0 <= x < W:
                            canvas[y][x] = (*hair_dark, 255)
                # 顶部高光
                hl_y = max(0, head_cy - head_r - ps + 1)
                for x in range(max(0, cx - head_r//2), min(W, cx + head_r//2)):
                    if 0 <= hl_y < H:
                        dx = x - cx
                        if dx*dx <= (head_r//2)*(head_r//2):
                            canvas[hl_y][x] = (*hair_light, 255)

            elif hair_style == "spiky":
                # 刺猬头：多个三角尖刺从头顶伸出
                num_spikes = 5
                spike_base_y = head_cy - head_r + ps
                for i in range(num_spikes):
                    # 每根刺的X位置均匀分布在头顶
                    spike_x = cx - head_r + int((i + 0.5) * (2 * head_r) / num_spikes)
                    spike_h = head_r // 2 + (i % 2) * (head_r // 3)  # 交替高低
                    spike_w = max(ps, 2)
                    # 画三角形尖刺
                    for dy in range(spike_h):
                        tip_y = spike_base_y - spike_h + dy
                        half_w = max(1, (spike_h - dy) * spike_w // spike_h)
                        for dx in range(-half_w, half_w + 1):
                            px = spike_x + dx
                            if 0 <= tip_y < H and 0 <= px < W:
                                canvas[tip_y][px] = (*hair_color, 255)
                    # 尖端高光
                    tip_y = spike_base_y - spike_h
                    if 0 <= tip_y < H and 0 <= spike_x < W:
                        canvas[tip_y][spike_x] = (*hair_light, 255)
                # 底部连接层（头顶填充）
                for y in range(max(0, head_cy - head_r - ps), spike_base_y):
                    for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps)):
                        dx, dy = x - cx, y - head_cy
                        if dx*dx + (dy+ps)*(dy+ps) <= (head_r+ps)*(head_r+ps) and dy < -head_r//3:
                            canvas[y][x] = (*hair_color, 255)

            elif hair_style == "ponytail":
                # 马尾：头顶覆盖 + 一根辫子垂到背后
                # 头顶部分（类似medium）
                for y in range(max(0, head_cy - head_r - ps), head_cy):
                    for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps)):
                        dx, dy = x - cx, y - head_cy
                        if dx*dx + (dy+ps)*(dy+ps) <= (head_r+ps)*(head_r+ps) and dy < -head_r//3:
                            canvas[y][x] = (*hair_color, 255)
                # 马尾辫：从头顶右侧偏后延伸向下，带轻微波浪
                tail_start_x = cx + head_r // 2
                tail_start_y = head_cy - head_r + ps
                tail_len = min(H - tail_start_y, body_h + leg_h // 2)
                for dy in range(tail_len):
                    wave = int(math.sin(dy * 0.15 + frame_idx * 0.2) * ps)
                    ty = tail_start_y + dy
                    for dx in range(-ps, ps + 1):
                        tx = tail_start_x + wave + dx
                        if 0 <= ty < H and 0 <= tx < W:
                            canvas[ty][tx] = (*hair_dark, 255)
                    # 马尾高光线
                    if 0 <= ty < H and 0 <= tail_start_x + wave < W:
                        canvas[ty][tail_start_x + wave] = (*hair_light, 255)
                # 头顶高光
                hl_y = max(0, head_cy - head_r - ps + 1)
                for x in range(max(0, cx - head_r//3), min(W, cx + head_r//3)):
                    if 0 <= hl_y < H:
                        canvas[hl_y][x] = (*hair_light, 255)

            elif hair_style == "mohawk":
                # 莫西干：中央一条竖起的发型
                mohawk_w = max(ps, 3)
                mohawk_h = head_r + ps * 4
                mohawk_base_y = head_cy - head_r + ps
                for dy in range(mohawk_h):
                    y_pos = mohawk_base_y - mohawk_h + dy
                    # 逐渐收窄
                    width_here = max(1, mohawk_w - int(dy * mohawk_w / mohawk_h))
                    for dx in range(-width_here, width_here + 1):
                        px = cx + dx
                        if 0 <= y_pos < H and 0 <= px < W:
                            canvas[y_pos][px] = (*hair_color, 255)
                # 顶部尖端高光
                tip_y = mohawk_base_y - mohawk_h
                if 0 <= tip_y < H:
                    canvas[tip_y][cx] = (*hair_light, 255)

            elif hair_style == "side_part":
                # 偏分：一侧多一侧少的刘海
                # 右侧多（覆盖到眉毛）
                for y in range(max(0, head_cy - head_r - ps), head_cy):
                    for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps)):
                        dx, dy = x - cx, y - head_cy
                        if dx*dx + (dy+ps)*(dy+ps) <= (head_r+ps)*(head_r+ps) and dy < -head_r//3:
                            canvas[y][x] = (*hair_color, 255)
                        # 右侧额外刘海（延伸到更低位置）
                        elif 0 <= dy and dy <= head_r//3 and dx >= head_r//4 and dx <= head_r + ps:
                            if dx*dx + dy*dy <= (head_r+ps)*(head_r+ps):
                                canvas[y][x] = (*hair_dark, 255)
                # 偏分线（头顶的分界线）
                part_y = max(0, head_cy - head_r - ps + 1)
                part_x = cx + head_r // 3
                if 0 <= part_y < H and 0 <= part_x < W:
                    canvas[part_y][part_x] = (*skin, 255)
                # 高光
                for x in range(max(0, cx - head_r//3), min(W, cx + head_r//3)):
                    if 0 <= part_y < H:
                        canvas[part_y][x] = (*hair_light, 255)
        
        # ---- 绘制身体（v0.3.11: 颜色分层+服装纹理图案渲染） ----
        # 纹理由 _render_all_frames 在帧循环前一次性选定
        
        for y in range(body_top, min(H, body_bot)):
            # v0.3.9: 纵向颜色渐变 — 顶部高光、底部深色
            if body_bot > body_top:
                vert_t = (y - body_top) / (body_bot - body_top)  # 0=顶 1=底
            else:
                vert_t = 0.5
            # 上30%用高光色，中间40%用原色，下30%用深色
            if vert_t < 0.3:
                row_color = body_light
            elif vert_t > 0.7:
                row_color = body_dark
            else:
                row_color = body_color
            
            for x in range(max(0, cx - body_draw_w//2), min(W, cx + body_draw_w//2)):
                # v0.3.9: 横向也做微妙渐变（中心亮、边缘暗）
                h_dist = abs(x - cx) / max(1, body_draw_w // 2)  # 0=中心 1=边缘
                if h_dist > 0.7:
                    # 边缘区域用略深色模拟侧面阴影
                    fx_color = (max(0, row_color[0]-10), max(0, row_color[1]-10), max(0, row_color[2]-10))
                else:
                    fx_color = row_color
                
                # v0.3.11: 服装纹理图案叠加
                use_accent = False
                local_x = x - (cx - body_draw_w//2)  # 相对身体左边缘的X坐标
                local_y = y - body_top               # 相对身体顶部的Y坐标
                
                if cloth_texture == "horizontal_stripe":
                    # 横条纹：每隔2行交替颜色
                    if local_y % 4 < 2 and abs(x - cx) > ps:
                        use_accent = True
                elif cloth_texture == "checkerboard":
                    # 棋盘格：2x2像素方块交替
                    if (local_x // 2 + local_y // 2) % 2 == 0 and abs(x - cx) > ps:
                        use_accent = True
                elif cloth_texture == "diamond":
                    # 菱形图案：交叉斜线形成菱形
                    if (local_x + local_y) % 4 < 1 or (local_x - local_y) % 4 < 1:
                        if abs(x - cx) > ps:
                            use_accent = True
                elif cloth_texture == "v_stripe":
                    # 竖条纹：每隔3像素交替颜色
                    if local_x % 6 < 2 and abs(x - cx) > ps:
                        use_accent = True
                # "solid" 不添加额外纹理
                
                if use_accent:
                    canvas[y][x] = (*accent, 255)
                else:
                    canvas[y][x] = (*fx_color, 255)
                # 中心装饰线（用accent高光色）
                if abs(x - cx) <= ps:
                    canvas[y][x] = (*accent_light, 255)
        
        # ---- 绘制腿（v0.3.1: 独立肢体偏移） ----
        leg_w = body_w // 3
        # 左腿（带偏移）
        ldx, ldy = pose["left_leg_dx"], pose["left_leg_dy"]
        for y in range(leg_top + ldy, min(H, leg_top + ldy + leg_h)):
            for x in range(max(0, cx - body_w//2 + ldx), min(W, cx - body_w//2 + ldx + leg_w)):
                if 0 <= y < H:
                    canvas[y][x] = (*body_color, 255)
        # 右腿（带偏移）
        rdx, rdy = pose["right_leg_dx"], pose["right_leg_dy"]
        for y in range(leg_top + rdy, min(H, leg_top + rdy + leg_h)):
            for x in range(max(0, cx + body_w//2 - leg_w + rdx), min(W, cx + body_w//2 + rdx)):
                if 0 <= y < H:
                    canvas[y][x] = (*body_color, 255)
        
        # ---- 鞋子（v0.3.2: 腿底部加深色鞋子区域） ----
        shoe_color = (max(0, body_color[0]-60), max(0, body_color[1]-60), max(0, body_color[2]-60))
        shoe_h = max(ps, leg_h // 3)
        # 左鞋
        for y in range(min(H-1, leg_top + ldy + leg_h - shoe_h), min(H, leg_top + ldy + leg_h)):
            for x in range(max(0, cx - body_w//2 + ldx - ps), min(W, cx - body_w//2 + ldx + leg_w + ps)):
                if 0 <= y < H and canvas[y][x][3] > 0:
                    canvas[y][x] = (*shoe_color, 255)
        # 右鞋
        for y in range(min(H-1, leg_top + rdy + leg_h - shoe_h), min(H, leg_top + rdy + leg_h)):
            for x in range(max(0, cx + body_w//2 - leg_w + rdx - ps), min(W, cx + body_w//2 + rdx + ps)):
                if 0 <= y < H and canvas[y][x][3] > 0:
                    canvas[y][x] = (*shoe_color, 255)
        
        # ---- 绘制手臂（v0.3.7: arm_ratio差异化手臂粗细） ----
        arm_w = max(ps * 2, int(leg_w * arm_ratio))
        # 左臂（带偏移）
        ladx, lady = pose["left_arm_dx"], pose["left_arm_dy"]
        for y in range(body_top + ps + lady, min(H, body_bot - ps + lady)):
            for x in range(max(0, cx - body_w//2 - arm_w + ladx), min(W, cx - body_w//2 + ladx)):
                if 0 <= y < H:
                    canvas[y][x] = (*skin, 255)
        # 右臂（带偏移，武器侧）
        radx, rady = pose["right_arm_dx"], pose["right_arm_dy"]
        for y in range(body_top + ps + rady, min(H, body_bot - ps + rady)):
            for x in range(cx + body_w//2 + radx, min(W, cx + body_w//2 + arm_w + radx)):
                if 0 <= y < H:
                    canvas[y][x] = (*skin, 255)
        
        # ---- 类型专属配件 ----
        # 战士：盾牌
        if type_cfg.get("has_shield"):
            shield_x = cx - body_w//2 - arm_w - ps*2
            shield_cy = (body_top + body_bot) // 2
            shield_r = max(ps*2, arm_w + ps)
            for y in range(max(0, shield_cy - shield_r), min(H, shield_cy + shield_r)):
                for x in range(max(0, shield_x - shield_r), min(W, shield_x + shield_r)):
                    sdx, sdy = x - shield_x, y - shield_cy
                    if sdx*sdx + sdy*sdy <= shield_r*shield_r:
                        canvas[y][x] = (*accent, 255)
                        # 盾牌十字纹饰
                        if abs(sdx) <= ps or abs(sdy) <= ps:
                            canvas[y][x] = (min(255, accent[0]+50), min(255, accent[1]+50), min(255, accent[2]+50), 255)

        # 法师：长袍下摆（逐渐加宽的袍角）
        if type_cfg.get("has_robe"):
            robe_bot = min(H, body_bot + ps*4)
            robe_w = body_w + ps*4
            for y in range(body_top + body_h//3, robe_bot):
                progress = (y - body_top - body_h//3) / max(1, robe_bot - body_top - body_h//3 - 1)
                extra = int(progress * ps * 2)
                for x in range(max(0, cx - robe_w//2 - extra), min(W, cx + robe_w//2 + extra)):
                    if canvas[y][x][3] == 0:
                        canvas[y][x] = (max(0, body_color[0]-15), max(0, body_color[1]-15), max(0, body_color[2]-15), 255)
            # 长袍中心装饰条纹
            for y in range(body_top + body_h//2, robe_bot):
                for x_off in range(-ps, ps+1):
                    px = cx + x_off
                    if 0 <= px < W and canvas[y][px][3] > 0:
                        canvas[y][px] = (*accent, 255)

        # 弓箭手：兜帽
        if type_cfg.get("has_hood"):
            for y in range(max(0, head_cy - head_r - ps*2), min(H, head_cy)):
                for x in range(max(0, cx - head_r - ps*2), min(W, cx + head_r + ps*2)):
                    hdx, hdy = x - cx, y - head_cy
                    outer_r = head_r + ps*2
                    if hdx*hdx + hdy*hdy <= outer_r*outer_r and hdy < 0:
                        if canvas[y][x][3] == 0:
                            canvas[y][x] = (max(0, body_color[0]-25), max(0, body_color[1]-25), max(0, body_color[2]-25), 255)

        # 盗贼：披风（带轻微飘动效果）
        if type_cfg.get("has_cape"):
            cape_x_start = cx + body_w//2 + ps
            cape_w = ps * 3
            for y in range(body_top + ps, min(H, body_bot + leg_h//2)):
                sway = int(math.sin((y - body_top) * 0.3) * ps)
                for x in range(max(0, cape_x_start + sway), min(W, cape_x_start + cape_w + sway)):
                    if canvas[y][x][3] == 0:
                        canvas[y][x] = (max(0, body_color[0]-35), max(0, body_color[1]-35), max(0, body_color[2]-35), 255)

        # 怪物：犄角
        if type_cfg.get("is_monster"):
            horn_h = max(ps*3, head_r//2 + ps)
            horn_w = max(ps, 2)
            for dy2 in range(horn_h):
                y = max(0, head_cy - head_r - dy2)
                # 左角
                lx = max(0, cx - head_r//2 - horn_w)
                for ddx in range(horn_w):
                    if 0 <= lx+ddx < W:
                        canvas[y][lx+ddx] = (min(255, accent[0]+40), min(255, accent[1]+40), min(255, accent[2]+40), 255)
                # 右角
                rx = min(W-horn_w, cx + head_r//2)
                for ddx in range(horn_w):
                    if 0 <= rx+ddx < W:
                        canvas[y][rx+ddx] = (min(255, accent[0]+40), min(255, accent[1]+40), min(255, accent[2]+40), 255)

        # 治疗师：光环
        if type_cfg.get("weapon") == "book":
            halo_y = max(0, head_cy - head_r - ps*2)
            halo_rx = head_r + ps*2
            for x in range(max(0, cx - halo_rx), min(W, cx + halo_rx)):
                hdx = x - cx
                if hdx*hdx <= halo_rx*halo_rx:
                    if halo_y < H:
                        canvas[halo_y][x] = (255, 230, 100, 180)
                    if halo_y+1 < H:
                        canvas[halo_y+1][x] = (255, 240, 150, 120)

        # ---- v0.3.9: 随机配件渲染 ----
        for acc in chosen_acc:
            if acc == "belt":
                # 腰带：身体中部的横向条纹（accent色+金属扣）
                belt_y = body_top + body_h * 2 // 3
                for x in range(max(0, cx - body_draw_w//2 - 1), min(W, cx + body_draw_w//2 + 1)):
                    for dy2 in range(max(0, ps)):
                        by = belt_y + dy2
                        if 0 <= by < H:
                            canvas[by][x] = (*accent_dark, 255)
                # 腰带金属扣（中心亮点）
                buckle_y = belt_y
                for dy2 in range(ps):
                    for dx2 in range(-ps, ps+1):
                        bx = cx + dx2
                        bby = buckle_y + dy2
                        if 0 <= bx < W and 0 <= bby < H:
                            canvas[bby][bx] = (*accent_light, 255)

            elif acc == "shoulder_pads":
                # 肩甲：肩膀两侧的方形护甲片
                pad_w = max(ps*2, arm_w)
                pad_h = max(ps*2, body_h // 5)
                pad_y = body_top
                # 左肩甲
                for y in range(pad_y, min(H, pad_y + pad_h)):
                    for x in range(max(0, cx - body_draw_w//2 - pad_w), min(W, cx - body_draw_w//2)):
                        canvas[y][x] = (*accent, 255)
                        # 肩甲内高光
                        if (x - (cx - body_draw_w//2 - pad_w)) < ps and (y - pad_y) < ps:
                            canvas[y][x] = (*accent_light, 255)
                # 右肩甲
                for y in range(pad_y, min(H, pad_y + pad_h)):
                    for x in range(max(0, cx + body_draw_w//2), min(W, cx + body_draw_w//2 + pad_w)):
                        canvas[y][x] = (*accent, 255)
                        # 肩甲内高光
                        if (cx + body_draw_w//2 + pad_w - x) < ps and (y - pad_y) < ps:
                            canvas[y][x] = (*accent_light, 255)

            elif acc == "scarf":
                # 围巾：脖子处的飘逸带状物，轻微随风飘动
                scarf_y_start = body_top - 1
                scarf_color = (min(255, accent[0]+20), min(255, accent[1]-10), min(255, accent[2]+10))
                # 围巾围绕脖子
                for x in range(max(0, cx - body_draw_w//2 - 1), min(W, cx + body_draw_w//2 + 1)):
                    if scarf_y_start >= 0 and scarf_y_start < H:
                        canvas[scarf_y_start][x] = (*scarf_color, 255)
                # 围巾飘尾（右侧向下延伸，带波浪）
                tail_len = min(H - scarf_y_start, body_h // 2 + ps*2)
                for dy2 in range(tail_len):
                    ty = scarf_y_start + dy2
                    wave = int(math.sin(dy2 * 0.5 + frame_idx * 0.3) * ps)
                    for dx2 in range(ps*2):
                        tx = cx + body_draw_w//2 + 1 + wave + dx2
                        if 0 <= ty < H and 0 <= tx < W:
                            canvas[ty][tx] = (*scarf_color, 255)

            elif acc == "earing":
                # 耳环：头部侧面的小亮点
                ear_x = cx + head_r + 1
                ear_y = head_cy
                if 0 <= ear_x < W and 0 <= ear_y < H:
                    canvas[ear_y][ear_x] = (255, 220, 100, 255)  # 金色耳环
                    if ear_y + 1 < H:
                        canvas[ear_y+1][ear_x] = (220, 180, 60, 255)  # 耳环下半

            elif acc == "belt_pouch":
                # 腰包：身体侧面的小方块包
                pouch_y = body_top + body_h * 2 // 3
                pouch_x = cx - body_draw_w//2 - ps*2
                pouch_w = max(ps*2, 3)
                pouch_h = max(ps*2, 4)
                for dy2 in range(pouch_h):
                    for dx2 in range(pouch_w):
                        px2 = pouch_x + dx2
                        py2 = pouch_y + dy2
                        if 0 <= px2 < W and 0 <= py2 < H:
                            canvas[py2][px2] = (*accent_dark, 255)
                # 包盖（浅色）
                if 0 <= pouch_y < H:
                    for dx2 in range(pouch_w):
                        px2 = pouch_x + dx2
                        if 0 <= px2 < W:
                            canvas[pouch_y][px2] = (*accent_light, 255)

            elif acc == "collar":
                # 衣领：脖子处的V形或环绕线条
                collar_y = body_top - 1
                collar_color = (*accent_light, 255)
                # V形衣领
                for dy2 in range(ps*2):
                    cy2 = collar_y + dy2
                    # 左侧V线
                    vx_l = cx - dy2
                    vx_r = cx + dy2
                    if 0 <= cy2 < H:
                        if 0 <= vx_l < W:
                            canvas[cy2][vx_l] = collar_color
                        if 0 <= vx_r < W:
                            canvas[cy2][vx_r] = collar_color
                # 顶部横线连接
                for x in range(max(0, cx - body_draw_w//2 - 1), min(W, cx + body_draw_w//2 + 1)):
                    if 0 <= collar_y < H:
                        canvas[collar_y][x] = collar_color

        # ---- 武器（v0.3.6: 跟随右臂偏移 + weapon_angle旋转） ----
        weapon = type_cfg.get("weapon", "none")
        radx, rady = pose["right_arm_dx"], pose["right_arm_dy"]
        weapon_angle = pose.get("weapon_angle", 0)
        weapon_base_x = cx + body_w//2 + arm_w + ps + radx
        weapon_base_y = body_top + ps*2 + rady
        weapon_len = body_h//2 + ps*3  # 武器长度
        
        if weapon in ("sword", "staff", "bow", "dagger"):
            # v0.3.6: 用Bresenham直线算法按weapon_angle画倾斜武器
            # weapon_angle: 0=垂直, 负=后拉, 正=前挥
            # 转换为像素偏移：每单位角度偏移 weapon_len*0.4 像素
            tip_dx = int(weapon_angle * weapon_len * 0.4)
            tip_dy = weapon_len
            tip_x = weapon_base_x + tip_dx
            tip_y = weapon_base_y + tip_dy
            
            # Bresenham画线（从base到tip）
            x0, y0 = weapon_base_x, weapon_base_y
            x1, y1 = tip_x, min(H-1, tip_y)
            dx_w = abs(x1 - x0)
            dy_w = abs(y1 - y0)
            sx = 1 if x0 < x1 else -1
            sy = 1 if y0 < y1 else -1
            err = dx_w - dy_w
            px_count = 0
            while True:
                # 在武器路径上画像素
                if 0 <= y0 < H and 0 <= x0 < W:
                    canvas[y0][x0] = (200, 200, 210, 255)
                    if weapon == "sword" and x0+1 < W:
                        canvas[y0][x0+1] = (220, 220, 230, 255)
                px_count += 1
                if px_count > weapon_len + 2:
                    break
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 > -dy_w:
                    err -= dy_w
                    x0 += sx
                if e2 < dx_w:
                    err += dx_w
                    y0 += sy
            
            # 武器尖端装饰（剑尖/杖头/弓弧）
            if 0 <= tip_y < H and 0 <= tip_x < W:
                if weapon == "sword":
                    canvas[tip_y][min(W-1, tip_x)] = (240, 240, 250, 255)
                elif weapon == "staff":
                    # 杖顶宝石
                    for gy in range(max(0, tip_y-ps*2), min(H, tip_y+1)):
                        for gx in range(max(0, tip_x-ps), min(W, tip_x+ps+1)):
                            if 0 <= gy < H and 0 <= gx < W:
                                canvas[gy][gx] = (*accent, 255)
                elif weapon == "dagger":
                    canvas[tip_y][min(W-1, tip_x)] = (180, 180, 190, 255)
        
        elif weapon == "book":
            for y in range(body_top + ps + rady, body_top + ps*5 + rady):
                if 0 <= y < H:
                    for x in range(weapon_base_x, min(W, weapon_base_x + ps*3)):
                        canvas[y][x] = (180, 160, 100, 255)
        
        # ---- 描边（v0.3.4: 非破坏性8方向描边，保留角色细节） ----
        if outline:
            outline_layer = [[False]*W for _ in range(H)]
            for y in range(H):
                for x in range(W):
                    if canvas[y][x][3] == 0:  # 空白像素
                        # 检查8方向是否有角色像素，若有则在空白处画描边
                        for dx2, dy2 in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
                            nx, ny = x+dx2, y+dy2
                            if 0 <= nx < W and 0 <= ny < H and canvas[ny][nx][3] > 0:
                                outline_layer[y][x] = True
                                break
            for y in range(H):
                for x in range(W):
                    if outline_layer[y][x]:
                        canvas[y][x] = (*outline, 255)
        
        # ---- 像素化处理 ----
        if ps > 1:
            new_canvas = [[(0,0,0,0)]*W for _ in range(H)]
            for by in range(0, H, ps):
                for bx in range(0, W, ps):
                    # 取块中心色
                    cx2 = min(bx + ps//2, W-1)
                    cy2 = min(by + ps//2, H-1)
                    color = canvas[cy2][cx2]
                    for dy2 in range(ps):
                        for dx2 in range(ps):
                            px, py = bx+dx2, by+dy2
                            if 0 <= px < W and 0 <= py < H:
                                new_canvas[py][px] = color
            canvas = new_canvas
        
        # ---- 明暗层次（v0.3.4: 双轴光照+深度阴影增强立体感） ----
        # 光源设定：左上方主光源 + 顶部环境光
        for y in range(H):
            for x in range(W):
                r, g, b, a = canvas[y][x]
                if a == 0:
                    continue
                
                # 水平偏移：左亮右暗（主光源方向）
                h_bias = (x - cx) / max(1, W // 2)  # -1 到 1
                
                # 垂直偏移：上亮下暗（顶光环境照明）
                v_bias = (y - H * 0.3) / max(1, H * 0.7)  # 上部为负，下部为正
                
                lift = 0
                shadow = 0
                
                # 水平光照（主光源从左上方照射）
                if h_bias < -0.15:
                    lift += int(abs(h_bias) * 10)
                elif h_bias > 0.15:
                    shadow += int(h_bias * 14)
                
                # 垂直深度（顶部受光更强，底部更暗，模拟顶光）
                if v_bias < -0.2:
                    lift += int(abs(v_bias) * 6)
                elif v_bias > 0.25:
                    shadow += int(v_bias * 8)
                
                if lift > 0 or shadow > 0:
                    r2 = min(255, max(0, r + lift - shadow))
                    g2 = min(255, max(0, g + lift - shadow))
                    b2 = min(255, max(0, b + lift - shadow))
                    canvas[y][x] = (r2, g2, b2, a)
        
        # ---- v0.3.13: 边缘环境光遮蔽（Edge AO）— 增强轮廓立体感 ----
        # 在角色不透明区域的边缘内侧2像素范围内，添加渐变暗化效果
        # 模拟真实环境光遮蔽：边缘处环境光更少，显得更暗
        ao_pass = [[False]*W for _ in range(H)]
        for y in range(H):
            for x in range(W):
                if canvas[y][x][3] > 0:
                    # 检查4方向（上下左右）是否接触透明区域
                    for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nx2, ny2 = x+ddx, y+ddy
                        if nx2 < 0 or nx2 >= W or ny2 < 0 or ny2 >= H or canvas[ny2][nx2][3] == 0:
                            ao_pass[y][x] = True
                            break
        # 对边缘像素做AO暗化（-15亮度），向内1像素做轻微AO（-7亮度）
        for y in range(H):
            for x in range(W):
                if ao_pass[y][x]:
                    r, g, b, a = canvas[y][x]
                    canvas[y][x] = (max(0, r-15), max(0, g-15), max(0, b-15), a)
                    # 向内1像素也做轻微暗化
                    for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                        ix, iy = x+ddx, y+ddy
                        if 0 <= ix < W and 0 <= iy < H and not ao_pass[iy][ix] and canvas[iy][ix][3] > 0:
                            r3, g3, b3, a3 = canvas[iy][ix]
                            canvas[iy][ix] = (max(0, r3-7), max(0, g3-7), max(0, b3-7), a3)
        
        # ---- v0.3.13: 地面阴影投射 — 椭圆形渐变阴影增强空间感 ----
        # 在角色脚底位置绘制一个椭圆形半透明阴影，模拟地面投影
        # 阴影宽度约等于身体宽度+margin，高度很扁（透视压缩）
        # 受 body_dy 影响：角色上升时阴影缩小变淡，下降时扩大变深
        shadow_y_base = leg_top + leg_h + body_dy  # 阴影Y基准位置
        shadow_rx = int(body_draw_w * 1.3)  # 阴影水平半径（比身体宽一些）
        shadow_ry = max(2, int(leg_h * 0.15))  # 阴影垂直半径（很扁）
        # 阴影透明度随身体偏移动态变化（跳起时阴影更淡）
        shadow_alpha_base = 70
        if body_dy < -2:
            shadow_alpha_base = max(20, shadow_alpha_base + body_dy * 5)  # 上升→阴影淡
        
        for y in range(max(0, shadow_y_base - shadow_ry), min(H, shadow_y_base + shadow_ry + 1)):
            for x in range(max(0, cx - shadow_rx), min(W, cx + shadow_rx)):
                dx_s = (x - cx) / max(1, shadow_rx)
                dy_s = (y - shadow_y_base) / max(1, shadow_ry)
                dist_sq = dx_s * dx_s + dy_s * dy_s
                if dist_sq <= 1.0:
                    # 椭圆内部：中心深、边缘淡（高斯衰减）
                    falloff = 1.0 - dist_sq
                    sa = int(shadow_alpha_base * falloff * falloff)
                    if sa > 3 and canvas[y][x][3] == 0:
                        # 仅在空白区域绘制阴影（不覆盖角色像素）
                        canvas[y][x] = (0, 0, 0, sa)
        
        return canvas

    def _apply_flash(self, frame, intensity):
        """对帧应用白闪效果（受击闪烁）"""
        W, H = self.CANVAS_W, self.CANVAS_H
        result = [list(row) for row in frame]
        for y in range(H):
            for x in range(W):
                r, g, b, a = result[y][x]
                if a > 0:
                    result[y][x] = (min(255, r+intensity), min(255, g+intensity), min(255, b+intensity), a)
        return result
    
    def _apply_alpha(self, frame, alpha):
        """对帧应用全局透明度（死亡渐隐）"""
        W, H = self.CANVAS_W, self.CANVAS_H
        result = [list(row) for row in frame]
        for y in range(H):
            for x in range(W):
                r, g, b, a = result[y][x]
                if a > 0:
                    result[y][x] = (r, g, b, alpha)
        return result

    def _generate_skeleton(self, type_cfg, palette):
        """生成骨骼定义（Spine兼容格式）"""
        W, H = self.CANVAS_W, self.CANVAS_H
        cx = W // 2
        
        head_r = int(H * type_cfg.get("head_ratio", 0.19) / 2)
        body_h = int(H * 0.35)
        
        head_y = H // 2 - body_h // 2 - head_r + 2
        body_top = head_y + head_r + 1
        body_bot = body_top + body_h
        neck_y = body_top
        
        return {
            "bones": [
                {"name": "root", "x": cx, "y": H, "parent": None},
                {"name": "hip", "x": 0, "y": -(H - body_bot), "parent": "root"},
                {"name": "spine", "x": 0, "y": -body_h // 2, "parent": "hip"},
                {"name": "neck", "x": 0, "y": -body_h // 2, "parent": "spine"},
                {"name": "head", "x": 0, "y": -head_r, "parent": "neck"},
                {"name": "left_upper_arm", "x": -8, "y": 0, "parent": "neck"},
                {"name": "left_lower_arm", "x": 0, "y": -10, "parent": "left_upper_arm"},
                {"name": "right_upper_arm", "x": 8, "y": 0, "parent": "neck"},
                {"name": "right_lower_arm", "x": 0, "y": -10, "parent": "right_upper_arm"},
                {"name": "left_upper_leg", "x": -5, "y": 0, "parent": "hip"},
                {"name": "left_lower_leg", "x": 0, "y": -12, "parent": "left_upper_leg"},
                {"name": "right_upper_leg", "x": 5, "y": 0, "parent": "hip"},
                {"name": "right_lower_leg", "x": 0, "y": -12, "parent": "right_upper_leg"},
            ],
            "slots": [
                {"name": "body", "bone": "spine", "attachment": "body"},
                {"name": "head", "bone": "head", "attachment": "head"},
                {"name": "left_arm", "bone": "left_lower_arm", "attachment": "arm_l"},
                {"name": "right_arm", "bone": "right_lower_arm", "attachment": "arm_r"},
                {"name": "left_leg", "bone": "left_lower_leg", "attachment": "leg_l"},
                {"name": "right_leg", "bone": "right_lower_leg", "attachment": "leg_r"},
            ],
            "ik": [],
        }

    @staticmethod
    def _to_base64(data):
        import base64
        return base64.b64encode(data).decode("ascii")
