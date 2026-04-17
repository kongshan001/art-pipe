"""
ArtPipe 角色生成引擎 v0.3
支持三种渲染模式: procedural(程序化) / ai(AI生成) / hybrid(混合)
纯Python实现，零外部依赖
v0.3.30: HSV色温偏移(高光/阴影色彩分层升级为真正的HSV色相旋转)+修复垂直抖动矩阵为2D索引
v0.3.26: 关节缝隙阴影(Joint Crease AO,颈部/腰部/肩部衔接处渐变暗化增强部件分离感)
v0.3.24: 手部渲染(手臂末端添加椭圆形手掌细节，增加角色完成度)
v0.3.23: 调色板色彩快照(Palette Snap,后处理色彩量化到调色板色阶消除连续色调噪点)+头部镜面高光(Specular Highlight,圆形衰减高光点增强面部立体感)
v0.3.21: 头部球面法线渐变着色(模拟球体光照:左上亮右下暗)+AI重试seed轮换(fix:重试时更换seed确保不同结果)
v0.3.20: 腿部纵向渐变着色(body_light/body_color/body_dark三区)+眉毛情感系统(动画状态联动:攻击V形怒眉/惊讶上扬/死亡下垂/施法微蹙)
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
    # v0.3.17: 新增骑士 — 重甲坦克型角色
    "knight": {
        "name": "骑士", "head_ratio": 0.17, "body_w": 0.38,
        "has_helmet": True, "weapon": "sword",
        "face_type": "serious",
        "body_ratio": 1.25,  # 最宽壮躯干
        "leg_ratio": 0.85,   # 短粗稳固腿
        "arm_ratio": 1.15,   # 强壮手臂
        "accessories": ["belt", "shoulder_pads", "collar", "belt_pouch"],
    },
    # v0.3.17: 新增吟游诗人 — 轻巧辅助型角色
    "bard": {
        "name": "吟游诗人", "head_ratio": 0.20, "body_w": 0.24,
        "has_hat": True, "weapon": "lute",
        "face_type": "gentle",
        "body_ratio": 0.88,  # 纤细身材
        "leg_ratio": 1.05,   # 灵活腿
        "arm_ratio": 1.00,   # 匀称手臂
        "accessories": ["scarf", "earing", "collar", "belt"],
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
    # v0.3.17
    "knight": ["short", "bald", "medium"],        # 骑士：短发为主（被头盔遮挡）
    "bard": ["long", "ponytail", "medium", "side_part"],  # 吟游诗人：飘逸发型
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

        # 检测类型 — 评分制：统计每个类型命中的关键词数，选最高分
        # v0.3.19: 修复 warrior/knight 关键词冲突，改用评分机制替代首次匹配
        char_type = "warrior"
        type_keywords = {
            "mage": ["法师", "魔法师", "巫师", "mage", "wizard", "魔法", "少女", "术士", "sorcerer"],
            "monster": ["怪物", "史莱姆", "monster", "slime", "恶魔", "boss", "demon"],
            "archer": ["弓箭手", "猎人", "archer", "hunter", "弓"],
            "rogue": ["盗贼", "刺客", "rogue", "assassin", "thief", "匕首", "忍者", "ninja"],
            "healer": ["治疗", "牧师", "healer", "priest", "cleric", "修女", "僧侣"],
            "knight": ["骑士", "圣骑士", "knight", "paladin", "坦克", "tank", "圣骑"],  # v0.3.17→19
            "bard": ["诗人", "吟游诗人", "bard", "minstrel", "音乐家", "乐师"],  # v0.3.17
            "npc": ["村民", "商人", "npc", "villager", "店员", "老爷爷", "老奶奶"],
            "warrior": ["战士", "武士", "warrior", "剑", "勇者", "剑士", "sword"],
        }
        # 评分：计算每个类型命中数，选得分最高的
        best_type = "warrior"
        best_score = 0
        for t, kws in type_keywords.items():
            score = sum(1 for kw in kws if kw in prompt_lower)
            if score > best_score:
                best_score = score
                best_type = t
        if best_score > 0:
            char_type = best_type

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
            "cast": 8,    # 施法：中速蓄力+快速释放（v0.3.16）
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
        # v0.3.17: padding=1 帧间1px透明间距，防止游戏引擎纹理渗透
        spritesheet_png = create_spritesheet(all_frames, cols, self.CANVAS_W, self.CANVAS_H,
                                             frame_map=frame_map, padding=1)
        
        result["spritesheet"] = {
            "png_base64": self._to_base64(spritesheet_png),
            "total_frames": len(all_frames),
            "cols": cols,
            "rows": (len(all_frames) + cols - 1) // cols,
            "frame_width": self.CANVAS_W,
            "frame_height": self.CANVAS_H,
            "padding": 1,
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
        """v0.3.18: 基于感知色彩理论的增强色相和谐算法
        v0.3.5: HSV色相和谐 — 类似色/三角色/分裂互补/四方色
        v0.3.18: 新增感知色彩质量修正：
          - 感知亮度感知饱和度上限（防止霓虹色，Rec.709加权）
          - 最小感知色距保障（调色板内颜色在精灵表小尺寸下可区分）
          - 黄金角度色相展开（色彩过近时自动偏移）
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

        # v0.3.18: 感知亮度计算 (Rec.709标准加权)
        # 人眼对绿色最敏感(71.5%)，红色次之(21.3%)，蓝色最弱(7.2%)
        def perceived_luminance(r, g, b):
            return 0.2126 * (r / 255.0) + 0.7152 * (g / 255.0) + 0.0722 * (b / 255.0)

        # v0.3.18: 感知色距（加权欧氏距离近似delta-E）
        # 绿色通道权重×4（人眼最敏感），红色×2，蓝色×3（像素美术中蓝色区分度重要）
        def color_dist_sq(c1, c2):
            dr, dg, db = c1[0] - c2[0], c1[1] - c2[1], c1[2] - c2[2]
            return 2 * dr * dr + 4 * dg * dg + 3 * db * db

        # 提取主色HSV
        primary = palette[0]
        p_h, p_s, p_v = rgb_to_hsv(*primary)

        result = [primary]  # 主色保持不变

        # 用RNG选择和谐模式（避免所有角色用同一模式）
        # v0.3.17: 新增四方色(tetradic)和谐模式 — 4色色环互补，丰富视觉表现力
        harmony_modes = ["analogous", "triadic", "split_comp", "tetradic"]
        # 类似色40%，三角色25%，分裂互补20%，四方色15%
        roll = rng.next()
        if roll < 0.4:
            mode = "analogous"
        elif roll < 0.65:
            mode = "triadic"
        elif roll < 0.85:
            mode = "split_comp"
        else:
            mode = "tetradic"

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
            elif mode == "tetradic":
                # v0.3.17: 四方色(tetradic/矩形互补) — 两组互补色，色环上呈矩形分布
                # 在90°和180°之间交替选择，产生丰富但平衡的4色配色方案
                # 概率：50%偏移+90°，50%偏移-90°（第二对互补色）
                angle = 90 if (i % 2 == 1) else 180
                sign = 1 if rng.next() > 0.5 else -1
                hue_offset = sign * angle + (rng.next() - 0.5) * 15  # ±7.5°抖动
                new_h = p_h + hue_offset
                # 四方色需要降低饱和度以避免4色同时高饱和的混乱感
                new_s = min(s, p_s) * 0.75
                new_v = v * 0.85 + p_v * 0.15
            else:
                # 分裂互补：偏移 ±150°
                sign = 1 if rng.next() > 0.5 else -1
                hue_offset = sign * 150 + (rng.next() - 0.5) * 20
                new_h = p_h + hue_offset
                new_s = s * 0.6 + p_s * 0.4
                new_v = v * 0.75 + p_v * 0.25

            result.append(hsv_to_rgb(new_h, new_s, new_v))

        # v0.3.18: 感知色彩质量后处理
        # 1) 感知饱和度上限：高亮度+高饱和=霓虹色(不协调)，需渐进衰减
        #    钟形曲线：中间色调(L≈0.5)饱和度上限最高(1.0)，
        #    极端亮/暗(L≈0或1)时上限降低到0.55，避免刺眼
        # 2) 最小感知色距：确保调色板内颜色在精灵表小尺寸(64x64)下仍可区分
        #    阈值1500 ≈ 约39 RGB距离（绿色通道加权后）
        # 3) 黄金角度偏移：色彩过近时用137.5°旋转，保证最大色相展开
        fixed = [result[0]]
        for i in range(1, len(result)):
            r, g, b = result[i]
            h, s, v = rgb_to_hsv(r, g, b)
            L = perceived_luminance(r, g, b)
            # 感知饱和度上限
            sat_cap = 0.55 + 0.45 * (1 - abs(2 * L - 1))
            if s > sat_cap:
                s = sat_cap + (s - sat_cap) * 0.25  # 渐进衰减，保留25%超量
            new_color = hsv_to_rgb(h, s, v)
            # 最小感知色距检查（与已有所有颜色比较）
            min_dist = float('inf')
            for prev in fixed:
                d = color_dist_sq(new_color, prev)
                if d < min_dist:
                    min_dist = d
            if min_dist < 1500:
                # 色距不足，用黄金角度(≈137.508°)偏移色相
                # 黄金角度保证连续旋转不会回到近邻位置（最大 irrational coverage）
                h = (h + 137.508) % 360
                new_color = hsv_to_rgb(h, s, v)
            fixed.append(new_color)

        return fixed

    def _render_all_frames(self, rng, style_cfg, type_cfg, palette, char_type_key="warrior"):
        """渲染8种动画的帧（v0.3.11: 传入char_type_key用于发型选择）"""
        animations = {}
        
        # v0.3.11: 在所有帧之前一次性选择发型和纹理（保证帧间一致性）
        hair_pool = HAIR_STYLES.get(char_type_key, ["short", "medium"])
        hair_style = hair_pool[rng.int_range(0, len(hair_pool) - 1)]
        texture_patterns = ["solid", "horizontal_stripe", "checkerboard", "diamond", "v_stripe"]
        cloth_texture = texture_patterns[rng.int_range(0, len(texture_patterns) - 1)]
        
        # v0.3.13: 在所有帧之前一次性选择配件（修复帧间配件闪烁bug）
        available_acc = type_cfg.get("accessories", [])
        chosen_acc = []
        if available_acc:
            acc_pool = list(available_acc)
            for i in range(len(acc_pool) - 1, 0, -1):
                j = rng.int_range(0, i)
                acc_pool[i], acc_pool[j] = acc_pool[j], acc_pool[i]
            roll = rng.next()
            if roll < 0.70:
                n_acc = 1
            elif roll < 0.90:
                n_acc = 2
            else:
                n_acc = 0
            chosen_acc = acc_pool[:n_acc]
        
        anim_configs = {
            "idle":   {"frames": 4},
            "walk":   {"frames": 6},
            "run":    {"frames": 6},
            "jump":   {"frames": 6},  # v0.3.2: 跳跃动画
            "attack": {"frames": 6},
            "defend": {"frames": 5},  # v0.3.8: 防御动画
            "hurt":   {"frames": 3},
            "die":    {"frames": 6},
            "cast":   {"frames": 7},  # v0.3.16: 施法动画（蓄力→释放→恢复）
        }
        
        for anim_name, cfg in anim_configs.items():
            frames = []
            for f in range(cfg["frames"]):
                t = f / max(cfg["frames"] - 1, 1)
                # 计算当前帧的肢体姿态参数
                pose = self._calc_pose(anim_name, t)
                # 每帧独立渲染（含肢体偏移）
                frame = self._render_character(rng, style_cfg, type_cfg, palette, f, anim_name, pose, char_type_key, hair_style, cloth_texture, chosen_acc)
                # 后处理：特殊效果
                if anim_name == "hurt" and int(t * 4) % 2 == 0:
                    # 受击白闪效果
                    frame = self._apply_flash(frame, 80)
                elif anim_name == "die":
                    # 死亡渐隐
                    alpha = max(0, int(255 * (1 - t)))
                    frame = self._apply_alpha(frame, alpha)
                elif anim_name == "cast":
                    # v0.3.16: 施法蓄力闪光效果
                    # t=0~0.43 蓄力渐强，t=0.43~0.57 释放高峰，t=0.57~1.0 消散
                    if t < 0.43:
                        flash_intensity = int(t / 0.43 * 50)
                    elif t < 0.57:
                        flash_intensity = 50  # 释放高峰
                    else:
                        flash_intensity = int(50 * (1 - (t - 0.57) / 0.43))
                    if flash_intensity > 0:
                        frame = self._apply_flash(frame, flash_intensity)
                frames.append(frame)
            animations[anim_name] = frames
        
        return animations
    
    # v0.3.22: 缓动函数 — 替代线性插值，让动画运动更自然
    # 参考 Robert Penner 经典缓动公式，适配像素级整数动画
    @staticmethod
    def _ease_in(t):
        """加速缓入 — 从静止逐渐加速（用于蓄力、蹲下）"""
        return t * t

    @staticmethod
    def _ease_out(t):
        """减速缓出 — 从快速逐渐减速（用于着地、攻击后坐）"""
        return t * (2 - t)

    @staticmethod
    def _ease_in_out(t):
        """先慢后快再慢 — 自然钟摆运动（用于呼吸、摇摆）"""
        if t < 0.5:
            return 2 * t * t
        return -1 + (4 - 2 * t) * t

    @staticmethod
    def _ease_in_cubic(t):
        """三次加速 — 比二次更急促的加速（用于重击蓄力）"""
        return t * t * t

    @staticmethod
    def _ease_out_cubic(t):
        """三次减速 — 比二次更急剧的减速（用于着地冲击）"""
        t1 = t - 1
        return t1 * t1 * t1 + 1

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
        v0.3.22: 引入缓动函数替代线性插值，动画运动更自然流畅
        """
        pose = {
            "left_leg_dx": 0, "left_leg_dy": 0,
            "right_leg_dx": 0, "right_leg_dy": 0,
            "left_arm_dx": 0, "left_arm_dy": 0,
            "right_arm_dx": 0, "right_arm_dy": 0,
            "body_dy": 0, "head_dy": 0,
            "weapon_angle": 0,
            "body_scale_x": 1.0,  # v0.3.8: 胸腔横向缩放（呼吸）
            "body_scale_y": 1.0,  # v0.3.25: 纵向缩放（squash & stretch）
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
            # v0.3.27: 次级运动 — 躯干前倾微摆+头部延迟跟随
            phase = t * math.pi * 2
            pose["left_leg_dx"] = int(math.sin(phase) * 2)
            pose["left_leg_dy"] = -int(abs(math.sin(phase)) * 2)
            pose["right_leg_dx"] = int(math.sin(phase + math.pi) * 2)
            pose["right_leg_dy"] = -int(abs(math.sin(phase + math.pi)) * 2)
            pose["body_dy"] = -int(abs(math.sin(phase * 2)) * 1)
            # v0.3.27: 躯干横向微倾（与迈步同相，相位偏移π/4产生延迟感）
            # 行走时重心随迈步自然左右微移，幅度1.5px（int截断后实际±1px）
            pose["body_dx"] = int(math.sin(phase + math.pi / 4) * 1.5)
            # v0.3.27: 头部延迟跟随 — 比body_dy额外延迟0.2弧度，幅度1.5px
            # 模拟真实行走中头部因惯性滞后于躯干的现象
            pose["head_dy"] = -int(abs(math.sin(phase * 2 + 0.2)) * 1.5)
            # 手臂自然摆动（与腿反向）
            pose["left_arm_dx"] = int(math.sin(phase + math.pi) * 1)
            pose["right_arm_dx"] = int(math.sin(phase) * 1)
            
        elif anim == "run":
            # 更大幅度的腿交替 + 身体前倾
            # v0.3.27: 次级运动 — 跑步躯干前倾+更大横向摆动+头部延迟
            phase = t * math.pi * 2
            pose["left_leg_dx"] = int(math.sin(phase) * 3)
            pose["left_leg_dy"] = -int(abs(math.sin(phase)) * 3)
            pose["right_leg_dx"] = int(math.sin(phase + math.pi) * 3)
            pose["right_leg_dy"] = -int(abs(math.sin(phase + math.pi)) * 3)
            pose["body_dy"] = -int(abs(math.sin(phase * 2)) * 2)
            # v0.3.27: 跑步躯干横向摆动（幅度2px，比walk更大）
            # 重心左右转移更明显，相位偏移π/3增加动态感
            pose["body_dx"] = int(math.sin(phase + math.pi / 3) * 2)
            # v0.3.27: 头部延迟跟随 — 延迟0.3弧度，幅度2.5px（int后实际±1px）
            # 跑步时头部惯性更大，滞后更明显
            pose["head_dy"] = -int(abs(math.sin(phase * 2 + 0.3)) * 2.5)
            pose["left_arm_dx"] = int(math.sin(phase + math.pi) * 2)
            pose["right_arm_dx"] = int(math.sin(phase) * 2)
            pose["left_arm_dy"] = -int(abs(math.sin(phase + math.pi)) * 1)
            pose["right_arm_dy"] = -int(abs(math.sin(phase)) * 1)
            
        elif anim == "jump":
            # v0.3.2: 跳跃动画 - 蹲→起跳→滞空→落地
            # v0.3.22: 缓动曲线让跳跃更自然 — 蹲用ease-in-out，起跳用ease-out快速弹出
            # t: 0~0.15蹲, 0.15~0.35起跳上升, 0.35~0.65滞空, 0.65~1.0下落落地
            if t < 0.15:
                # 蹲下蓄力（ease-in-out平滑下蹲）
                raw = t / 0.15  # 0→1
                squat = self._ease_in_out(raw)
                pose["body_dy"] = int(squat * 3)
                pose["head_dy"] = int(squat * 2)
                pose["left_leg_dx"] = -1
                pose["right_leg_dx"] = 1
                pose["left_leg_dy"] = int(squat * 1)
                pose["right_leg_dy"] = int(squat * 1)
                # v0.3.25: 蹲下蓄力squash（横向膨胀+纵向压缩，蓄力感）
                pose["body_scale_x"] = 1.0 + 0.10 * squat
                pose["body_scale_y"] = 1.0 - 0.08 * squat
            elif t < 0.35:
                # 起跳上升（ease-out快速弹出身体）
                raw = (t - 0.15) / 0.2  # 0→1
                lift = self._ease_out_cubic(raw)
                pose["body_dy"] = -int(lift * 8)
                pose["head_dy"] = -int(lift * 8)
                pose["left_arm_dy"] = -int(lift * 3)
                pose["right_arm_dy"] = -int(lift * 3)
                pose["left_leg_dy"] = -int(lift * 2)
                pose["right_leg_dy"] = -int(lift * 2)
                # v0.3.25: 起跳stretch（纵向拉长+横向收窄，表现爆发力）
                if raw < 0.5:
                    stretch_strength = raw * 2  # 0→1 渐强
                    pose["body_scale_x"] = 1.0 - 0.08 * stretch_strength
                    pose["body_scale_y"] = 1.0 + 0.10 * stretch_strength
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
                # 下落并落地（ease-in加速下坠 + 着地缓冲）
                raw = (t - 0.65) / 0.35  # 0→1
                fall = self._ease_in(raw)
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
                    # v0.3.25: 着地squash（横向膨胀+纵向压缩，体积守恒）
                    # 经典动画原理：冲击瞬间squash，然后快速恢复
                    # squash强度随缓冲衰减：刚着地最强，逐渐恢复
                    squash_decay = 1.0 - cushion * 0.7  # 1.0→0.3
                    pose["body_scale_x"] = 1.0 + 0.12 * squash_decay
                    pose["body_scale_y"] = 1.0 - 0.10 * squash_decay
                elif fall > 0.5:
                    # v0.3.25: 下落中段stretch（纵向拉长+横向收窄，表现速度感）
                    stretch_t = (fall - 0.5) / 0.2  # 0→1
                    pose["body_scale_x"] = 1.0 - 0.06 * stretch_t
                    pose["body_scale_y"] = 1.0 + 0.08 * stretch_t
        
        elif anim == "attack":
            # 攻击：右臂（武器侧）前伸 → 收回（v0.3.6: 身体前冲+头部后仰分离）
            # v0.3.22: 蓄力用ease-in（缓慢蓄势），挥出用ease-out（快速爆发后减速）
            # t: 0=蓄力, 0.4=挥出, 1.0=收回
            if t < 0.4:
                # 蓄力阶段：武器后拉，身体微微后坐（ease-in缓慢蓄势）
                raw = t / 0.4  # 0→1
                swing = self._ease_in(raw)
                pose["right_arm_dx"] = -int(swing * 3)
                pose["right_arm_dy"] = -int(swing * 2)
                pose["weapon_angle"] = -swing * 0.5
                pose["body_dy"] = int(swing * 1)  # 后坐
                pose["head_dy"] = int(swing * 1)  # 头随身体
            else:
                # 挥出阶段：快速前刺，身体前冲但头部保持（ease-out快速爆发）
                raw = (t - 0.4) / 0.6  # 0→1
                swing = self._ease_out(raw)
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
            # 受击：整体后仰（v0.3.22: ease-out缓出 — 快速冲击后减速）
            et = self._ease_out(t)
            pose["body_dy"] = int(et * 2)
            pose["head_dy"] = int(et * 3)
            pose["left_arm_dx"] = int(et * 2)
            pose["right_arm_dx"] = int(et * 2)
            
        elif anim == "defend":
            # v0.3.8: 防御动画 — 重心下沉+手臂护身+微颤抖
            # v0.3.22: ease-out快速进入防御姿态
            if t < 0.25:
                # 准备阶段：重心下移，手臂举起（ease-out快速架起防御）
                raw = t / 0.25  # 0→1
                prep = self._ease_out(raw)
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
            # 死亡：身体下沉（v0.3.22: ease-in加速 — 逐渐加速倒下，最后瘫软）
            et = self._ease_in(t)
            pose["body_dy"] = int(et * 8)
            pose["head_dy"] = int(et * 10)
            pose["left_arm_dx"] = int(et * 2)
            pose["right_arm_dx"] = int(et * 2)
            pose["left_leg_dx"] = int(et * 1)
            pose["right_leg_dx"] = int(et * -1)
        
        elif anim == "cast":
            # v0.3.16: 施法动画 — 7帧蓄力→释放→恢复
            # 参考 RPG 标准：蓄力慢(anticipation) → 释放快(release) → 恢复中速(recovery)
            # v0.3.22: 缓动曲线 — 蓄力ease-in缓慢凝聚，释放ease-out快速爆发
            # t=0~0.29 蓄力（手臂举起，身体后仰）
            # t=0.29~0.43 高位蓄力（能量凝聚）
            # t=0.43~0.57 释放（前推施法，能量爆发）
            # t=0.57~1.0 恢复（收回idle姿态）
            if t < 0.29:
                # 蓄力阶段：手臂逐渐举高（ease-in缓慢凝聚能量）
                raw = t / 0.29  # 0→1
                prep = self._ease_in(raw)
                pose["right_arm_dy"] = -int(prep * 5)  # 右臂举高
                pose["right_arm_dx"] = -int(prep * 1)  # 略向左（双手聚能感）
                pose["left_arm_dy"] = -int(prep * 4)   # 左臂同步举高
                pose["left_arm_dx"] = int(prep * 1)    # 略向右
                pose["body_dy"] = int(prep * 2)         # 微微下蹲蓄力
                pose["head_dy"] = -int(prep * 1)        # 头微抬
                pose["weapon_angle"] = -prep * 0.3      # 武器微微后倾
            elif t < 0.43:
                # 高位蓄力：手臂高举过头，身体后仰到极限
                hold = (t - 0.29) / 0.14  # 0→1
                base = 1.0  # 从蓄力完成状态开始
                tremor = round(math.sin(hold * math.pi * 6) * 0.8)  # 能量凝聚颤抖
                pose["right_arm_dy"] = -int((base + hold * 0.2) * 5) + tremor
                pose["right_arm_dx"] = -1
                pose["left_arm_dy"] = -int((base + hold * 0.2) * 4) + tremor
                pose["left_arm_dx"] = 1
                pose["body_dy"] = 2 - int(hold * 1)  # 略微下沉蓄势
                pose["head_dy"] = -1 - int(hold * 1)  # 头更仰
                pose["weapon_angle"] = -0.3 - hold * 0.2
            elif t < 0.57:
                # 释放阶段：手臂前推，身体前冲（ease-out快速释放能量）
                raw = (t - 0.43) / 0.14  # 0→1
                release = self._ease_out_cubic(raw)
                # 从高举快速切换到前推
                pose["right_arm_dy"] = -int(5 * (1 - release))  # 右臂下压
                pose["right_arm_dx"] = int(release * 4)          # 右臂前推
                pose["left_arm_dy"] = -int(4 * (1 - release))
                pose["left_arm_dx"] = -int(release * 2)          # 左臂辅助
                pose["body_dy"] = -int(release * 2)              # 身体前冲
                pose["head_dy"] = int(release * 1)               # 头随身体前倾
                pose["weapon_angle"] = release * 0.8             # 武器前挥
                # 前冲时双腿后蹬
                pose["left_leg_dx"] = -int(release * 2)
                pose["right_leg_dx"] = int(release * 1)
            else:
                # 恢复阶段：逐渐回到idle姿态（ease-out缓出）
                raw = (t - 0.57) / 0.43  # 0→1
                ease = self._ease_out(raw)
                pose["right_arm_dy"] = -int(2 * (1 - ease))
                pose["right_arm_dx"] = int(2 * (1 - ease))
                pose["left_arm_dy"] = -int(1 * (1 - ease))
                pose["body_dy"] = -int(1 * (1 - ease))
                pose["weapon_angle"] = 0.4 * (1 - ease)
        
        return pose

    def _render_character(self, rng, style_cfg, type_cfg, palette, frame_idx, anim, pose=None, char_type_key="warrior", hair_style="short", cloth_texture="solid", chosen_acc=None):
        """渲染单帧角色像素数据（v0.3.13: 配件由外层传入，保证帧间一致性）"""
        W, H = self.CANVAS_W, self.CANVAS_H
        ps = style_cfg["pixel_size"]
        
        # 无 pose 时使用默认（无偏移）
        if pose is None:
            pose = {
                "left_leg_dx": 0, "left_leg_dy": 0,
                "right_leg_dx": 0, "right_leg_dy": 0,
                "left_arm_dx": 0, "left_arm_dy": 0,
                "right_arm_dx": 0, "right_arm_dy": 0,
                "body_dx": 0, "body_dy": 0, "head_dy": 0,
                "weapon_angle": 0,
                "body_scale_x": 1.0,
                "body_scale_y": 1.0,
            }
        
        # v0.3.13: 配件由 _render_all_frames 在帧循环前一次性选定并传入
        # 不再在每帧中重新随机选择，避免帧间配件闪烁
        if chosen_acc is None:
            chosen_acc = []
        
        # 创建空白画布 (RGBA)
        canvas = [[(0,0,0,0) for _ in range(W)] for _ in range(H)]
        
        cx, cy = W // 2, H // 2
        skin = palette[0] if not type_cfg.get("is_monster") else (palette[3])
        body_color = palette[1]
        accent = palette[2]
        hair_color = palette[3]
        outline = style_cfg.get("outline_color")
        
        # v0.3.9→v0.3.30: 颜色分层 — 使用HSV色相偏移(Hue Shift)技术
        # 像素美术最佳实践：高光偏暖色(色相向红/黄方向旋转)，
        #                     阴影偏冷色(色相向蓝方向旋转)
        # v0.3.30: 升级为真正的HSV色相旋转，替代之前的RGB通道加减法
        # 在HSV空间中旋转色相更符合色彩感知理论：
        #   - 暖偏移：色相向黄(60°)方向旋转，同时微提亮度和降低饱和度(模拟光照退色)
        #   - 冷偏移：色相向蓝(240°)方向旋转，同时微降亮度和微增饱和度(模拟阴影凝聚)
        # 参考技术：Hue Shifting / Color Temperature in Pixel Art (slynyrd, 2024)
        def _warm_shift(color, amount):
            """色相偏暖：在HSV空间向黄色(60°)方向旋转色相，模拟直射暖光"""
            r, g, b = color
            # 转换到HSV
            rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
            mx, mn = max(rf, gf, bf), min(rf, gf, bf)
            diff = mx - mn
            if diff == 0:
                h = 0
            elif mx == rf:
                h = (60 * ((gf - bf) / diff) + 360) % 360
            elif mx == gf:
                h = (60 * ((bf - rf) / diff) + 120) % 360
            else:
                h = (60 * ((rf - gf) / diff) + 240) % 360
            s = 0 if mx == 0 else diff / mx
            v = mx
            # 暖偏移：色相向60°(黄)方向旋转，偏移量与amount成比例
            # 计算到60°的最短距离
            hue_target = 60  # 黄色
            hue_diff = ((hue_target - h + 180) % 360) - 180
            hue_shift = hue_diff * (amount / 80.0)  # amount/80 控制旋转强度
            h = (h + hue_shift) % 360
            # 微提亮度（模拟光照增亮）
            v = min(1.0, v + amount / 200.0)
            # 微降饱和度（高光区退色效果）
            s = max(0.0, s - amount / 300.0)
            # HSV → RGB
            h = h % 360
            c = v * s
            x = c * (1 - abs((h / 60) % 2 - 1))
            m = v - c
            if h < 60:   rr, gg, bb = c, x, 0
            elif h < 120: rr, gg, bb = x, c, 0
            elif h < 180: rr, gg, bb = 0, c, x
            elif h < 240: rr, gg, bb = 0, x, c
            elif h < 300: rr, gg, bb = x, 0, c
            else:         rr, gg, bb = c, 0, x
            return (min(255, max(0, int((rr + m) * 255))),
                    min(255, max(0, int((gg + m) * 255))),
                    min(255, max(0, int((bb + m) * 255))))

        def _cool_shift(color, amount):
            """色相偏冷：在HSV空间向蓝色(240°)方向旋转色相，模拟阴影冷散射光"""
            r, g, b = color
            rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
            mx, mn = max(rf, gf, bf), min(rf, gf, bf)
            diff = mx - mn
            if diff == 0:
                h = 0
            elif mx == rf:
                h = (60 * ((gf - bf) / diff) + 360) % 360
            elif mx == gf:
                h = (60 * ((bf - rf) / diff) + 120) % 360
            else:
                h = (60 * ((rf - gf) / diff) + 240) % 360
            s = 0 if mx == 0 else diff / mx
            v = mx
            # 冷偏移：色相向240°(蓝)方向旋转
            hue_target = 240  # 蓝色
            hue_diff = ((hue_target - h + 180) % 360) - 180
            hue_shift = hue_diff * (amount / 80.0)
            h = (h + hue_shift) % 360
            # 微降亮度（阴影区变暗）
            v = max(0.0, v - amount / 200.0)
            # 微增饱和度（阴影区色彩凝聚）
            s = min(1.0, s + amount / 400.0)
            # HSV → RGB
            h = h % 360
            c = v * s
            x = c * (1 - abs((h / 60) % 2 - 1))
            m = v - c
            if h < 60:   rr, gg, bb = c, x, 0
            elif h < 120: rr, gg, bb = x, c, 0
            elif h < 180: rr, gg, bb = 0, c, x
            elif h < 240: rr, gg, bb = 0, x, c
            elif h < 300: rr, gg, bb = x, 0, c
            else:         rr, gg, bb = c, 0, x
            return (min(255, max(0, int((rr + m) * 255))),
                    min(255, max(0, int((gg + m) * 255))),
                    min(255, max(0, int((bb + m) * 255))))
        body_dark = _cool_shift(body_color, 30)    # 阴影→偏冷蓝
        body_light = _warm_shift(body_color, 20)    # 高光→偏暖黄
        accent_dark = _cool_shift(accent, 25)
        accent_light = _warm_shift(accent, 30)
        # v0.3.19→v0.3.25: 肤色分层 — 同样使用色相偏移
        skin_dark = _cool_shift(skin, 25)
        skin_light = _warm_shift(skin, 15)
        
        # 根据类型调整比例（v0.3.7: 应用体型比例差异化）
        head_r = int(H * type_cfg.get("head_ratio", 0.19) / 2)
        body_ratio = type_cfg.get("body_ratio", 1.0)
        leg_ratio = type_cfg.get("leg_ratio", 1.0)
        arm_ratio = type_cfg.get("arm_ratio", 1.0)
        body_w = int(W * type_cfg.get("body_w", 0.25) * body_ratio)
        body_h = int(H * 0.35 * body_ratio)
        # v0.3.8: 呼吸缩放宽度（仅影响身体矩形绘制，不影响肢体定位）
        body_draw_w = int(body_w * pose.get("body_scale_x", 1.0))
        # v0.3.25: squash & stretch — 纵向缩放影响身体高度
        body_draw_h = int(body_h * pose.get("body_scale_y", 1.0))
        leg_h = int(H * 0.2 * leg_ratio)
        
        # 应用 body_dy/head_dy 独立偏移（v0.3.6修复：body_dy 真正影响躯干位置）
        body_dy = pose["body_dy"]
        head_dy = pose["head_dy"]
        # v0.3.27: 躯干横向偏移（walk/run次级运动 — 重心左右微移）
        body_dx = pose.get("body_dx", 0)
        
        # v0.3.27: 上半身水平中心 — 受body_dx影响（头、躯干、手臂随重心横移）
        torso_cx = cx + body_dx
        # 头部位置：仅受 head_dy 影响，水平跟随躯干
        head_cy = cy - body_h // 2 - head_r + 2 + head_dy
        # 身体位置：基础位置 + body_dy 独立偏移（不再跟随头部head_dy）
        body_top_base = cy - body_h // 2 + 2 + 1  # 颈部基准位置
        body_top = body_top_base + body_dy
        # v0.3.25: body_bot 使用 body_draw_h（受 squash & stretch 纵向缩放影响）
        body_bot = body_top + body_draw_h
        leg_top = body_bot + 1
        
        # v0.3.27: 应用 body_dx 到 cx — 上半身（头/躯干/手臂/配件）使用偏移后的中心
        # 腿部将在稍后恢复原始cx以保持地面锚定
        _original_cx = cx
        if body_dx != 0:
            cx = torso_cx
        
        # ---- 绘制头部 ----
        # v0.3.21: 头部渐变着色 — 左上亮、右下暗，模拟球体光照
        # 原理：头部近似球体，根据每个像素相对球心的角度计算明暗
        # 使用方向性渐变（法线点积光源方向），比flat着色更有3D立体感
        face_type = type_cfg.get("face_type", "plain")
        # 光源方向（归一化）：左上方 (lx, ly) = (-0.5, -0.7)
        _light_len = (0.5*0.5 + 0.7*0.7) ** 0.5
        _lx, _ly = -0.5/_light_len, -0.7/_light_len
        for y in range(max(0, head_cy - head_r), min(H, head_cy + head_r)):
            for x in range(max(0, cx - head_r), min(W, cx + head_r)):
                dx, dy = x - cx, y - head_cy
                dist_sq = dx*dx + dy*dy
                if dist_sq <= head_r*head_r:
                    # v0.3.21: 球面法线渐变着色
                    # 计算法线方向（球面上的法线 = 从球心指向表面的单位向量）
                    inv_r = 1.0 / max(1, head_r)
                    nx_n = dx * inv_r
                    ny_n = dy * inv_r
                    # 法线点积光源方向 → 光照强度（-1到1）
                    dot = nx_n * _lx + ny_n * _ly
                    # 映射到亮度偏移：dot从-1(背光)到1(受光) → 偏移从-18到+15
                    brightness = int(dot * 16)
                    head_c = (
                        min(255, max(0, skin[0] + brightness)),
                        min(255, max(0, skin[1] + brightness)),
                        min(255, max(0, skin[2] + brightness)),
                        255
                    )
                    canvas[y][x] = head_c
                    
                    # ---- v0.3.7: 增强面部细节 ----
                    # v0.3.20: 眉毛情感系统 — 动画状态联动眉毛角度
                    # hurt/jump: 上扬(惊讶) | attack/defend: 内低外高(愤怒V形) 
                    # die: 下垂(虚弱) | cast: 微蹙(专注) | 其他: 正常(face_type默认)
                    brow_y = -ps - 1
                    # 动画状态影响眉毛偏移
                    brow_anim_dy = 0  # 整体Y偏移
                    brow_anim_tilt = 0  # 内外倾斜: 正值=内低外高(怒)
                    brow_anim_alpha = 1.0  # 眉毛颜色强度(1.0=正常, 0.5=淡化)
                    if anim in ("attack", "defend"):
                        brow_anim_tilt = 1  # 愤怒V形：内侧下压1px
                        brow_anim_dy = 0
                    elif anim in ("hurt", "jump"):
                        brow_anim_dy = -1  # 惊讶：整体上扬1px
                        brow_anim_tilt = -1  # 内高外低(倒V惊讶)
                    elif anim == "die":
                        brow_anim_dy = 1  # 虚弱：整体下垂1px
                        brow_anim_alpha = 0.5  # 颜色变淡
                    elif anim == "cast":
                        brow_anim_tilt = 1  # 施法专注：微蹙
                    
                    brow_base_y = brow_y + brow_anim_dy
                    # 愤怒时内侧额外下压，惊讶时内侧额外上扬
                    brow_inner_side = 1 if dx > 0 else -1
                    brow_tilt_dy = brow_anim_tilt if abs(dx) >= head_r//3 + 1 else 0
                    brow_check_y = brow_base_y - brow_tilt_dy
                    brow_zone_y = dy == brow_check_y or dy == brow_check_y - 1
                    brow_inner = abs(dx) >= head_r//3 and abs(dx) <= head_r//2

                    if brow_zone_y and brow_inner:
                        # 眉毛基础颜色（根据动画状态调整强度）
                        brow_dark = max(0, int(80 * brow_anim_alpha))
                        brow_mid = max(0, int(60 * brow_anim_alpha))
                        brow_light = max(0, int(50 * brow_anim_alpha))
                        brow_soft = max(0, int(30 * brow_anim_alpha))
                        
                        if face_type == "fierce":
                            # 怒眉：内低外高（向内倾斜）+ 动画叠加
                            base_tilt = 1 if dx > 0 else -1
                            if dy == brow_check_y and abs(dx) <= head_r//2 - 1:
                                canvas[y][x] = (max(0, skin[0]-brow_dark), max(0, skin[1]-brow_dark), max(0, skin[2]-brow_dark), 255)
                            elif dy == brow_check_y - 1 and abs(dx) >= head_r//3 + 1:
                                canvas[y][x] = (max(0, skin[0]-brow_mid), max(0, skin[1]-brow_mid), max(0, skin[2]-brow_mid), 255)
                        elif face_type == "gentle":
                            # 温柔淡眉：浅色短横线
                            if dy == brow_check_y and abs(dx) >= head_r//3 + 1 and abs(dx) <= head_r//2 - 2:
                                canvas[y][x] = (max(0, skin[0]-brow_soft), max(0, skin[1]-brow_soft), max(0, skin[2]-brow_soft), 255)
                        elif face_type == "serious":
                            # 严肃平眉：深色横线
                            if dy == brow_check_y:
                                canvas[y][x] = (max(0, skin[0]-brow_dark), max(0, skin[1]-brow_dark), max(0, skin[2]-brow_dark), 255)
                        elif face_type == "cute":
                            # 可爱弯眉：弧形短眉
                            brow_curve = 1 if abs(dx) <= head_r//3 + 2 else 0
                            if dy == brow_check_y - brow_curve:
                                canvas[y][x] = (max(0, skin[0]-brow_light), max(0, skin[1]-brow_light), max(0, skin[2]-brow_light), 255)
                    
                    # 眼睛（v0.3.19: 情感化眼部表情 — 根据动画状态调整睁眼程度）
                    # hurt/jump: 睁大(惊讶) | attack/defend: 眯眼(专注) | die: 半闭(虚弱)
                    # cast: 微睁(施法专注) | 其他(idle/walk/run): 正常
                    eye_zone_y = abs(dy) <= ps
                    if anim in ("hurt", "jump"):
                        eye_zone_y = abs(dy) <= ps + 1  # 惊讶：睁大眼
                    elif anim in ("attack", "defend"):
                        eye_zone_y = abs(dy) <= max(0, ps - 1)  # 专注：眯眼
                    elif anim == "die":
                        eye_zone_y = dy <= 0 and abs(dy) <= ps  # 虚弱：只画上半
                    eye_zone_x = abs(dx) >= head_r//3 and abs(dx) <= head_r//2
                    if eye_zone_y and eye_zone_x:
                        # 虹膜
                        iris_color = (min(255, accent[0]+30), min(255, accent[1]+30), min(255, accent[2]+30))
                        canvas[y][x] = (*iris_color, 255)
                        # 瞳孔（受惊时不画瞳孔=大虹膜=惊恐效果）
                        if anim != "hurt":
                            if abs(dx) >= head_r//3 + max(1, ps//2) and abs(dx) <= head_r//2 - max(1, ps//2):
                                canvas[y][x] = (15, 15, 25, 255)
                    # 主高光（右上方小白点，死亡时不画=失去神采）
                    if anim != "die":
                        if dy == -ps//2 and dx == head_r//3 + max(1, ps//2):
                            canvas[y][x] = (255, 255, 255, 255)
                        if dy == -ps//2 and dx == -(head_r//3 + max(1, ps//2)):
                            canvas[y][x] = (255, 255, 255, 255)
                    # v0.3.19: 副高光 — 动漫风第二高光点（主高光内侧下方，增加水润感）
                    # 只在正常/惊讶/施法时显示，眯眼和半闭时不画
                    if anim not in ("attack", "defend", "die"):
                        sub_y = max(0, -ps//2 + 1)
                        sub_dx = head_r//3 + max(1, ps//2) - 1
                        if dy == sub_y and abs(dx) == sub_dx and canvas[y][x][3] > 0:
                            canvas[y][x] = (210, 225, 255, 255)  # 淡蓝白副高光
                    
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
                    # v0.3.22: 动画状态联动嘴型 — 攻击怒吼/受击惊叫/施法吟唱/死亡松弛/防御咬牙
                    # 优先级：动画状态覆盖 > face_type默认嘴型
                    mouth_y = head_r//3 + 1
                    mouth_drawn = False  # 标记是否已由动画状态绘制
                    
                    # ---- v0.3.22: 动画驱动嘴型（优先于face_type） ----
                    if anim == "attack":
                        # 攻击怒吼：宽张嘴+露齿，比fierce基础更宽
                        if dy >= mouth_y and dy <= mouth_y + 1 and abs(dx) <= head_r//3:
                            if dy == mouth_y and abs(dx) <= head_r//3:
                                canvas[y][x] = (150, 40, 40, 255)  # 深红张嘴
                                mouth_drawn = True
                            if dy == mouth_y + 1 and abs(dx) <= head_r//5:
                                # 下排牙齿暗示
                                canvas[y][x] = (230, 225, 215, 255)
                                mouth_drawn = True
                    
                    elif anim == "hurt":
                        # 受击惊叫：大张嘴（椭圆形），痛苦+惊讶
                        mouth_open_h = 2  # 上下2行，比正常嘴型多1行
                        if dy >= mouth_y - 1 and dy <= mouth_y + mouth_open_h and abs(dx) <= head_r//4:
                            # 椭圆张嘴：中间行宽，上下行窄
                            if dy == mouth_y and abs(dx) <= head_r//4:
                                canvas[y][x] = (140, 35, 35, 255)  # 最宽行
                                mouth_drawn = True
                            elif abs(dx) <= head_r//5:
                                canvas[y][x] = (160, 45, 45, 255)
                                mouth_drawn = True
                    
                    elif anim == "cast":
                        # 施法吟唱：O形嘴（念咒时嘴型）
                        if dy == mouth_y and abs(dx) <= head_r//6:
                            canvas[y][x] = (170, 60, 60, 255)  # O形竖窄嘴
                            mouth_drawn = True
                        if dy == mouth_y - 1 and abs(dx) <= head_r//7:
                            canvas[y][x] = (180, 70, 70, 255)  # O形上缘
                            mouth_drawn = True
                        if dy == mouth_y + 1 and abs(dx) <= head_r//7:
                            canvas[y][x] = (180, 70, 70, 255)  # O形下缘
                            mouth_drawn = True
                    
                    elif anim == "die":
                        # 死亡松弛：微张下垂嘴，失去控制感
                        if dy == mouth_y and abs(dx) <= head_r//5:
                            canvas[y][x] = (160, 70, 70, 180)  # 半透明淡色（虚弱感）
                            mouth_drawn = True
                        if dy == mouth_y + 1 and abs(dx) <= head_r//6:
                            canvas[y][x] = (155, 65, 65, 140)  # 下垂半透明
                            mouth_drawn = True
                    
                    elif anim == "defend":
                        # 防御咬牙：紧绷一字线，比serious更紧更短
                        if dy == mouth_y and abs(dx) <= head_r//6:
                            canvas[y][x] = (140, 50, 50, 255)  # 紧缩深色嘴线
                            mouth_drawn = True
                    
                    elif anim == "jump":
                        # 跳跃微张：轻微张嘴（惊讶弱化版）
                        if dy == mouth_y and abs(dx) <= head_r//5:
                            canvas[y][x] = (190, 85, 85, 255)
                            mouth_drawn = True
                        if dy == mouth_y + 1 and dx == 0:
                            canvas[y][x] = (185, 80, 80, 255)  # 下方中心1像素（微张）
                            mouth_drawn = True
                    
                    # ---- face_type 默认嘴型（无动画覆盖时使用） ----
                    if not mouth_drawn and dy >= mouth_y and dy <= mouth_y + 1 and abs(dx) <= head_r//4:
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
        
        # ---- v0.3.13: 腮红渲染（独立通道，带距离衰减的柔滑圆形腮红） ----
        if face_type == "cute" or face_type == "gentle":
            blush_y_offset = head_r // 4
            blush_x_offset = head_r // 3
            blush_r = max(1, head_r // 5)
            blush_center_y = head_cy + blush_y_offset
            for blush_side in [-1, 1]:
                blush_center_x = cx + blush_side * blush_x_offset
                for by in range(max(0, blush_center_y - blush_r), min(H, blush_center_y + blush_r + 1)):
                    for bx in range(max(0, blush_center_x - blush_r), min(W, blush_center_x + blush_r + 1)):
                        bdx = bx - blush_center_x
                        bdy = by - blush_center_y
                        dist_sq = bdx*bdx + bdy*bdy
                        if dist_sq <= blush_r * blush_r:
                            if 0 <= by < H and 0 <= bx < W and canvas[by][bx][3] > 0:
                                # 距离衰减：中心最浓，边缘渐淡
                                intensity = 1.0 - (dist_sq / (blush_r * blush_r + 1))
                                blush_r_comp = min(255, int(skin[0] + 50 * intensity))
                                blush_g_comp = max(0, int(skin[1] - 15 * intensity))
                                blush_b_comp = max(0, int(skin[2] - 25 * intensity))
                                old_r, old_g, old_b, old_a = canvas[by][bx]
                                canvas[by][bx] = (
                                    (old_r + blush_r_comp) // 2,
                                    (old_g + blush_g_comp) // 2,
                                    (old_b + blush_b_comp) // 2,
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
        
        # ---- v0.3.13: 绘制耳朵 ----
        # 耳朵位于头部两侧中部，为肤色椭圆（2x3像素）
        # 被头发遮挡时不绘制（检查是否有头发像素）
        ear_w = max(1, head_r // 4)
        ear_h = max(2, head_r // 2)
        ear_y = head_cy  # 耳朵位于头部垂直中心
        for side in [-1, 1]:  # 左耳、右耳
            ear_cx = cx + side * (head_r + ear_w)
            for ey in range(max(0, ear_y - ear_h // 2), min(H, ear_y + ear_h // 2 + 1)):
                for ex in range(max(0, ear_cx - ear_w // 2), min(W, ear_cx + ear_w // 2 + 1)):
                    # 椭圆检测
                    edx = ex - ear_cx
                    edy = ey - ear_y
                    if (edx * edx * (ear_h * ear_h) + edy * edy * (ear_w * ear_w)
                            <= ear_w * ear_w * ear_h * ear_h):
                        # 检查是否被头发遮挡
                        if 0 <= ey < H and 0 <= ex < W and canvas[ey][ex][3] == 0:
                            # 耳朵外轮廓（略深肤色）
                            ear_edge = (abs(edx) >= ear_w // 2 or abs(edy) >= ear_h // 2)
                            if ear_edge:
                                canvas[ey][ex] = (max(0, skin[0]-30), max(0, skin[1]-30), max(0, skin[2]-20), 255)
                            else:
                                canvas[ey][ex] = (*skin, 255)
        
        # ---- 绘制身体（v0.3.11: 颜色分层+服装纹理图案渲染） ----
        # 纹理由 _render_all_frames 在帧循环前一次性选定
        
        for y in range(body_top, min(H, body_bot)):
            # v0.3.9: 纵向颜色渐变 — 顶部高光、底部深色
            # v0.3.15: 颜色过渡区域使用有序抖动(dithered shading)平滑过渡
            if body_bot > body_top:
                vert_t = (y - body_top) / (body_bot - body_top)  # 0=顶 1=底
            else:
                vert_t = 0.5
            # 有序抖动阈值矩阵(4x4 Bayer) — 让颜色过渡区域产生中间色错觉
            # 经典像素美术技法：两种颜色在边界处用固定图案混合，视觉上产生新色调
            dither_thresholds = [
                [ 0,  8,  2, 10],
                [12,  4, 14,  6],
                [ 3, 11,  1,  9],
                [15,  7, 13,  5],
            ]
            # v0.3.15: 带抖动的三区渐变
            # 过渡带: 0.2~0.4(高光→原色), 0.6~0.8(原色→深色)
            # 在过渡带内用 Bayer 矩阵决定每像素使用哪种颜色，模拟中间色调
            row_color = body_color  # 默认中间色
            if vert_t < 0.2:
                row_color = body_light
            elif vert_t < 0.4:
                # 高光→原色过渡带（约20%身体高度）：50%位置开始抖动
                blend = (vert_t - 0.2) / 0.2  # 0→1
                local_y_body = y - body_top
                # v0.3.30: 修复抖动矩阵索引 — 使用完整的2D坐标(x,y)
                # 之前只使用列0，导致垂直过渡带出现可见条纹
                local_x_body_ref = (cx - body_draw_w // 2)  # 身体左边界x坐标
                threshold = dither_thresholds[local_y_body % 4][(cx % 4)] / 16.0
                if blend > threshold:
                    row_color = body_color
                else:
                    row_color = body_light
            elif vert_t > 0.8:
                row_color = body_dark
            elif vert_t > 0.6:
                # 原色→深色过渡带（约20%身体高度）
                blend = (vert_t - 0.6) / 0.2  # 0→1
                local_y_body = y - body_top
                # v0.3.30: 修复抖动矩阵索引 — 使用完整的2D坐标(x,y)
                threshold = dither_thresholds[local_y_body % 4][(cx % 4)] / 16.0
                if blend > threshold:
                    row_color = body_dark
                else:
                    row_color = body_color
            
            # v0.3.28: 身体轮廓塑形 — 肩宽→腰窄→髋宽的自然体型曲线
            # 避免纯矩形僵硬感，增加角色轮廓的有机感和立体感
            # 使用 smoothstep 平滑插值，确保肩腰过渡自然无锯齿
            _waist_narrow = 0.12  # 腰部最大收窄比例（12%）
            if vert_t < 0.25:
                _cf = 1.0  # 肩部保持全宽
            elif vert_t < 0.55:
                _nt = (vert_t - 0.25) / 0.30
                _nt = _nt * _nt * (3 - 2 * _nt)  # smoothstep 平滑过渡
                _cf = 1.0 - _waist_narrow * _nt
            elif vert_t < 0.75:
                _wt = (vert_t - 0.55) / 0.20
                _wt = _wt * _wt * (3 - 2 * _wt)  # smoothstep
                _cf = (1.0 - _waist_narrow) + _waist_narrow * 0.6 * _wt
            else:
                _bt = (vert_t - 0.75) / 0.25
                _cf = (1.0 - _waist_narrow * 0.4) - 0.05 * _bt  # 底部微收连接腿部
            _contour_hw = max(2, int(body_draw_w // 2 * _cf))
            
            for x in range(max(0, cx - _contour_hw), min(W, cx + _contour_hw)):
                # v0.3.9: 横向也做微妙渐变（中心亮、边缘暗）
                # v0.3.15: 横向边缘也用抖动过渡
                h_dist = abs(x - cx) / max(1, _contour_hw)  # 0=中心 1=边缘
                local_x_body = x - (cx - body_draw_w//2)
                local_y_body = y - body_top
                dither_val = dither_thresholds[local_y_body % 4][local_x_body % 4] / 16.0
                if h_dist > 0.75:
                    # 外边缘区：深色（用抖动平滑过渡）
                    edge_blend = (h_dist - 0.75) / 0.25  # 0→1
                    if edge_blend > dither_val:
                        fx_color = (max(0, row_color[0]-12), max(0, row_color[1]-12), max(0, row_color[2]-12))
                    else:
                        fx_color = (max(0, row_color[0]-5), max(0, row_color[1]-5), max(0, row_color[2]-5))
                elif h_dist > 0.6:
                    # 轻微边缘暗化过渡区
                    edge_blend = (h_dist - 0.6) / 0.15  # 0→1
                    if edge_blend > dither_val:
                        fx_color = (max(0, row_color[0]-5), max(0, row_color[1]-5), max(0, row_color[2]-5))
                    else:
                        fx_color = row_color
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
        
        # v0.3.29: 服装高光带（Specular Band）— 胸部区域横向高光条纹增强材质质感
        # 原理：真实服装在光照下，面料凸起处（胸部/肩部）会形成一道水平高光带，
        #       这是布料在主光源下的镜面反射。这条高光带是区分"画了颜色"和"穿了衣服"的关键视觉元素
        # 实现：在身体上部1/3区域，横向画一道偏暖的高光条纹（宽度约身体60%）
        #       条纹纵向有高斯衰减（中心最亮，上下渐淡），颜色偏暖模拟布料漫反射
        spec_band_cy = body_top + int(body_draw_h * 0.3)  # 高光带中心：身体上部30%处
        spec_band_h = max(2, int(body_draw_h * 0.08))  # 高光带纵向半径（很窄）
        spec_band_hw = int(_contour_hw * 0.65)  # 高光带横向半宽（身体宽度的65%）
        for y in range(max(0, spec_band_cy - spec_band_h - 1), min(H, spec_band_cy + spec_band_h + 2)):
            for x in range(max(0, cx - spec_band_hw), min(W, cx + spec_band_hw)):
                r, g, b, a = canvas[y][x]
                if a == 0:
                    continue
                # 纵向高斯衰减
                dy_sb = abs(y - spec_band_cy)
                gauss = max(0, 1.0 - (dy_sb * dy_sb) / max(1, spec_band_h * spec_band_h))
                # 横向也做轻微衰减（中心最亮，两侧渐淡）
                dx_sb = abs(x - cx)
                h_fade = max(0, 1.0 - dx_sb / max(1, spec_band_hw))
                intensity = gauss * h_fade
                if intensity > 0.15:
                    # 暖色高光：偏黄白（布料漫反射特征色）
                    boost = int(18 * intensity)
                    canvas[y][x] = (
                        min(255, r + boost + 4),    # 红色额外+4偏暖
                        min(255, g + boost + 2),    # 绿色微增
                        min(255, b + max(0, boost - 3)),  # 蓝色少增（偏暖）
                        a
                    )
        
        # v0.3.27: 恢复原始cx — 腿部使用无偏移的中心保持地面锚定
        # （腿已经有自己的ldx/rdx偏移，不需要body_dx影响）
        if body_dx != 0:
            cx = _original_cx
        
        # ---- 绘制腿（v0.3.20: 纵向渐变着色增加立体感，匹配身体渐变风格） ----
        leg_w = body_w // 3
        # 左腿（带偏移 + 纵向渐变：顶部受光偏亮，底部阴影偏暗）
        ldx, ldy = pose["left_leg_dx"], pose["left_leg_dy"]
        for y in range(leg_top + ldy, min(H, leg_top + ldy + leg_h)):
            leg_t = (y - leg_top - ldy) / max(1, leg_h - 1)  # 0=顶 1=底
            if leg_t < 0.3:
                leg_c = body_light
            elif leg_t > 0.7:
                leg_c = body_dark
            else:
                leg_c = body_color
            for x in range(max(0, cx - body_w//2 + ldx), min(W, cx - body_w//2 + ldx + leg_w)):
                if 0 <= y < H:
                    canvas[y][x] = (*leg_c, 255)
        # 右腿（带偏移 + 纵向渐变）
        rdx, rdy = pose["right_leg_dx"], pose["right_leg_dy"]
        for y in range(leg_top + rdy, min(H, leg_top + rdy + leg_h)):
            leg_t = (y - leg_top - rdy) / max(1, leg_h - 1)  # 0=顶 1=底
            if leg_t < 0.3:
                leg_c = body_light
            elif leg_t > 0.7:
                leg_c = body_dark
            else:
                leg_c = body_color
            for x in range(max(0, cx + body_w//2 - leg_w + rdx), min(W, cx + body_w//2 + rdx)):
                if 0 <= y < H:
                    canvas[y][x] = (*leg_c, 255)
        
        # ---- v0.3.27: 按类型鞋子渲染 — 独特鞋型+双层渐变着色 ----
        # 每种角色类型有独特的鞋型设计，提升视觉辨识度和完成度
        # 鞋子使用 body_dark（上部衔接）→ shoe_color（主体）→ shoe_sole（鞋底）三层渐变
        # shoe_style: "boots"(战士/骑士), "pointed"(法师), "hunting"(弓箭手),
        #             "soft"(盗贼), "sandals"(治疗师), "claws"(怪物), "plain"(NPC/吟游诗人)
        shoe_type_map = {
            "warrior": "boots", "knight": "heavy_boots",
            "mage": "pointed", "archer": "hunting",
            "rogue": "soft", "healer": "sandals",
            "monster": "claws", "npc": "plain", "bard": "plain",
        }
        shoe_style = shoe_type_map.get(char_type_key, "plain")
        # 鞋子主色：基于body色的深色变体（偏冷偏暗，模拟皮革/金属质感）
        shoe_color = _cool_shift(body_color, 50)
        # 鞋底色：更深一级的暗色（鞋底与地面接触面）
        shoe_sole = _cool_shift(body_color, 70)
        # 鞋子高光（鞋面受光面）
        shoe_highlight = _warm_shift(shoe_color, 10)
        shoe_h = max(ps, leg_h // 3)  # 鞋子高度（从腿底部往上）

        for side in ("left", "right"):
            if side == "left":
                leg_dx, leg_dy = ldx, ldy
                leg_x0 = cx - body_w // 2 + leg_dx
            else:
                leg_dx, leg_dy = rdx, rdy
                leg_x0 = cx + body_w // 2 - leg_w + rdx

            # 该腿的鞋底Y范围
            leg_bottom = min(H, leg_top + leg_dy + leg_h)
            shoe_top_y = min(H - 1, leg_bottom - shoe_h)

            if shoe_style == "boots":
                # 战士：圆头装甲靴 — 比腿宽1px，底部加厚鞋底+微圆弧
                # 靴子比腿稍宽，模拟包裹感
                for y in range(shoe_top_y, leg_bottom):
                    if y < 0 or y >= H:
                        continue
                    # 靴子宽度随Y变化：上部窄（衔接腿），底部宽（鞋底）
                    boot_t = (y - shoe_top_y) / max(1, shoe_h - 1)  # 0=上 1=下
                    extra_w = int(boot_t * 1.5)  # 底部比上部宽1-2px
                    for x in range(max(0, leg_x0 - ps - extra_w), min(W, leg_x0 + leg_w + ps + extra_w)):
                        if canvas[y][x][3] > 0 or (0 <= y < H and 0 <= x < W):
                            # 检查是否在鞋区域内（半透明像素也覆盖）
                            if canvas[y][x][3] == 0:
                                continue
                            # 三层渐变：上部shoe_highlight → 中部shoe_color → 底部shoe_sole
                            if boot_t < 0.3:
                                sc = shoe_highlight
                            elif boot_t > 0.75:
                                sc = shoe_sole
                            else:
                                sc = shoe_color
                            canvas[y][x] = (*sc, 255)
                    # 底部最后一行加厚鞋底线（深色）
                    if y == leg_bottom - 1:
                        for x in range(max(0, leg_x0 - ps - 1), min(W, leg_x0 + leg_w + ps + 1)):
                            if 0 <= y < H and canvas[y][x][3] > 0:
                                canvas[y][x] = (*shoe_sole, 255)

            elif shoe_style == "heavy_boots":
                # 骑士：重型铁靴 — 最宽，方形钝头，金属扣环装饰
                for y in range(shoe_top_y, leg_bottom):
                    if y < 0 or y >= H:
                        continue
                    boot_t = (y - shoe_top_y) / max(1, shoe_h - 1)
                    # 重甲靴底部更宽
                    extra_w = int(boot_t * 2.5)
                    for x in range(max(0, leg_x0 - ps - extra_w), min(W, leg_x0 + leg_w + ps + extra_w)):
                        if canvas[y][x][3] == 0:
                            continue
                        if boot_t < 0.25:
                            sc = shoe_highlight
                        elif boot_t > 0.7:
                            sc = shoe_sole
                        else:
                            sc = shoe_color
                        canvas[y][x] = (*sc, 255)
                    # 铁扣装饰线（靴子中部1px横向亮线，模拟金属扣环）
                    if abs(boot_t - 0.4) < 0.15 and leg_x0 + leg_w + extra_w < W:
                        buck_x0 = max(0, leg_x0 - extra_w)
                        buck_x1 = min(W, leg_x0 + leg_w + extra_w)
                        for x in range(buck_x0, buck_x1):
                            if canvas[y][x][3] > 0:
                                canvas[y][x] = (*_warm_shift(accent, 15), 255)

            elif shoe_style == "pointed":
                # 法师：尖头鞋 — 底部逐渐收窄成尖头，优雅弧线
                for y in range(shoe_top_y, leg_bottom):
                    if y < 0 or y >= H:
                        continue
                    boot_t = (y - shoe_top_y) / max(1, shoe_h - 1)
                    # 尖头鞋：上部宽（=腿宽），底部收窄并向外延伸1px尖头
                    taper = int(boot_t * 1.5)  # 底部收窄
                    # 尖头向外延伸（朝外侧方向）
                    point_ext = int(boot_t * 2)
                    if side == "left":
                        x0 = max(0, leg_x0 - point_ext)
                        x1 = max(0, min(W, leg_x0 + leg_w - taper))
                    else:
                        x0 = max(0, min(W, leg_x0 + taper))
                        x1 = min(W, leg_x0 + leg_w + point_ext)
                    for x in range(x0, x1):
                        if canvas[y][x][3] == 0:
                            continue
                        if boot_t < 0.3:
                            sc = shoe_highlight
                        elif boot_t > 0.8:
                            sc = shoe_sole
                        else:
                            sc = shoe_color
                        canvas[y][x] = (*sc, 255)

            elif shoe_style == "hunting":
                # 弓箭手：猎靴 — 中等宽度，顶部有毛边装饰
                for y in range(shoe_top_y, leg_bottom):
                    if y < 0 or y >= H:
                        continue
                    boot_t = (y - shoe_top_y) / max(1, shoe_h - 1)
                    extra_w = int(boot_t * 1.2)
                    for x in range(max(0, leg_x0 - ps - extra_w), min(W, leg_x0 + leg_w + ps + extra_w)):
                        if canvas[y][x][3] == 0:
                            continue
                        if boot_t < 0.25:
                            sc = shoe_highlight
                        elif boot_t > 0.75:
                            sc = shoe_sole
                        else:
                            sc = shoe_color
                        canvas[y][x] = (*sc, 255)
                    # 顶部毛边装饰（靴口处1px浅色模拟翻毛/毛皮）
                    if abs(boot_t - 0.05) < 0.1:
                        for x in range(max(0, leg_x0 - ps), min(W, leg_x0 + leg_w + ps)):
                            if canvas[y][x][3] > 0:
                                canvas[y][x] = (*_warm_shift(shoe_highlight, 20), 255)

            elif shoe_style == "soft":
                # 盗贼：软底靴 — 贴合腿形，不外扩，低调
                for y in range(shoe_top_y, leg_bottom):
                    if y < 0 or y >= H:
                        continue
                    boot_t = (y - shoe_top_y) / max(1, shoe_h - 1)
                    for x in range(max(0, leg_x0), min(W, leg_x0 + leg_w)):
                        if canvas[y][x][3] == 0:
                            continue
                        if boot_t < 0.3:
                            sc = shoe_highlight
                        elif boot_t > 0.8:
                            sc = shoe_sole
                        else:
                            sc = shoe_color
                        canvas[y][x] = (*sc, 255)

            elif shoe_style == "claws":
                # 怪物：利爪脚 — 底部3个尖爪，不穿鞋
                claw_color = _warm_shift(accent, 10)  # 爪色偏暖
                for y in range(shoe_top_y, leg_bottom):
                    if y < 0 or y >= H:
                        continue
                    boot_t = (y - shoe_top_y) / max(1, shoe_h - 1)
                    for x in range(max(0, leg_x0 - ps), min(W, leg_x0 + leg_w + ps)):
                        if canvas[y][x][3] == 0:
                            continue
                        canvas[y][x] = (*shoe_color, 255)
                # 利爪：底部最后1-2行，画3个小尖角
                if leg_bottom - 1 < H and leg_bottom >= 0:
                    for claw_off in [-1, 0, 1]:  # 3个爪
                        cx_claw = leg_x0 + leg_w // 2 + claw_off * max(1, leg_w // 3)
                        for dy in range(2):  # 爪长2px
                            cy_claw = min(H - 1, leg_bottom - 1 + dy)
                            if 0 <= cx_claw < W and 0 <= cy_claw < H:
                                canvas[cy_claw][cx_claw] = (*claw_color, 255)

            else:
                # plain/NPC/吟游诗人：简单平底鞋 — 与旧版类似但加渐变
                for y in range(shoe_top_y, leg_bottom):
                    if y < 0 or y >= H:
                        continue
                    boot_t = (y - shoe_top_y) / max(1, shoe_h - 1)
                    for x in range(max(0, leg_x0 - ps), min(W, leg_x0 + leg_w + ps)):
                        if canvas[y][x][3] == 0:
                            continue
                        if boot_t > 0.7:
                            sc = shoe_sole
                        else:
                            sc = shoe_color
                        canvas[y][x] = (*sc, 255)
        
        # v0.3.27: 手臂恢复躯干偏移cx — 手臂跟随上半身横移
        if body_dx != 0:
            cx = torso_cx
        
        # ---- 绘制手臂（v0.3.19: 纵向渐变着色增加立体感） ----
        arm_w = max(ps * 2, int(leg_w * arm_ratio))
        arm_top_y = body_top + ps
        arm_bot_y = body_bot - ps
        arm_h = max(1, arm_bot_y - arm_top_y)
        # 左臂（带偏移 + 纵向渐变：顶部受光偏亮，底部阴影偏暗）
        ladx, lady = pose["left_arm_dx"], pose["left_arm_dy"]
        for y in range(arm_top_y + lady, min(H, arm_bot_y + lady)):
            arm_t = (y - arm_top_y - lady) / max(1, arm_h - 1)  # 0=顶 1=底
            if arm_t < 0.3:
                arm_c = skin_light
            elif arm_t > 0.7:
                arm_c = skin_dark
            else:
                arm_c = skin
            for x in range(max(0, cx - body_w//2 - arm_w + ladx), min(W, cx - body_w//2 + ladx)):
                if 0 <= y < H:
                    canvas[y][x] = (*arm_c, 255)
        # 右臂（带偏移 + 纵向渐变，武器侧）
        radx, rady = pose["right_arm_dx"], pose["right_arm_dy"]
        for y in range(arm_top_y + rady, min(H, arm_bot_y + rady)):
            arm_t = (y - arm_top_y - rady) / max(1, arm_h - 1)  # 0=顶 1=底
            if arm_t < 0.3:
                arm_c = skin_light
            elif arm_t > 0.7:
                arm_c = skin_dark
            else:
                arm_c = skin
            for x in range(cx + body_w//2 + radx, min(W, cx + body_w//2 + arm_w + radx)):
                if 0 <= y < H:
                    canvas[y][x] = (*arm_c, 255)
        
        # ---- v0.3.24: 手部渲染 — 手臂末端添加手掌细节增加完成度 ----
        # 手掌是手臂末端的椭圆区域（比手臂宽1px），用肤色绘制
        # 与手臂颜色一致但使用更亮的skin_light色模拟手心受光
        hand_w = arm_w + ps  # 手掌比手臂略宽
        hand_h = max(ps + 1, arm_w)  # 手掌高度
        # 左手（跟随左臂偏移）
        lh_x = cx - body_w//2 - hand_w + ladx  # 手掌中心x
        lh_y = arm_bot_y + lady - 1  # 手掌中心y（手臂底部）
        for y in range(max(0, lh_y), min(H, lh_y + hand_h)):
            for x in range(max(0, lh_x), min(W, lh_x + hand_w)):
                # 椭圆内判定
                hx = (x - lh_x - hand_w/2) / max(1, hand_w/2)
                hy = (y - lh_y - hand_h/2) / max(1, hand_h/2)
                if hx*hx + hy*hy <= 1.0:
                    canvas[y][x] = (*skin_light, 255)
        # 右手（跟随右臂偏移）
        rh_x = cx + body_w//2 + radx  # 手掌中心x
        rh_y = arm_bot_y + rady - 1  # 手掌中心y
        for y in range(max(0, rh_y), min(H, rh_y + hand_h)):
            for x in range(max(0, rh_x), min(W, rh_x + hand_w)):
                hx = (x - rh_x - hand_w/2) / max(1, hand_w/2)
                hy = (y - rh_y - hand_h/2) / max(1, hand_h/2)
                if hx*hx + hy*hy <= 1.0:
                    canvas[y][x] = (*skin_light, 255)
        
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

        # v0.3.17: 骑士 — 全覆头盔（覆盖头部+面甲+头顶羽饰）
        if type_cfg.get("has_helmet"):
            helm_color = (max(0, accent[0]-20), max(0, accent[1]-20), max(0, accent[2]-10))
            helm_highlight = (min(255, accent[0]+30), min(255, accent[1]+30), min(255, accent[2]+30))
            # 头盔主体（覆盖整个头部区域，比头大1圈）
            for y in range(max(0, head_cy - head_r - ps), head_cy + head_r//2 + 1):
                for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps + 1)):
                    dx, dy = x - cx, y - head_cy
                    dist_sq = dx*dx + (dy+ps)*(dy+ps)
                    r_sq = (head_r + ps) * (head_r + ps)
                    if dist_sq <= r_sq:
                        canvas[y][x] = (*helm_color, 255)
            # 头盔顶部高光弧线
            hl_y = max(0, head_cy - head_r - ps + 1)
            for x in range(max(0, cx - head_r//2), min(W, cx + head_r//2)):
                if 0 <= hl_y < H:
                    canvas[hl_y][x] = (*helm_highlight, 255)
            # 面甲横缝（眼睛位置的横线开口）
            visor_y = head_cy - head_r//4
            for x in range(max(0, cx - head_r + ps), min(W, cx + head_r - ps + 1)):
                if 0 <= visor_y < H:
                    canvas[visor_y][x] = (20, 15, 15, 255)  # 深色眼缝
            # 头顶羽饰（竖立的羽毛状装饰，accent色）
            plume_h = max(ps*4, head_r + ps*3)
            plume_base_y = head_cy - head_r - ps
            for dy2 in range(plume_h):
                py = plume_base_y - dy2
                # 羽毛逐渐收窄，带微弯
                curve = int(math.sin(dy2 * 0.2) * ps * 0.5)
                plume_w = max(1, ps - dy2 // (plume_h // ps + 1))
                for dx2 in range(-plume_w, plume_w + 1):
                    px = cx + curve + dx2
                    if 0 <= py < H and 0 <= px < W:
                        canvas[py][px] = (*accent, 255)

        # v0.3.17: 吟游诗人 — 尖顶帽（三角形帽子+帽檐+羽毛装饰）
        if type_cfg.get("has_hat"):
            hat_color = (max(0, accent[0]-10), max(0, accent[1]-10), max(0, accent[2]+10))
            hat_band_color = (*accent_light, 255)
            # 帽檐（宽椭圆，位于头顶稍下方）
            brim_y = head_cy - head_r + ps
            brim_rx = head_r + ps*3
            brim_ry = max(1, ps)
            for x in range(max(0, cx - brim_rx), min(W, cx + brim_rx + 1)):
                dx_b = x - cx
                if dx_b*dx_b <= brim_rx*brim_rx:
                    if 0 <= brim_y < H:
                        canvas[brim_y][x] = (*hat_color, 255)
                    if brim_y + 1 < H:
                        canvas[brim_y+1][x] = (max(0, hat_color[0]-15), max(0, hat_color[1]-15), max(0, hat_color[2]-15), 255)
            # 帽身（从帽檐向上的锥形，略微弯曲）
            hat_h = head_r + ps*5
            for dy2 in range(hat_h):
                hy = brim_y - 2 - dy2
                # 锥形收窄
                w_at_h = max(1, int(brim_rx * (1.0 - dy2 / hat_h * 0.85)))
                # 微弯
                curve = int(math.sin(dy2 * 0.15) * ps * 0.3)
                for x in range(max(0, cx - w_at_h + curve), min(W, cx + w_at_h + curve + 1)):
                    if 0 <= hy < H:
                        canvas[hy][x] = (*hat_color, 255)
            # 帽带（帽身下部一圈accent色横条纹）
            band_y = brim_y - ps
            band_h = max(1, ps)
            for dy2 in range(band_h):
                by = band_y - dy2
                w_at_h = max(1, int(brim_rx * (1.0 - dy2 / hat_h * 0.85)))
                for x in range(max(0, cx - w_at_h), min(W, cx + w_at_h + 1)):
                    if 0 <= by < H:
                        canvas[by][x] = hat_band_color
            # 帽顶高光
            tip_y = brim_y - 2 - hat_h
            if 0 <= tip_y < H:
                canvas[tip_y][cx] = (*accent_light, 255)

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
            
            # v0.3.16: 武器发光效果（加法混合 additive glow）
            # 施法动画时发光最强，其他动画轻微发光
            glow_intensity = 0.3  # 基础发光强度
            if anim == "cast":
                # 施法时根据阶段调整发光：蓄力渐强→释放峰值→恢复渐弱
                cast_t = frame_idx / max(1, 7 - 1)  # cast动画固定7帧
                if cast_t < 0.43:
                    glow_intensity = 0.3 + 0.7 * (cast_t / 0.43)  # 0.3→1.0
                elif cast_t < 0.57:
                    glow_intensity = 1.0  # 释放峰值
                else:
                    glow_intensity = 1.0 * (1 - (cast_t - 0.57) / 0.43)  # 1.0→0
            
            if glow_intensity > 0.05 and weapon in ("staff", "sword", "dagger", "bow"):
                # 发光中心点
                gx, gy = tip_x, min(H-1, tip_y)
                # 发光半径：施法时更大
                glow_r = int(3 + glow_intensity * 4)
                # 发光颜色：法杖=accent色，剑=白色，匕首=青色，弓=绿色
                if weapon == "staff":
                    gc = (min(255, accent[0] + 50), min(255, accent[1] + 50), min(255, accent[2] + 50))
                elif weapon == "sword":
                    gc = (255, 250, 240)
                elif weapon == "dagger":
                    gc = (150, 240, 255)
                else:  # bow
                    gc = (180, 255, 180)
                
                # 径向衰减加法混合
                for gy2 in range(max(0, gy - glow_r), min(H, gy + glow_r + 1)):
                    for gx2 in range(max(0, gx - glow_r), min(W, gx + glow_r + 1)):
                        dist = ((gx2 - gx)**2 + (gy2 - gy)**2) ** 0.5
                        if dist <= glow_r:
                            # 二次衰减：中心亮边缘暗
                            falloff = (1 - dist / glow_r) ** 2 * glow_intensity
                            # 加法混合（不覆盖已有像素，叠加发光）
                            existing = canvas[gy2][gx2]
                            if existing[3] > 0:
                                # 有实体像素：加法提亮
                                nr = min(255, int(existing[0] + gc[0] * falloff))
                                ng = min(255, int(existing[1] + gc[1] * falloff))
                                nb = min(255, int(existing[2] + gc[2] * falloff))
                                canvas[gy2][gx2] = (nr, ng, nb, existing[3])
                            else:
                                # 空白区域：画半透明发光光晕
                                ga = int(falloff * 120)
                                if ga > 8:  # 低于8的太淡，跳过
                                    canvas[gy2][gx2] = (gc[0], gc[1], gc[2], ga)
        
        elif weapon == "book":
            for y in range(body_top + ps + rady, body_top + ps*5 + rady):
                if 0 <= y < H:
                    for x in range(weapon_base_x, min(W, weapon_base_x + ps*3)):
                        canvas[y][x] = (180, 160, 100, 255)
        
        # v0.3.17: 吟游诗人的鲁特琴（梨形琴身+长颈+弦线）
        elif weapon == "lute":
            # 琴颈（长直线）
            neck_top_y = max(0, body_top + rady)
            neck_bot_y = min(H, body_top + body_h + rady)
            for y in range(neck_top_y, neck_bot_y):
                nx = weapon_base_x + ps // 2
                if 0 <= y < H and 0 <= nx < W:
                    canvas[y][nx] = (160, 120, 70, 255)  # 木色琴颈
                    if nx + 1 < W:
                        canvas[y][nx+1] = (140, 100, 55, 255)  # 颈边暗色
            # 琴身（梨形椭圆，位于琴颈底部）
            body_cy = neck_bot_y - ps*2
            body_rx = max(ps*3, arm_w + ps)
            body_ry = max(ps*2, arm_w)
            for y in range(max(0, body_cy - body_ry), min(H, body_cy + body_ry + 1)):
                for x in range(max(0, weapon_base_x - body_rx + ps), min(W, weapon_base_x + body_rx + ps)):
                    dx_l, dy_l = x - weapon_base_x - ps//2, y - body_cy
                    if dx_l*dx_l + dy_l*dy_l <= body_rx*body_ry:
                        if 0 <= y < H and 0 <= x < W:
                            canvas[y][x] = (180, 140, 80, 255)  # 木色琴身
            # 琴身高光
            hl_y = max(0, body_cy - body_ry // 2)
            for x in range(max(0, weapon_base_x - body_rx//3 + ps), min(W, weapon_base_x + body_rx//3 + ps)):
                if 0 <= hl_y < H:
                    canvas[hl_y][x] = (210, 175, 110, 255)
            # 琴弦（琴身上的竖直线）
            for y in range(max(0, body_cy - body_ry + ps), min(H, body_cy + body_ry)):
                sx = weapon_base_x + ps // 2
                if 0 <= y < H and 0 <= sx < W:
                    canvas[y][sx] = (230, 220, 200, 200)  # 半透明弦线
            # 音孔（琴身中央的圆形暗区）
            hole_r = max(1, body_rx // 3)
            for y in range(max(0, body_cy - hole_r), min(H, body_cy + hole_r + 1)):
                for x in range(max(0, weapon_base_x + ps//2 - hole_r), min(W, weapon_base_x + ps//2 + hole_r + 1)):
                    dx_h, dy_h = x - weapon_base_x - ps//2, y - body_cy
                    if dx_h*dx_h + dy_h*dy_h <= hole_r*hole_r:
                        if 0 <= y < H and 0 <= x < W:
                            canvas[y][x] = (100, 70, 40, 255)  # 暗色音孔
        
        # ---- 描边（v0.3.29: 深度加权描边 — 底部粗顶部细，增强空间层次感） ----
        # 原理：像素美术最佳实践中，角色底部（脚/腿）比顶部（头/发）更靠近地面，
        #       用更粗的描边模拟"近大远小"的透视效果，让角色在复杂背景下更有空间感
        # 实现：上半身用标准1px描边，下半身用2px描边（检查更大的邻域）
        if outline:
            # 构建不透明像素掩码（加速查找）
            opaque = [[canvas[y][x][3] > 0 for x in range(W)] for y in range(H)]
            outline_layer = [[False]*W for _ in range(H)]
            
            for y in range(H):
                # 深度系数：y越大（越靠近底部）→ 描边越粗
                # 使用 smoothstep 平滑过渡，避免突变分界线
                depth_t = y / max(1, H)  # 0=顶部 1=底部
                # 上半身(0-55%): 仅1px标准描边
                # 过渡区(55-75%): 混合区域
                # 下半身(75-100%): 扩展到2px描边
                if depth_t < 0.55:
                    search_range = 1
                elif depth_t < 0.75:
                    _st = (depth_t - 0.55) / 0.20
                    _st = _st * _st * (3 - 2 * _st)  # smoothstep
                    search_range = 1 if _st < 0.5 else 2
                else:
                    search_range = 2
                
                for x in range(W):
                    if opaque[y][x]:  # 已有不透明像素，跳过
                        continue
                    # 根据深度检查不同范围
                    found = False
                    for dx2, dy2 in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
                        nx, ny = x+dx2, y+dy2
                        if 0 <= nx < W and 0 <= ny < H and opaque[ny][nx]:
                            found = True
                            break
                    # 下半身额外检查2px距离的邻居
                    if not found and search_range >= 2:
                        for dx2, dy2 in [(-2,0),(2,0),(0,-2),(0,2),(-2,-1),(-2,1),(2,-1),(2,1),(-1,-2),(1,-2),(-1,2),(1,2)]:
                            nx, ny = x+dx2, y+dy2
                            if 0 <= nx < W and 0 <= ny < H and opaque[ny][nx]:
                                found = True
                                break
                    if found:
                        outline_layer[y][x] = True
            
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
        
        # ---- 明暗层次（v0.3.14: 双轴光照+色相偏移+深度阴影增强立体感） ----
        # 光源设定：左上方主光源 + 顶部环境光
        # v0.3.14改进：高光区域偏暖色（红+绿微增、蓝微减），
        #              阴影区域偏冷色（蓝微增、红+绿微减），
        #              模拟真实环境色温变化，让角色更有层次感
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
                    # 基础亮度调整
                    r2 = r + lift - shadow
                    g2 = g + lift - shadow
                    b2 = b + lift - shadow
                    
                    # v0.3.14: 色相偏移（hue shift）— 高光偏暖，阴影偏冷
                    # 高光区域：微增红+绿（暖色调），微减蓝
                    if lift > 0:
                        warm = lift * 0.3  # 暖色偏移量
                        r2 += int(warm)
                        g2 += int(warm * 0.5)
                        b2 -= int(warm * 0.3)
                    # 阴影区域：微增蓝（冷色调），微减红+绿
                    if shadow > 0:
                        cool = shadow * 0.25  # 冷色偏移量
                        r2 -= int(cool * 0.4)
                        g2 -= int(cool * 0.2)
                        b2 += int(cool)
                    
                    r2 = min(255, max(0, int(r2)))
                    g2 = min(255, max(0, int(g2)))
                    b2 = min(255, max(0, int(b2)))
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
        
        # ---- v0.3.14: 边缘背光（Rim Lighting）— 增强轮廓分离和立体感 ----
        # 在角色阴影侧（右侧）的轮廓边缘添加1px暖色高光，
        # 模拟背光散射效果，让角色从背景中"弹出"
        # 原理：真实光照中，物体背光侧边缘会有光从后方散射形成的亮边
        # 实现：在角色右侧（x > cx）的不透明像素中，找紧邻透明区域的边缘像素，
        #       微增亮度（+20）并偏暖色（+8红），形成微妙的轮廓光
        if outline:  # 只在有描边的风格中启用（非 western 风格）
            for y in range(1, H - 1):
                for x in range(cx, W - 1):  # 只处理右半部分（阴影侧）
                    r, g, b, a = canvas[y][x]
                    if a == 0:
                        continue
                    # 检查是否为右侧边缘（右邻居是透明或出界）
                    is_right_edge = (x + 1 >= W or canvas[y][x + 1][3] == 0)
                    if is_right_edge:
                        # 边缘背光：微增亮度 + 偏暖色
                        # 根据垂直位置调整强度（顶部更强=头顶光散射更明显）
                        v_pos = y / H  # 0=顶, 1=底
                        rim_strength = max(8, int(22 * (1.0 - v_pos * 0.6)))
                        canvas[y][x] = (
                            min(255, r + rim_strength + 5),  # 红色额外+5偏暖
                            min(255, g + rim_strength),
                            min(255, b + max(0, rim_strength - 4)),  # 蓝色少增一点
                            a
                        )
        
        # ---- v0.3.15: 像素聚簇清理（Pixel Cluster Cleanup）----
        # 移除孤立的单一不透明像素（四周全是透明的1px点），让角色看起来更精致
        # 经典像素美术规则：单个悬浮像素(noise)使画面显得机械/粗糙
        # 但保留描边上的孤立像素（它们是角色轮廓的一部分）
        cleanup_pass = [[False]*W for _ in range(H)]
        for y in range(1, H - 1):
            for x in range(1, W - 1):
                r, g, b, a = canvas[y][x]
                if a == 0:
                    continue
                # 检查4方向邻居
                has_opaque_neighbor = False
                for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nx2, ny2 = x+ddx, y+ddy
                    if 0 <= nx2 < W and 0 <= ny2 < H and canvas[ny2][nx2][3] > 0:
                        has_opaque_neighbor = True
                        break
                # 检查对角线邻居（更严格的孤立检测）
                if not has_opaque_neighbor:
                    for ddx, ddy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
                        nx2, ny2 = x+ddx, y+ddy
                        if 0 <= nx2 < W and 0 <= ny2 < H and canvas[ny2][nx2][3] > 0:
                            has_opaque_neighbor = True
                            break
                # 完全孤立的不透明像素 → 标记为清理
                if not has_opaque_neighbor:
                    cleanup_pass[y][x] = True
        # 执行清理：将孤立像素设为透明
        for y in range(H):
            for x in range(W):
                if cleanup_pass[y][x]:
                    canvas[y][x] = (0, 0, 0, 0)
        
        # ---- v0.3.23: 调色板色彩快照（Palette Snap）— 增强色彩统一性和像素艺术质感 ----
        # 将角色像素颜色量化到调色板附近的有限色阶，减少后处理引入的连续色调噪点
        # 原理：经过光照/AO/rim等多pass处理后，原始调色板的离散颜色被渐变为连续色，
        #       导致像素画看起来像缩小的位图而非真正的像素美术。本pass将颜色重新snap到
        #       调色板色阶上，保留光照方向但消除过度平滑。
        # 方法：对每个不透明像素，找到其在调色板扩展色阶（亮/中/暗三层）中最近的匹配色
        if palette and len(palette) >= 4:
            # 构建扩展调色板：每个调色板色生成3个亮度层
            # v0.3.25: 使用色相偏移而非均匀RGB偏移，与渲染颜色分层一致
            # 亮色层偏暖（模拟高光直射光），暗色层偏冷（模拟阴影散射光）
            snap_palette = []
            for pc in palette:
                snap_palette.append(pc)  # 原色
                # 暗色层：偏冷（蓝增，红减）— 模拟阴影
                snap_palette.append((max(0, pc[0] - int(20 * 0.4)), max(0, pc[1] - int(20 * 0.2)), max(0, pc[2] - 20)))
                # 亮色层：偏暖（红增，蓝减）— 模拟高光
                snap_palette.append((min(255, pc[0] + 15 + 3), min(255, pc[1] + 15 + 1), min(255, pc[2] + max(0, 15 - 4))))
            # 添加辅助色
            snap_palette.append((0, 0, 0))  # 纯黑（阴影/描边）
            if outline:
                snap_palette.append(outline)  # 描边色
            # 去重
            seen = set()
            unique_snap = []
            for c in snap_palette:
                if c not in seen:
                    seen.add(c)
                    unique_snap.append(c)
            snap_palette = unique_snap

            for y in range(H):
                for x in range(W):
                    r, g, b, a = canvas[y][x]
                    if a == 0:
                        continue
                    # 找最近调色板色（加权欧氏距离，绿色通道权重×2）
                    best_dist = float('inf')
                    best_color = (r, g, b)
                    for sc in snap_palette:
                        dr_s, dg_s, db_s = r - sc[0], g - sc[1], b - sc[2]
                        d = dr_s*dr_s + 2*dg_s*dg_s + db_s*db_s
                        if d < best_dist:
                            best_dist = d
                            best_color = sc
                    # 仅当距离超过阈值时才snap（避免过近颜色被不必要地替换）
                    # 阈值设为600 ≈ RGB距离约20，足够保留光照梯度但消除噪点
                    if best_dist > 200:
                        canvas[y][x] = (*best_color, a)

        # ---- v0.3.23: 头部镜面高光（Specular Highlight）— 增强面部立体感 ----
        # 在头部左上方向添加一个小型圆形高光点，模拟光滑表面的镜面反射
        # 与v0.3.21的球面法线渐变着色互补：渐变提供柔和的漫射光感，镜面高光提供锐利的反射感
        # 位置：头部圆心偏左上(cx - head_r*0.25, head_cy - head_r*0.3)
        spec_x = cx - int(head_r * 0.25)  # 偏左（头中心x就是cx）
        spec_y = head_cy - int(head_r * 0.3)   # 偏上
        spec_r = max(1, head_r // 4)  # 高光半径（很小的点）
        for sy in range(max(0, spec_y - spec_r), min(H, spec_y + spec_r + 1)):
            for sx in range(max(0, spec_x - spec_r), min(W, spec_x + spec_r + 1)):
                dx_sp, dy_sp = sx - spec_x, sy - spec_y
                dist_sq = dx_sp*dx_sp + dy_sp*dy_sp
                if dist_sq <= spec_r * spec_r:
                    r_sp, g_sp, b_sp, a_sp = canvas[sy][sx]
                    if a_sp > 0:  # 只在已有像素上叠加
                        # 高光强度：中心最强，边缘衰减
                        intensity = 1.0 - (dist_sq / max(1, spec_r * spec_r))
                        boost = int(35 * intensity)
                        canvas[sy][sx] = (
                            min(255, r_sp + boost + 8),  # 偏暖
                            min(255, g_sp + boost + 5),
                            min(255, b_sp + boost),
                            a_sp
                        )

        # ---- v0.3.26: 关节缝隙阴影（Joint Crease AO）— 增强身体部件衔接处的深度感 ----
        # 在头部-颈部、肩部-手臂、腰部-腿部等身体部件衔接区域绘制深色缝隙线
        # 原理：真实光照中，两个立体形状的交界处会形成深邃的阴影缝隙（如脖子褶皱、
        #       肩膀内侧、腰带下缘），因为环境光被两侧几何体遮挡。
        # 像素美术最佳实践：在关节处加深1-2px暗线，可以显著增强部件的"分离感"，
        #       让角色看起来不是一个扁平的整体，而是由多个立体部件组合而成。
        # 实现：检测身体关键衔接区域的像素，根据与关节线距离做衰减暗化
        neck_y = head_cy + head_r  # 颈部底端（头部球体最底端）
        # 1) 颈部缝隙：在head底端和body_top之间画1px深色线
        for y in range(max(0, neck_y - 1), min(H, body_top + 1)):
            for x in range(max(0, cx - body_draw_w // 2), min(W, cx + body_draw_w // 2)):
                r, g, b, a = canvas[y][x]
                if a > 0:
                    # 距关节中心线越近越暗（高斯衰减）
                    dist = abs(y - (neck_y + body_top) // 2)
                    max_dist = max(1, (body_top - neck_y) // 2 + 1)
                    darkness = int(22 * (1.0 - dist / max_dist))
                    if darkness > 2:
                        canvas[y][x] = (max(0, r - darkness), max(0, g - darkness), max(0, b - darkness), a)

        # 2) 腰部缝隙：在body_bot（躯干与腿的交界）画深色横线
        for x in range(max(0, cx - body_draw_w // 2), min(W, cx + body_draw_w // 2)):
            for dy_c in range(-1, 2):
                y = body_bot + dy_c
                if 0 <= y < H:
                    r, g, b, a = canvas[y][x]
                    if a > 0:
                        darkness = 18 if dy_c == 0 else 10
                        canvas[y][x] = (max(0, r - darkness), max(0, g - darkness), max(0, b - darkness), a)

        # 3) 肩部缝隙：在手臂与躯干交界处画1px深色竖线
        # 左肩
        shoulder_x_l = cx - body_draw_w // 2
        for y in range(body_top, min(H, body_top + body_draw_h // 2)):
            for dx_c in range(-1, 1):
                sx = shoulder_x_l + dx_c
                if 0 <= sx < W:
                    r, g, b, a = canvas[y][sx]
                    if a > 0:
                        canvas[y][sx] = (max(0, r - 14), max(0, g - 14), max(0, b - 14), a)
        # 右肩
        shoulder_x_r = cx + body_draw_w // 2
        for y in range(body_top, min(H, body_top + body_draw_h // 2)):
            for dx_c in range(0, 2):
                sx = shoulder_x_r + dx_c
                if 0 <= sx < W:
                    r, g, b, a = canvas[y][sx]
                    if a > 0:
                        canvas[y][sx] = (max(0, r - 14), max(0, g - 14), max(0, b - 14), a)

        # ---- v0.3.13: 地面阴影投射 — 椭圆形渐变阴影增强空间感 ----
        # 在角色脚底位置绘制一个椭圆形半透明阴影，模拟地面投影
        # 阴影宽度约等于身体宽度+margin，高度很扁（透视压缩）
        # 受 body_dy 影响：角色上升时阴影缩小变淡，下降时扩大变深
        shadow_y_base = leg_top + leg_h + body_dy  # 阴影Y基准位置
        shadow_rx = int(body_draw_w * 1.3)  # 阴影水平半径（比身体宽一些）
        shadow_ry = max(2, int(leg_h * 0.15))  # 阴影垂直半径（很扁）
        # v0.3.28: 动态跳跃阴影 — 角色越高，阴影越宽越扁越淡（透视投影模拟）
        # 原理：真实光照中，物体离地面越远，投射的阴影面积越大但浓度越低
        shadow_alpha_base = 70
        if body_dy < -2:
            _jump_h = abs(body_dy)
            _stretch = 1.0 + _jump_h * 0.06  # 每像素高度→阴影宽度+6%
            shadow_rx = int(shadow_rx * _stretch)  # 越高越宽（透视扩散）
            shadow_ry = max(1, int(shadow_ry / _stretch))  # 越高越扁（透视压缩）
            shadow_alpha_base = max(12, 70 - _jump_h * 4)  # 越高越淡（距离衰减）
        
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
