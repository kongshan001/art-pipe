"""
ArtPipe 角色生成引擎 v0.3
v0.3.76: 呼吸亮度脉冲(Breath Luminance Pulse,吸气胸腔扩张时身体微亮+呼气收缩时微暗,与body_scale_x同步让呼吸不仅影响形状还影响光照)+手部镜面高光点(Hand Specular Highlight,手掌左上1px亮白点模拟球形表面镜面反射,让手从flat色块变为有3D体积感的球形)
v0.3.75: 施法升腾魔法粒子(Cast Rising Aura Particles,蓄力阶段身体两侧accent色光粒向上飘升形成能量柱效果)+地面阴影水平跟随(Shadow Body-DX Follow,阴影中心跟随body_dx偏移让水平位移有物理基础)
v0.3.73: 瞳孔注视漂移(Pupil Gaze Drift,idle/walk时瞳孔/高光±1px正弦漂移模拟微saccade让角色活着感)+跳跃落地冲击扬尘(Jump Landing Impact Dust,jump落地帧8颗冲击扬尘粒子±6px扩散比walk扬尘更剧烈提供着陆反馈)
v0.3.65: 受击水平击退(Hurt Knockback,body_dx 3px ease-out快速击退)+死亡侧倾(Die Body Tilt,body_dx 4px ease-in加速侧倾模拟重心失衡倒地)
v0.3.57: 胸甲V形线(Chest Plate V-Line,肩到胸口的V形暗线暗示胸甲/胸肌结构)+下颌轮廓线(Jawline Contour,头部底部弧形暗线定义下颌形状)
支持三种渲染模式: procedural(程序化) / ai(AI生成) / hybrid(混合)
v0.3.53: 攻击武器动态发光(Attack Weapon Glow,蓄力微光→挥出峰值→收招渐熄三阶段)+防御武器微光(Defend Glow,格挡时武器微微闪光)+受击冲击粒子(Hurt Impact Sparks,受击时6颗accent色火花从身体中心向外扩散渐淡)
v0.3.49: 攻击武器挥动轨迹(Weapon Swing Trail,攻击挥出阶段3步渐隐残影模拟运动模糊)+行走/奔跑地面扬尘粒子(Walk/Run Dust Particles,脚着地帧地面灰尘颗粒增加运动重量感)
v0.3.46: 选择性眼睛发光(Selective Eye Glow,眼睛高光2px半径bloom散射冷白光晕模拟Hollow Knight/Ori锐利眼神)+服装褶皱暗示线(Clothing Fold Implication,V形垂坠褶皱暗线从肩向腰收敛增强面料立体质感)
纯Python实现，零外部依赖
v0.3.40: Selout选择性描边(描边色与相邻表面色3:1混合,亮面附近描边微亮/暗面附近保持深色,3D弹出效果)+垂直色温梯度(顶部冷偏移模拟天空环境光R-5/B+5,底部暖偏移模拟地面反射光R+6/G+3/B-3,角色嵌入环境感)
v0.3.34: 周期性眨眼动画(idle/walk/cast末帧闭合眼睑线+抑制高光)+身体椭球法线渐变着色(椭球法线点积光源方向补充横向立体感)
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
#   wrist_guards=护腕(手腕处环形装饰, v0.3.35)
CHAR_TYPES = {
    "warrior": {
        "name": "战士", "head_ratio": 0.16, "body_w": 0.35,  # v0.3.35: 缩小头部(0.18→0.16)配合宽壮体型，更紧凑有力
        "has_shield": True, "weapon": "sword",
        "face_type": "serious",
        "body_ratio": 1.15,  # 宽壮躯干
        "leg_ratio": 0.90,   # 短粗腿
        "arm_ratio": 1.10,   # 粗壮手臂
        "accessories": ["belt", "shoulder_pads", "scarf", "belt_pouch", "wrist_guards"],  # v0.3.35: 新增护腕
    },
    "mage": {
        "name": "法师", "head_ratio": 0.22, "body_w": 0.28,  # v0.3.35: 增大头部(0.20→0.22)配合纤细体型，更知性灵动
        "has_robe": True, "weapon": "staff",
        "face_type": "gentle",
        "body_ratio": 0.90,  # 纤细身体
        "leg_ratio": 1.15,   # 修长腿
        "arm_ratio": 0.95,   # 细长手臂
        "accessories": ["scarf", "collar", "earing", "wrist_guards", "cloak", "potion_bottles"],  # v0.3.39: 新增斗篷, v0.3.66: 新增药水瓶
    },
    "archer": {
        "name": "弓箭手", "head_ratio": 0.19, "body_w": 0.25,
        "has_hood": True, "weapon": "bow",
        "face_type": "serious",
        "body_ratio": 0.92,  # 精瘦身体
        "leg_ratio": 1.10,   # 长腿（灵活）
        "arm_ratio": 1.15,   # 长臂（拉弓）
        "accessories": ["belt", "belt_pouch", "scarf", "earing", "wrist_guards"],  # v0.3.35: 新增护腕
    },
    "rogue": {
        "name": "盗贼", "head_ratio": 0.17, "body_w": 0.22,
        "has_cape": True, "weapon": "dagger",
        "face_type": "fierce",
        "body_ratio": 0.85,  # 窄小身材
        "leg_ratio": 1.10,   # 灵活长腿
        "arm_ratio": 1.05,   # 匀称手臂
        "accessories": ["belt", "earing", "scarf", "belt_pouch", "wrist_guards"],  # v0.3.35: 新增护腕
    },
    "healer": {
        "name": "治疗师", "head_ratio": 0.22, "body_w": 0.30,  # v0.3.35: 增大头部(0.20→0.22)配合柔和气质
        "has_wings": False, "weapon": "book",
        "face_type": "gentle",
        "body_ratio": 0.95,  # 正常体型
        "leg_ratio": 1.00,   # 正常腿
        "arm_ratio": 0.95,   # 纤细手臂
        "accessories": ["collar", "scarf", "earing", "potion_bottles"],  # v0.3.66: 新增药水瓶
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
        "name": "骑士", "head_ratio": 0.15, "body_w": 0.38,  # v0.3.35: 缩小头部(0.17→0.15)配合最宽壮体型，全头盔更包裹
        "has_helmet": True, "weapon": "sword",
        "face_type": "serious",
        "body_ratio": 1.25,  # 最宽壮躯干
        "leg_ratio": 0.85,   # 短粗稳固腿
        "arm_ratio": 1.15,   # 强壮手臂
        "accessories": ["belt", "shoulder_pads", "collar", "belt_pouch", "wrist_guards", "cloak"],  # v0.3.39: 新增斗篷
    },
    # v0.3.17: 新增吟游诗人 — 轻巧辅助型角色
    "bard": {
        "name": "吟游诗人", "head_ratio": 0.21, "body_w": 0.24,  # v0.3.35: 略增头部(0.20→0.21)配合艺术气质
        "has_hat": True, "weapon": "lute",
        "face_type": "gentle",
        "body_ratio": 0.88,  # 纤细身材
        "leg_ratio": 1.05,   # 灵活腿
        "arm_ratio": 1.00,   # 匀称手臂
        "accessories": ["scarf", "earing", "collar", "belt", "cloak", "potion_bottles"],  # v0.3.39: 新增斗篷, v0.3.66: 新增药水瓶
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

        # 检测颜色（v0.3.52: 支持多颜色解析，如"红蓝骑士"同时检测红+蓝）
        color = None
        color2 = None  # v0.3.52: 第二颜色用于accent色
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
        # v0.3.52: 收集所有匹配颜色（保留出现顺序）
        _matched_colors = []
        _matched_positions = []  # 记录关键词在prompt中的位置，用于确定先后顺序
        for kw, rgb in color_map.items():
            pos = prompt_lower.find(kw)
            if pos >= 0:
                # 避免重复颜色（中文和英文可能匹配同一个色）
                if rgb not in _matched_colors:
                    _matched_colors.append(rgb)
                    _matched_positions.append(pos)
        # 按在prompt中出现位置排序（先出现的为主色）
        if _matched_colors:
            _sorted = sorted(zip(_matched_positions, _matched_colors))
            color = _sorted[0][1]   # 主色：最先出现的颜色
            if len(_sorted) > 1:
                color2 = _sorted[1][1]  # 副色：第二个出现的颜色

        return {"style": style, "char_type": char_type, "color": color, "color2": color2}

    def generate(self, prompt, style=None, char_type=None, seed=None,
                 render_mode="procedural", ai_backend="pollinations",
                 ai_width=512, ai_height=768, ai_frames_per_anim=8):
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
        # v0.3.52: 多颜色解析 — 第二颜色替换accent色(base_palette[1])
        if parsed.get("color2"):
            base_palette[1] = parsed["color2"]
        # Fisher-Yates 洗牌保持随机性
        for i in range(len(base_palette) - 1, 0, -1):
            j = rng.int_range(0, i)
            base_palette[i], base_palette[j] = base_palette[j], base_palette[i]
        # 色彩和谐度优化：基于主色生成互补/类似色增强
        base_palette = self._harmonize_palette(base_palette, rng, ct)
        
        char_id = f"char_{int(time.time())}_{seed % 10000}"
        
        # ---- 渲染模式分支 ----
        ai_result = None
        if render_mode in ("ai", "hybrid"):
            ai_result = self._generate_ai_image(
                prompt, s, ct, seed, ai_backend, ai_width, ai_height
            )

        # v0.4: 非像素风 AI 模式 → 额外生成 AI 动画帧
        ai_spritesheet_result = None
        if render_mode == "ai" and s != "pixel":
            ai_spritesheet_result = self._generate_ai_spritesheet(
                prompt, s, ct, seed, ai_backend,
                frames_per_anim=ai_frames_per_anim,
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

        # v0.4: AI 动画表数据（非像素风 AI 模式）
        if ai_spritesheet_result:
            ai_frames = ai_spritesheet_result.get("images", [])
            ai_anim_data = {}
            for frame in ai_frames:
                anim_name = frame.get("animation", "unknown")
                if anim_name not in ai_anim_data:
                    ai_anim_data[anim_name] = []
                ai_anim_data[anim_name].append({
                    "image_base64": frame["image_base64"],
                    "frame_idx": frame["frame_idx"],
                    "size": frame.get("size", 0),
                    "generation_time": frame.get("generation_time", 0),
                })
            result["ai_spritesheet"] = {
                "animations": ai_anim_data,
                "metadata": ai_spritesheet_result.get("metadata", {}),
                "layout": ai_spritesheet_result.get("layout", {}),
                "total_time": ai_spritesheet_result.get("total_time", 0),
                "success_count": ai_spritesheet_result.get("success_count", 0),
                "fail_count": ai_spritesheet_result.get("fail_count", 0),
            }

        # 附加各动画的帧数据（v0.3.3: 逐动画FPS，不同动画速度不同）
        # v0.3.33: 变量帧时长 — 关键帧(蓄力/冲击)保持更长，过渡帧更短
        #   遵循迪士尼动画12原则的"时间分配"(Timing)原则
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
        # v0.3.33: 变量帧时长系数 — 每帧相对基准时长的倍率
        # 系数>1表示该帧停留更久(强调/蓄力/冲击帧)，<1表示快速过渡
        # 设计原则: anticipation帧×1.5~2.0(蓄力感), impact/release帧×0.7~0.8(速度感), 其他帧×1.0
        anim_frame_timing = {
            "idle":   [1.2, 1.0, 1.2, 1.0],       # 呼吸: 吸气/呼气强调帧稍长
            "walk":   [1.0, 1.0, 1.1, 1.0, 1.0, 1.1], # 踏地帧(2,5)稍长
            "run":    [1.0, 0.9, 1.1, 1.0, 0.9, 1.1],  # 踏地帧(2,5)稍长,腾空帧(1,4)更快
            "jump":   [1.5, 0.8, 1.0, 0.9, 0.9, 1.8],  # 蹲蓄力×1.5, 起跳快×0.8, 落地强调×1.8
            "attack": [1.6, 0.7, 0.7, 1.5, 0.8, 1.0],  # 蓄力×1.6, 挥出快×0.7, 冲击帧×1.5
            "defend": [1.2, 1.3, 1.0, 1.0, 1.3],        # 蓄力准备×1.2, 稳守帧×1.3
            "hurt":   [0.7, 1.5, 1.2],                    # 冲击快×0.7, 后仰强调×1.5
            "die":    [1.0, 1.0, 1.2, 1.5, 2.0, 2.5],    # 渐慢: 后期帧越来越长(1→2.5)
            "cast":   [1.4, 1.2, 1.0, 0.7, 0.8, 1.0, 1.3], # 蓄力慢×1.4, 释放快×0.7, 恢复×1.3
        }
        for anim_name, frames in animations.items():
            fps = anim_fps.get(anim_name, 8)
            base_ms = int(1000 / fps)  # 基准帧时长(ms)
            timing = anim_frame_timing.get(anim_name, [1.0] * len(frames))
            # 计算每帧时长(ms)
            frame_durations = []
            for i in range(len(frames)):
                t_factor = timing[i] if i < len(timing) else 1.0
                frame_durations.append(int(base_ms * t_factor))
            result["animations"][anim_name] = {
                "frame_count": len(frames),
                "fps": fps,
                "loop": anim_name != "die",
                "frame_durations_ms": frame_durations,  # v0.3.33: 变量帧时长
            }
        
        # SpriteSheet PNG
        # v0.3.67: 按行动画布局(Per-Animation Row Layout)
        # 原理：每个动画占据精灵表的独立行，cols=最大帧数。
        #       游戏引擎可直接按行裁剪动画帧，无需复杂偏移计算。
        #       例如：idle在第0行(4帧)、walk在第1行(6帧)...
        #       比旧版固定8列布局更友好：Unity/Godot的动画导入器
        #       通常按行切割spritesheet，按行布局让导入零配置。
        all_frames = []
        frame_map = {}
        anim_durations = {name: info["frame_durations_ms"] for name, info in result["animations"].items()}
        
        # 计算每行最大列数 = 所有动画中最大帧数
        max_frames_per_anim = max(len(frames) for frames in animations.values())
        cols = max_frames_per_anim  # 每行动画最多cols帧，短动画右侧留空
        
        frame_idx = 0
        for anim_name, frames in animations.items():
            # 每个动画占一整行，start对齐到行首
            row_start = frame_idx
            # 对齐到行首（确保start是cols的整数倍）
            row_start = (frame_idx // cols) * cols
            if frame_idx % cols != 0:
                row_start += cols  # 跳到下一行
            frame_idx = row_start
            frame_map[anim_name] = {
                "start": frame_idx,
                "count": len(frames),
                "frame_durations_ms": anim_durations.get(anim_name, []),
                "row": frame_idx // cols,  # v0.3.67: 动画所在行号
            }
            # 填充行首空白（对齐用）
            while len(all_frames) < frame_idx:
                all_frames.append([[(0,0,0,0)] * self.CANVAS_W for _ in range(self.CANVAS_H)])
            all_frames.extend(frames)
            frame_idx += len(frames)
        
        # 补齐最后一行空白帧
        while len(all_frames) % cols != 0:
            all_frames.append([[(0,0,0,0)] * self.CANVAS_W for _ in range(self.CANVAS_H)])
        
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
            "layout": "per_animation_row",  # v0.3.67: 标记布局类型
        }
        
        # v0.3.67: 调色板渐变元数据导出(Palette Ramp Metadata Export)
        # 为每种调色板颜色生成亮/中/暗三级色阶，支持游戏引擎运行时调色板替换。
        # 原理：基于HSV色相旋转技术，与渲染引擎的_warm_shift/_cool_shift一致。
        #       highlight(高光)：色相偏暖+提亮，用于受光面
        #       mid(中间调)：原色，用于主色调
        #       shadow(阴影)：色相偏冷+降亮，用于背光面
        #       deep_shadow(深影)：进一步偏冷降亮，用于最深阴影
        # 游戏引擎可用此数据实现"换皮"功能：替换角色主色时，
        # 自动生成配套的高光和阴影色，保持画面色彩和谐。
        def _hsv_shift(color, hue_target, amount, bright_delta):
            """通用HSV色相偏移辅助函数"""
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
            # 色相旋转
            hue_diff = ((hue_target - h + 180) % 360) - 180
            h = (h + hue_diff * (amount / 80.0)) % 360
            v = max(0.0, min(1.0, v + bright_delta))
            # HSV → RGB
            c = v * s
            x = c * (1 - abs((h / 60) % 2 - 1))
            m = v - c
            h6 = h % 360
            if h6 < 60:   rr, gg, bb = c, x, 0
            elif h6 < 120: rr, gg, bb = x, c, 0
            elif h6 < 180: rr, gg, bb = 0, c, x
            elif h6 < 240: rr, gg, bb = 0, x, c
            elif h6 < 300: rr, gg, bb = x, 0, c
            else:          rr, gg, bb = c, 0, x
            return [min(255, max(0, int((rr + m) * 255))),
                    min(255, max(0, int((gg + m) * 255))),
                    min(255, max(0, int((bb + m) * 255)))]
        
        palette_ramp = []
        ramp_labels = ["skin", "body", "accent", "hair", "extra1", "extra2"]
        for i, base_color in enumerate(base_palette):
            base_list = list(base_color)
            ramp = {
                "role": ramp_labels[i] if i < len(ramp_labels) else f"color_{i}",
                "base": base_list,
                "highlight": _hsv_shift(base_list, 60, 20, 0.12),    # 暖偏移+提亮
                "mid": base_list,                                       # 原色
                "shadow": _hsv_shift(base_list, 240, 20, -0.12),      # 冷偏移+降亮
                "deep_shadow": _hsv_shift(base_list, 240, 35, -0.25), # 强冷偏移+强降亮
            }
            palette_ramp.append(ramp)
        result["palette_ramp"] = palette_ramp
        
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

    def _generate_ai_spritesheet(self, prompt, style, char_type, seed, backend,
                                     frames_per_anim=8):
        """v0.4: 生成AI序列帧动画表（非像素风专用）
        v0.4.1: frames_per_anim 默认8帧，支持用户自定义
        """
        try:
            from .sd_client import AIGenerator
            gen = AIGenerator(backend=backend)
            result = gen.generate_spritesheet(
                prompt=prompt,
                style=style,
                char_type=char_type,
                seed=seed,
                animations=["idle", "walk", "attack", "hurt", "die", "cast"],
                frames_per_anim=frames_per_anim,
            )
            print(f"[Engine] AI spritesheet: {result['success_count']} frames OK, "
                  f"{result['fail_count']} failed, {result['total_time']}s")
            return result
        except Exception as e:
            print(f"[Engine] AI spritesheet generation failed: {e}")
            return None

    def _harmonize_palette(self, palette, rng, char_type_key="warrior"):
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

        # ---- v0.3.37: OKLCH感知色彩距离终检 ----
        # OKLCH色彩空间比HSV/加权RGB更符合人眼感知：
        #   - 1个OKLCH单位 ≈ 1个刚可分辨差异(JND)
        #   - 解决HSV的已知问题：黄绿色和纯黄色在HSV中距离远但感知相近
        #   - 在64×80像素的精灵表中，颜色差异需要≥12 OKLCH才能可靠区分
        # 算法：RGB→线性sRGB→OKLab→OKLCH，计算极坐标色差ΔE_oklch
        # 修复案例：seed=100产生的[[255,213,79],[228,242,96],[255,243,87]]（感知相近黄色）
        def _rgb_to_oklch(r, g, b):
            """RGB → OKLCH（简化版，无矩阵运算，纯算术实现，零依赖）
            OKLCH = (L, C, H)，L∈[0,1]，C∈[0,~0.4]，H∈[0,360)
            参考：Björn Ottosson (2020) "OKLab" 色彩空间
            """
            # Step 1: sRGB → 线性 sRGB（gamma解码，使用标准IEC 61966-2-1精确公式）
            def _lin(c):
                c = c / 255.0
                if c <= 0.04045:
                    return c / 12.92
                else:
                    return ((c + 0.055) / 1.055) ** 2.4
            lr, lg, lb = _lin(r), _lin(g), _lin(b)
            # Step 2: 线性 sRGB → LMS（长波-中波-短波锥体响应）
            # 使用 OKLab 的简化 M1 矩阵（3×3，手动展开避免 numpy）
            l = lr * 0.4122214708 + lg * 0.5363325363 + lb * 0.0514459929
            m = lr * 0.2119034982 + lg * 0.6806995451 + lb * 0.1073969566
            s = lr * 0.0883024619 + lg * 0.2817188376 + lb * 0.6299787005
            # Step 3: LMS → 立方根（模拟人眼非线性响应）
            l_ = l ** (1.0/3.0) if l > 0 else 0.0
            m_ = m ** (1.0/3.0) if m > 0 else 0.0
            s_ = s ** (1.0/3.0) if s > 0 else 0.0
            # Step 4: LMS' → OKLab（M2 矩阵，手动展开）
            L_ok = l_ * 0.2104542553 + m_ * 0.7936177850 + s_ * (-0.0040720468)
            a_ok = l_ * 1.9779984951 + m_ * (-2.4285922050) + s_ * 0.4505937099
            b_ok = l_ * 0.0259040371 + m_ * 0.7827717662 + s_ * (-0.8086757660)
            # Step 5: OKLab → OKLCH
            C = (a_ok * a_ok + b_ok * b_ok) ** 0.5
            H = math.degrees(math.atan2(b_ok, a_ok)) % 360
            return L_ok, C, H

        def _oklch_delta(c1_lch, c2_lch):
            """计算两个OKLCH颜色之间的感知色差ΔE_oklch
            使用改良极坐标距离：ΔE = sqrt(ΔL² + ΔC² + 2·C₁·C₂·(1-cosΔH))
            其中 C₁·C₂·(1-cosΔH) 是色相差异的感知加权项
            """
            dL = c1_lch[0] - c2_lch[0]
            dC = c1_lch[1] - c2_lch[1]
            C1, C2 = c1_lch[1], c2_lch[1]
            dH_sq = 2.0 * C1 * C2 * (1.0 - math.cos(math.radians(c1_lch[2] - c2_lch[2])))
            return (dL * dL + dC * dC + dH_sq) ** 0.5

        # 计算所有颜色的OKLCH值
        _oklch_vals = [_rgb_to_oklch(c[0], c[1], c[2]) for c in fixed]

        # 检测并修复感知距离不足的颜色对
        # v0.3.43: 按角色类型差异化OKLCH阈值
        #   warrior/knight: 0.12 ≈ 18 JND — 大胆对比，突出力量感
        #   rogue/archer:   0.09 ≈ 14 JND — 中等对比，灵动但不花哨
        #   mage/healer:    0.06 ≈ 9 JND  — 柔和和谐，神秘/治愈气质
        #   monster:        0.10 ≈ 15 JND — 鲜明对比，突出危险感
        #   npc/bard:       0.08 ≈ 12 JND — 默认值，通用平衡
        _OKLCH_THRESHOLDS = {
            "warrior": 0.12, "knight": 0.12,
            "rogue": 0.09, "archer": 0.09,
            "mage": 0.06, "healer": 0.06,
            "monster": 0.10,
            "npc": 0.08, "bard": 0.08,
        }
        _oklch_min = _OKLCH_THRESHOLDS.get(char_type_key, 0.08)
        _max_fix_attempts = 5  # 每个颜色最多尝试5次修复（确保覆盖边缘情况）
        for i in range(1, len(fixed)):
            for _attempt in range(_max_fix_attempts):
                _too_close = False
                for j in range(i):
                    _de = _oklch_delta(_oklch_vals[i], _oklch_vals[j])
                    if _de < _oklch_min:
                        _too_close = True
                        break
                if not _too_close:
                    break
                # 修复策略：按优先级尝试（1）调亮度↑（2）调亮度↓（3）黄金角度色相
                # （4）增色度（5）组合：黄金角度+亮度偏移
                Li, Ci, Hi = _oklch_vals[i]
                if _attempt == 0:
                    # 第一次尝试：大幅增亮（+0.20），保持色相和色度
                    Li = min(0.92, Li + 0.20)
                elif _attempt == 1:
                    # 第二次尝试：大幅减暗（-0.20），保持色相和色度
                    Li = max(0.12, Li - 0.20)
                elif _attempt == 2:
                    # 第三次尝试：黄金角度偏移色相（137.5°）
                    Hi = (Hi + 137.508) % 360
                elif _attempt == 3:
                    # 第四次尝试：大幅增色度（对低饱和度灰色调最有效）
                    Ci = min(0.35, Ci + 0.15)
                else:
                    # 第五次尝试：组合 — 黄金角度色相 + 亮度跳变（最强修复）
                    Hi = (Hi + 137.508) % 360
                    Li = max(0.15, min(0.85, 0.35 if Li > 0.5 else 0.75))
                _oklch_vals[i] = (Li, Ci, Hi)
                # OKLCH → RGB 反向转换（手动展开，避免 numpy 依赖）
                _a_ok = Ci * math.cos(math.radians(Hi))
                _b_ok = Ci * math.sin(math.radians(Hi))
                # OKLab → LMS' (M2逆矩阵)
                _l_ = Li + 0.3963377774 * _a_ok + 0.2158037573 * _b_ok
                _m_ = Li - 0.1055613458 * _a_ok - 0.0638541728 * _b_ok
                _s_ = Li - 0.0894841775 * _a_ok - 1.2914855480 * _b_ok
                # 立方 → LMS
                _l = _l_ ** 3 if _l_ > 0 else 0.0
                _m = _m_ ** 3 if _m_ > 0 else 0.0
                _s = _s_ ** 3 if _s_ > 0 else 0.0
                # LMS → 线性 sRGB (M1逆矩阵)
                _lr = _l * 1.2270138511 + _m * (-0.5577999807) + _s * 0.0758016398
                _lg = _l * (-0.0405801784) + _m * 1.1122568696 + _s * (-0.0716766787)
                _lb = _l * (-0.0765878889) + _m * (-0.4208092268) + _s * 1.4845984291
                # 线性 → gamma sRGB
                def _srgb_gamma(c):
                    if c <= 0.0031308:
                        return max(0, min(255, int(c * 12.92 * 255 + 0.5)))
                    else:
                        return max(0, min(255, int((1.055 * c ** (1.0/2.4) - 0.055) * 255 + 0.5)))
                fixed[i] = (_srgb_gamma(_lr), _srgb_gamma(_lg), _srgb_gamma(_lb))
                # 从实际RGB重新计算OKLCH（补偿色域裁剪导致的偏差）
                # gamut clipping可能使目标OKLCH与实际RGB的OKLCH不一致
                _oklch_vals[i] = _rgb_to_oklch(fixed[i][0], fixed[i][1], fixed[i][2])

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
                    # v0.3.70: 死亡消散粒子（Death Dissipation Particles）— accent色光粒向上飘散
                    # 原理：RPG/动作游戏经典死亡特效——角色消亡时从身体飘出光粒/碎片，
                    #       向上缓慢飞散并逐渐淡出，营造"灵魂升华/能量消散"的氛围。
                    #       Celeste/Hollow Knight等独立游戏大量使用这种"粒子化消散"效果。
                    #       配合原有的alpha渐隐，让死亡不只是"淡出"，而是"分解成光"。
                    # 实现：每帧从角色已渲染的像素中采样若干点，在这些点上方绘制小光粒，
                    #       光粒颜色使用accent色（角色代表色），随t增大向上飘移+alpha递减。
                    accent = palette[2]
                    _W, _H = self.CANVAS_W, self.CANVAS_H
                    # 找到角色边界框
                    _bbox_x0, _bbox_x1, _bbox_y0, _bbox_y1 = _W, 0, _H, 0
                    for _dy in range(_H):
                        for _dx in range(_W):
                            if frame[_dy][_dx][3] > 0:
                                _bbox_x0 = min(_bbox_x0, _dx)
                                _bbox_x1 = max(_bbox_x1, _dx)
                                _bbox_y0 = min(_bbox_y0, _dy)
                                _bbox_y1 = max(_bbox_y1, _dy)
                    if _bbox_x0 < _bbox_x1:
                        # 消散粒子参数
                        _n_parts = 5 + int(t * 8)  # 粒子数随t增加: 5→13
                        _base_seed = f * 37 + 7  # 帧确定性种子
                        for _pi in range(_n_parts):
                            # 粒子X: 在角色宽度内伪随机分布
                            _px = _bbox_x0 + ((_base_seed + _pi * 23) % max(1, _bbox_x1 - _bbox_x0))
                            # 粒子Y: 从角色中部出发，向上飘移（t越大飘越高）
                            _py_start = _bbox_y0 + (_bbox_y1 - _bbox_y0) // 3
                            _float_up = int(t * 12 + (_pi * 3) % 8)
                            _py = _py_start - _float_up
                            # 粒子alpha: 首帧较亮，随t递减；边缘粒子更淡
                            _p_alpha = int(140 * (1.0 - t * 0.8) * max(0.2, 1.0 - _pi * 0.06))
                            # 粒子颜色: accent色微亮偏暖
                            _pr = min(255, accent[0] + 50)
                            _pg = min(255, accent[1] + 40)
                            _pb = min(255, accent[2] + 20)
                            if 0 <= _py < _H and 0 <= _px < _W and _p_alpha > 10:
                                frame[_py][_px] = (_pr, _pg, _pb, min(255, _p_alpha))
                                # 1px光晕（上下左右各一个半透明像素）
                                for _gdx, _gdy, _ga_mult in [(1,0,0.4),(-1,0,0.4),(0,1,0.4),(0,-1,0.4)]:
                                    _gx, _gy = _px + _gdx, _py + _gdy
                                    _ga = int(_p_alpha * _ga_mult)
                                    if 0 <= _gy < _H and 0 <= _gx < _W and _ga > 5:
                                        if frame[_gy][_gx][3] < _ga:  # 不覆盖更亮的像素
                                            frame[_gy][_gx] = (_pr, _pg, _pb, _ga)
                    # 死亡渐隐（原有逻辑）
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
                # v0.3.68: 攻击冲击闪光（Attack Impact Flash）
                # 原理：格斗游戏/动作游戏经典技法——攻击命中瞬间（t=0.4~0.6挥出阶段）
                #       角色全身短暂变亮，模拟冲击能量释放。Street Fighter/Hollow Knight等
                #       游戏使用1帧全白闪(flash)加强打击感。像素级别不需要那么极端，
                #       微妙亮度提升(20-35)即可在视觉上传达"命中"的瞬间感。
                #       冲击点(t≈0.5)闪光最强35，向两侧快速衰减。
                if anim_name == "attack":
                    if 0.4 <= t <= 0.7:
                        # 冲击期间：t=0.4开始，t=0.5峰值，t=0.7消散
                        _atk_t = (t - 0.4) / 0.3  # 0→1
                        if _atk_t < 0.33:
                            _atk_flash = int(_atk_t / 0.33 * 35)  # 蓄力渐强→35
                        elif _atk_t < 0.5:
                            _atk_flash = 35  # 冲击峰值
                        else:
                            _atk_flash = int(35 * (1 - (_atk_t - 0.5) / 0.5))  # 消散
                        if _atk_flash > 0:
                            frame = self._apply_flash(frame, _atk_flash)
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

    @staticmethod
    def _ease_out_back(t):
        """v0.3.64: 回弹缓出 — 经典back ease-out，先超出目标再回弹
        基于CSS/Robert Penner easeOutBack公式，overshoot量~10%
        用于：攻击前冲过冲、施法释放回弹、着地压扁过冲
        """
        s = 1.70158  # 标准overshoot系数
        t1 = t - 1
        return t1 * t1 * ((s + 1) * t1 + s) + 1

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
            "head_dx": 0,  # v0.3.72: 头部水平偏移（walk/run身体前倾）
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
            # v0.3.61: 横向重心转移（Idle Body Sway）— 慢速左右微移模拟活人站立
            # 原理：真人静止站立时重心不会完全固定，会缓慢在左右脚之间转移，
            #       这是最自然的"呼吸"动作之一（迪士尼12原则：Secondary Action）。
            #       频率设为呼吸的一半(π而非2π)，两个动作不完全同步避免机械感。
            #       ±1px偏移在64px宽画布上清晰可感但不突兀。
            #       同时激活v0.3.48头发次级运动(body_dx≠0时hair_sway生效)。
            sway = math.sin(t * math.pi)  # 半周期，比呼吸慢一倍
            pose["body_dx"] = round(sway * 1.2)
            # v0.3.61: 手臂异步微摆 — 左臂延迟0.6rad产生自然不对称
            # 原理：真人两臂摆动幅度和相位总略有差异(神经不对称性)，
            #       同步摆动看起来像机器人。0.6rad≈34°相位差足以产生
            #       可感知但不过分的不对称，比v0.3.8双臂完全同步更自然。
            arm_sway = math.sin(t * math.pi * 2 + 0.3)
            pose["left_arm_dy"] = round(math.sin(t * math.pi * 2 + 0.3 + 0.6) * 1.5)
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
            # v0.3.62: 手臂垂直摆动 — 行走时手臂前摆微抬、后摆微落
            # 生物力学：前摆时手臂自然抬起（离心效应），后摆时自然下沉（重力+放松）
            # 垂直分量与水平分量90°相位差（cos vs sin），形成椭圆摆动轨迹
            # 幅度1.5px（int后±1px），与arm_dx同量级保持自然比例
            # 左右臂各0.3rad相位差避免完全对称（延续v0.3.61 idle手臂异步思路）
            pose["left_arm_dy"] = round(math.cos(phase + math.pi + 0.3) * 1.5)
            pose["right_arm_dy"] = round(math.cos(phase - 0.3) * 1.5)

            # v0.3.72: 行走身体前倾（Walk Body Lean）— 头部相对躯干额外前倾偏移
            # 原理：真实行走时身体重心前移，躯干自然前倾约5-10°。在像素美术中无法真正旋转，
            #       但可以通过头部水平偏移(head_dx)模拟前倾效果——行走时头比身体多前倾1px。
            #       生物力学依据：行走时从脚跟到头部的质量链形成倒摆模型(inverted pendulum)，
            #       头部作为最高质量点会因惯性领先于躯干前移。
            #       相位与迈步同频(sin(phase))，前迈脚时身体前倾最大。
            #       幅度仅1px（int后±0.5→±1），保持微妙感，避免像素角色"歪头"。
            #       与head_dy叠加形成斜向运动弧线，配合body_dx已有横向偏移创造3D运动感。
            pose["head_dx"] = int(math.sin(phase) * 1.0)
            
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
            # v0.3.62: 跑步手臂垂直摆动 +0.2rad相位差（左右臂异步）
            # 保留原arm_dy逻辑，仅在左臂相位偏移+0.2rad产生微妙不对称
            pose["left_arm_dy"] = -int(abs(math.sin(phase + math.pi + 0.2)) * 1)
            # v0.3.72: 跑步身体前倾（Run Body Lean）— 头部额外前倾，幅度大于walk
            # 跑步时前倾角度约15-20°，是行走的2-3倍。head_dx幅度2px（int后±1~2），
            # 与walk的1px形成递进关系，保持动画层级的力度差异。
            # 相位使用sin(phase)，与迈步同步：前迈脚时头最前倾。
            # 效果：跑步时角色看起来冲向前方，而非原地踏步。
            # 结合body_dy的垂直弹跳，形成45°斜向运动轨迹——增强速度感。
            pose["head_dx"] = int(math.sin(phase) * 2.0)
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
                    # v0.3.64: 着地过冲回弹（先压扁过度，再弹回）
                    ov_cushion = self._ease_out_back(cushion)
                    pose["body_dy"] = int(min(4, ov_cushion * 3))  # 过冲：先到3.3px再回弹到3px
                    pose["head_dy"] = int(ov_cushion * 1)
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
            # v0.3.69: 水平重心位移(body_dx) — 蓄力后坐→挥出前冲，增加打击方向感和重量感
            #          原理：攻击不是原地挥动，身体重心会先向后蓄力再向前释放，
            #          这是格斗游戏的"anticipation-release"模式（类似拳皇/街霸），
            #          body_dx让整个上半身水平移动，配合头发/斗篷的次级运动增强动态感。
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
                # v0.3.69: 蓄力时身体后移1px（重心蓄力→后坐位移动画感）
                pose["body_dx"] = -int(swing * 1)
            else:
                # 挥出阶段：快速前刺，身体前冲但头部保持（ease-out快速爆发）
                # v0.3.64: 身体前冲使用ease_out_back过冲，模拟武器惯性回弹
                raw = (t - 0.4) / 0.6  # 0→1
                swing = self._ease_out(raw)
                retract = max(0, 1 - swing * 1.5)
                # 过冲效果：body_dy先冲过目标(-3px)，再回弹到(-2px)
                ov = self._ease_out_back(raw)
                pose["right_arm_dx"] = int(5 * (1 - retract))
                pose["right_arm_dy"] = -int(3 * (1 - retract))
                pose["body_dy"] = -int(min(3, ov * 2 + 0.5))  # 过冲：最大-3px，稳定在-2px
                pose["head_dy"] = int(max(0, 1 - swing * 2))  # 头部略微后仰后恢复
                pose["weapon_angle"] = (1 - retract) * 1.0
                # v0.3.69: 挥出时身体前冲2px，ease_out_back过冲回弹（先冲到~2.5px再回弹到2px）
                pose["body_dx"] = int(min(2, ov * 2))
            # 前冲时左腿后蹬
            if t > 0.3:
                pose["left_leg_dx"] = -2
                pose["right_leg_dx"] = 1
            
        elif anim == "hurt":
            # 受击：整体后仰（v0.3.22: ease-out缓出 — 快速冲击后减速）
            # v0.3.64: 受击后增加ease_out_back过冲回弹（被击飞→回弹→稳定）
            # v0.3.65: 受击水平击退(Hurt Knockback) — 被击飞时身体整体后移3px，
            #          ease-out曲线快速位移后减速，配合body_dy形成真实的受击弧线轨迹
            et = self._ease_out(t)
            ov = self._ease_out_back(t)
            pose["body_dx"] = int(et * 3)   # 水平击退3px，ease-out快速位移
            pose["body_dy"] = int(ov * 2)  # 过冲：先到2.2px再回弹到2px
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
            # v0.3.65: 死亡侧倾(Die Body Tilt) — 倒下时身体向一侧倾斜4px，
            #          ease-in加速侧倾模拟重心失衡倒地，比纯垂直下沉更真实自然
            et = self._ease_in(t)
            pose["body_dx"] = int(et * 4)    # 侧倾4px，ease-in逐渐加速倒向一侧
            pose["body_dy"] = int(et * 8)
            pose["head_dy"] = int(et * 10)
            pose["left_arm_dx"] = int(et * 3)  # 增强：手臂跟随侧倾方向甩出
            pose["right_arm_dx"] = int(et * 3)
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
                # v0.3.64: 释放后手臂ease_out_back过冲回弹（施法后惯性+魔力反冲）
                raw = (t - 0.57) / 0.43  # 0→1
                ease = self._ease_out(raw)
                ov = self._ease_out_back(raw)
                pose["right_arm_dy"] = -int(2 * (1 - ease))
                pose["right_arm_dx"] = int(2 * ov)  # 过冲：先到2.2再回弹到2
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
        # 身体位置：基础位置 + body_dy 独立偏移（不再跟随头部head_dy）
        body_top_base = cy - body_h // 2 + 2 + 1  # 颈部基准位置
        body_top = body_top_base + body_dy
        # v0.3.32: squash & stretch 肢体补偿 — 身体纵向缩放时，保持腿部地面锚定
        # 无补偿时 body_top 固定，body_bot 随 body_draw_h 变化推动腿部移位
        # 补偿后 body_bot 保持不变，body_top 反向调整让身体向上/下伸缩
        # 效果：stretch 时头部上升（拉伸感），squash 时头部下沉（压缩感），腿部始终着地
        delta_h = body_draw_h - body_h  # 缩放引起的身高变化量
        body_top = body_top - delta_h  # 反向偏移：stretch时body_top上移，squash时下移
        body_bot = body_top + body_draw_h
        leg_top = body_bot + 1
        # 头部位置：仅受 head_dy 影响，水平跟随躯干
        # v0.3.32: head_cy 跟随 body_top 变化，squash时头下沉，stretch时头上升
        # 原始公式 head_cy = cy - body_h//2 - head_r + 2 + head_dy
        # body_top = cy - body_h//2 + 3 + body_dy - delta_h
        # 所以 head_cy = body_top - head_r - 1 + head_dy（保持原始偏移关系）
        head_cy = body_top - head_r - 1 + head_dy
        
        # v0.3.27: 应用 body_dx 到 cx — 上半身（头/躯干/手臂/配件）使用偏移后的中心
        # 腿部将在稍后恢复原始cx以保持地面锚定
        _original_cx = cx
        if body_dx != 0:
            cx = torso_cx
        
        # v0.3.72: 应用 head_dx — 头部额外水平偏移模拟身体前倾
        # head_dx 独立于 body_dx（已通过torso_cx应用），仅影响头部和头部配件
        _head_dx = pose.get("head_dx", 0)
        if _head_dx != 0:
            # 临时偏移cx供头部渲染使用，渲染后恢复
            cx = cx + _head_dx
        
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
                    # v0.3.34: 周期性眨眼动画 — idle/walk/cast 状态下每隔数帧眨眼一次
                    # 模拟真实眨眼：正常状态约每3~4秒眨一次，游戏像素角色在循环末帧触发
                    # hurt/jump: 睁大(惊讶) | attack/defend: 眯眼(专注) | die: 半闭(虚弱)
                    # cast: 微睁(施法专注) | 其他(idle/walk/run): 正常
                    # v0.3.34: 眨眼帧判断 — idle:帧3(末帧), walk:帧5(末帧), cast:帧5
                    _blink_frame = False
                    if anim == "idle" and frame_idx == 3:
                        _blink_frame = True
                    elif anim == "walk" and frame_idx == 5:
                        _blink_frame = True
                    elif anim == "cast" and frame_idx == 5:
                        _blink_frame = True
                    # v0.3.73: 瞳孔注视漂移(Pupil Gaze Drift) — idle/walk时瞳孔缓慢偏移±1px
                    # 原理：真人眼球每3-5秒会做微saccade(扫视)，像素角色中用慢正弦模拟
                    #       让角色看起来"活着"和"有意识"，而不是僵硬盯着前方
                    #       仅idle和walk激活，战斗/受伤/施法时注意力集中不做漂移
                    _gaze_dx = 0
                    if anim == "idle":
                        _gaze_dx = int(round(math.sin(frame_idx * math.pi / 2.0)))
                    elif anim == "walk":
                        _gaze_dx = int(round(math.sin(frame_idx * math.pi / 3.0) * 0.7))
                    _edx = dx - _gaze_dx  # 眼部计算用有效dx（注视偏移后的相对位置）
                    if _blink_frame:
                        # 眨眼：眼睛闭合为一条线（眼睑），用肤色暗色画
                        eye_zone_y = dy == 0  # 只在中心线画眼睑
                    else:
                        eye_zone_y = abs(dy) <= ps
                        if anim in ("hurt", "jump"):
                            eye_zone_y = abs(dy) <= ps + 1  # 惊讶：睁大眼
                        elif anim in ("attack", "defend"):
                            eye_zone_y = abs(dy) <= max(0, ps - 1)  # 专注：眯眼
                        elif anim == "die":
                            eye_zone_y = dy <= 0 and abs(dy) <= ps  # 虚弱：只画上半
                    eye_zone_x = abs(_edx) >= head_r//3 and abs(_edx) <= head_r//2
                    if _blink_frame and eye_zone_y and eye_zone_x:
                        # 眨眼时画眼睑线（肤色暗色窄线，模拟闭合的眼皮）
                        lid_color = (max(0, skin[0]-35), max(0, skin[1]-25), max(0, skin[2]-20), 255)
                        canvas[y][x] = lid_color
                    elif eye_zone_y and eye_zone_x:
                        # v0.3.58: 虹膜径向渐变(Iris Radial Gradient)
                        # 原理：真实虹膜呈环形结构——外缘暗（与巩膜接界的limbal ring）、
                        #       中间亮环（虹膜纤维反光层）、内缘暗（瞳孔边缘虹膜收缩纹理）。
                        #       像素美术中，用2-3个明度级别的径向渐变即可暗示这个3D球面结构。
                        #       这比flat纯色虹膜更有"玻璃球"质感，眼睛看起来有深度而非贴纸。
                        # 实现：根据dx在eye_zone中的归一化位置确定3级渐变
                        #       外缘(head_r//2附近)=暗边-15，中间=亮环+30，内缘(head_r//3附近)=中暗-8
                        _iris_inner = head_r // 3
                        _iris_outer = head_r // 2
                        _iris_range = max(1, _iris_outer - _iris_inner)
                        _iris_t = (abs(_edx) - _iris_inner) / _iris_range  # 0=内缘, 1=外缘
                        _iris_base = accent
                        if _iris_t < 0.35:
                            # 内缘区（靠近鼻子侧）—— 中暗，模拟瞳孔边缘虹膜收缩
                            iris_color = (max(0, _iris_base[0] - 8), max(0, _iris_base[1] - 8), max(0, _iris_base[2] - 8))
                        elif _iris_t < 0.7:
                            # 中间亮环 —— 最亮的虹膜色，模拟纤维反光
                            iris_color = (min(255, _iris_base[0] + 30), min(255, _iris_base[1] + 30), min(255, _iris_base[2] + 30))
                        else:
                            # 外缘暗边（limbal ring）—— 虹膜与巩膜接界的暗环
                            iris_color = (max(0, _iris_base[0] - 15), max(0, _iris_base[1] - 15), max(0, _iris_base[2] - 15))
                        canvas[y][x] = (*iris_color, 255)
                        # 瞳孔（受惊时不画瞳孔=大虹膜=惊恐效果）
                        if anim != "hurt":
                            if abs(_edx) >= head_r//3 + max(1, ps//2) and abs(_edx) <= head_r//2 - max(1, ps//2):
                                canvas[y][x] = (15, 15, 25, 255)
                    # 主高光（右上方小白点，死亡时不画=失去神采）
                    # v0.3.34: 眨眼时也不画高光（眼睛闭合）
                    if anim != "die" and not _blink_frame:
                        if dy == -ps//2 and _edx == head_r//3 + max(1, ps//2):
                            canvas[y][x] = (255, 255, 255, 255)
                        if dy == -ps//2 and _edx == -(head_r//3 + max(1, ps//2)):
                            canvas[y][x] = (255, 255, 255, 255)
                    # v0.3.19: 副高光 — 动漫风第二高光点（主高光内侧下方，增加水润感）
                    # 只在正常/惊讶/施法时显示，眯眼和半闭时不画
                    # v0.3.34: 眨眼时也不画副高光
                    if anim not in ("attack", "defend", "die") and not _blink_frame:
                        sub_y = max(0, -ps//2 + 1)
                        sub_dx = head_r//3 + max(1, ps//2) - 1
                        if dy == sub_y and abs(_edx) == sub_dx and canvas[y][x][3] > 0:
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
        
        # ---- v0.3.71: 耳朵渲染（Ear Rendering）— 头部两侧微小耳朵增加角色完成度 ----
        # 原理：真实人头两侧有可见的耳朵结构，像素角色省略耳朵时头部看起来像光滑的球体，
        #       缺少解剖结构的完整性。在像素美术中，即使只有2-3px的耳朵也能大幅提升
        #       角色的可读性和完成度——MortMort/slynyrd等像素美术教育者都将耳朵列为
        #       "头部三要素"（头形+面部+耳朵）之一。
        #       怪物(monster)使用尖耳(pointed)，其他角色使用圆耳(rounded)。
        #       耳朵位置在头部球体水平中心线的两侧边缘，与眼睛同高（真实解剖位置）。
        #       耳朵颜色使用skin色（耳廓可见部分）+skin_dark色（耳内阴影），
        #       受光侧(左)耳朵使用skin_light增加光照一致性。
        # 实现：在头部两侧各画2-3px的半圆/三角形耳朵区域：
        #       圆耳：2列×3行的半圆形，左侧受光用skin_light，右侧背光用skin
        #       尖耳(怪物)：3列×4行的三角形，向上外侧延伸，用skin色
        #       耳内阴影：耳廓中心1px用skin_dark，模拟耳孔/耳道暗影
        _ear_type = "pointed" if type_cfg.get("is_monster") else "rounded"
        # 耳朵Y中心：与眼睛同高（头部垂直中心附近）
        _ear_cy = head_cy
        # 耳朵X位置：头部球体边缘 ±1px
        _ear_left_x = cx - head_r
        _ear_right_x = cx + head_r
        if _ear_type == "rounded":
            # 圆耳：2列×3行的半圆形，紧贴头部球体两侧
            for _eside in (-1, 1):  # -1=左, 1=右
                _ear_base_x = cx + _eside * head_r  # 头部边缘
                # 左侧受光(亮)，右侧背光(暗)
                _ear_color = skin_light if _eside < 0 else skin
                for _ey_off in range(-1, 2):  # 3行：上中下
                    _ey = _ear_cy + _ey_off
                    for _ex_off in range(2):  # 2列向外延伸
                        _ex = _ear_base_x + _eside * _ex_off
                        if 0 <= _ey < H and 0 <= _ex < W:
                            # 椭圆判定：行方向的衰减，顶部和底部行只画1px
                            if _ey_off == 0 and _ex_off <= 1:
                                canvas[_ey][_ex] = (*_ear_color, 255)
                            elif abs(_ey_off) == 1 and _ex_off == 0:
                                canvas[_ey][_ex] = (*_ear_color, 255)
                # 耳内阴影：中心1px用skin_dark
                _ear_inner_x = _ear_base_x + (_eside * 0)  # 就在头部边缘
                _ear_inner_y = _ear_cy
                if 0 <= _ear_inner_y < H and 0 <= _ear_inner_x < W:
                    canvas[_ear_inner_y][_ear_inner_x] = (*skin_dark, 255)
        else:
            # 尖耳(怪物)：3列×4行的三角形，向上外侧延伸
            for _eside in (-1, 1):
                _ear_base_x = cx + _eside * (head_r - 1)
                _ear_color = skin
                for _ey_off in range(-2, 2):  # 4行
                    # 三角形：越往上越窄，越往下越宽
                    _tri_w = max(1, 2 - abs(_ey_off - 1))  # 顶部1px宽，底部2px宽
                    _ey = _ear_cy + _ey_off
                    for _ex_off in range(_tri_w):
                        _ex = _ear_base_x + _eside * _ex_off
                        if 0 <= _ey < H and 0 <= _ex < W:
                            # 尖端高光
                            if _ey_off == -2:
                                canvas[_ey][_ex] = (*skin_light, 255)
                            else:
                                canvas[_ey][_ex] = (*_ear_color, 255)
                # 耳内阴影
                _ear_inner_y = _ear_cy - 1
                _ear_inner_x = _ear_base_x
                if 0 <= _ear_inner_y < H and 0 <= _ear_inner_x < W:
                    canvas[_ear_inner_y][_ear_inner_x] = (*skin_dark, 255)
        
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
        # v0.3.64: 头发体积色带 — 中间色（发丝体色，介于暗色和基色之间）
        hair_mid = (
            (hair_dark[0] + hair_color[0]) // 2,
            (hair_dark[1] + hair_color[1]) // 2,
            (hair_dark[2] + hair_color[2]) // 2,
        )

        if hair_style != "bald":
            if hair_style == "short":
                # 短发：头顶薄层（覆盖头部上半部分）
                # v0.3.64: 体积色带 — 顶部高光→中间色→根部暗色，3层渐变
                hair_top_y = max(0, head_cy - head_r - ps)
                hair_bot_y = head_cy - head_r//3
                hair_height = max(1, hair_bot_y - hair_top_y)
                for y in range(hair_top_y, hair_bot_y):
                    # 垂直位置比例: 0=顶部(高光), 1=底部(暗色)
                    band_t = (y - hair_top_y) / hair_height
                    for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps)):
                        dx, dy = x - cx, y - head_cy
                        if dx*dx + (dy+ps)*(dy+ps) <= (head_r+ps)*(head_r+ps) and dy < -head_r//3:
                            # v0.3.64: 三色带着色
                            if band_t < 0.25:
                                canvas[y][x] = (*hair_light, 255)  # 顶部：高光
                            elif band_t < 0.6:
                                canvas[y][x] = (*hair_color, 255)  # 中上：基色
                            else:
                                canvas[y][x] = (*hair_mid, 255)    # 中下：中间色（过渡到暗色）
                # 刘海高光
                hl_y = max(0, head_cy - head_r - ps + 1)
                for x in range(max(0, cx - head_r//2), min(W, cx + head_r//2)):
                    if 0 <= hl_y < H and canvas[hl_y][x][3] == 0:
                        canvas[hl_y][x] = (*hair_light, 255)

            elif hair_style == "medium":
                # 中发：覆盖头顶+两侧到耳朵位置
                # v0.3.48: 次级运动 — 两侧延伸头发随body_dx反向延迟摆动
                # v0.3.64: 体积色带 — 顶部高光→基色→根部中间色
                _hair_sway = -body_dx if body_dx != 0 else 0
                med_top_y = max(0, head_cy - head_r - ps)
                med_bot_y = head_cy + head_r//4
                med_height = max(1, med_bot_y - med_top_y)
                for y in range(med_top_y, med_bot_y):
                    band_t = (y - med_top_y) / med_height
                    for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps)):
                        dx, dy = x - cx, y - head_cy
                        # 椭圆形头发覆盖
                        hair_rx = head_r + ps
                        hair_ry = head_r + ps
                        if dx*dx + (dy+ps)*(dy+ps) <= hair_rx*hair_ry and dy < 0:
                            # v0.3.64: 三色带
                            if band_t < 0.2:
                                canvas[y][x] = (*hair_light, 255)  # 顶部：高光
                            elif band_t < 0.55:
                                canvas[y][x] = (*hair_color, 255)  # 中上：基色
                            else:
                                canvas[y][x] = (*hair_mid, 255)    # 中下：中间色
                        # 两侧延伸（v0.3.48: 受hair_sway影响，运动时偏移）
                        elif abs(dy) <= head_r//3 and abs(dx) >= head_r - ps and abs(dx) <= head_r + ps:
                            sway_x = x + _hair_sway
                            if 0 <= sway_x < W and 0 <= y < H and canvas[y][sway_x][3] == 0:
                                canvas[y][sway_x] = (*hair_dark, 255)
                            elif 0 <= x < W:
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
                # v0.3.48: 次级运动 — 长发两侧垂发随body_dx反向延迟摆动（跟随通过原则）
                # v0.3.64: 体积色带 — 顶部高光→基色→根部中间色
                _hair_sway = -body_dx if body_dx != 0 else 0
                # 头顶部分
                long_top_y = max(0, head_cy - head_r - ps)
                long_bot_y = head_cy + head_r//3
                long_height = max(1, long_bot_y - long_top_y)
                for y in range(long_top_y, long_bot_y):
                    band_t = (y - long_top_y) / long_height
                    for x in range(max(0, cx - head_r - ps*2), min(W, cx + head_r + ps*2)):
                        dx, dy = x - cx, y - head_cy
                        hair_rx = head_r + ps*2
                        hair_ry = head_r + ps
                        if dx*dx + (dy+ps)*(dy+ps) <= hair_rx*hair_ry and dy < 0:
                            # v0.3.64: 三色带
                            if band_t < 0.2:
                                canvas[y][x] = (*hair_light, 255)  # 顶部：高光
                            elif band_t < 0.5:
                                canvas[y][x] = (*hair_color, 255)  # 中上：基色
                            else:
                                canvas[y][x] = (*hair_mid, 255)    # 中下：中间色
                # 两侧长发垂下到肩部（v0.3.48: 受hair_sway偏移）
                hair_drop_top = head_cy
                hair_drop_bot = min(H, body_top + body_h // 3)
                for y in range(hair_drop_top, hair_drop_bot):
                    # 左侧（v0.3.48: 加sway偏移）
                    for x in range(max(0, cx - head_r - ps*2 + _hair_sway), max(0, cx - head_r + ps + _hair_sway)):
                        if 0 <= x < W and canvas[y][x][3] == 0:
                            canvas[y][x] = (*hair_dark, 255)
                    # 右侧（v0.3.48: 加sway偏移）
                    for x in range(min(W, cx + head_r - ps + _hair_sway), min(W, cx + head_r + ps*2 + _hair_sway)):
                        if 0 <= x < W and canvas[y][x][3] == 0:
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
                # v0.3.48: 次级运动 — 尖刺尖端受body_dx反向偏移（惯性跟随）
                _spike_sway = -body_dx if body_dx != 0 else 0
                num_spikes = 5
                spike_base_y = head_cy - head_r + ps
                for i in range(num_spikes):
                    # 每根刺的X位置均匀分布在头顶
                    spike_x = cx - head_r + int((i + 0.5) * (2 * head_r) / num_spikes)
                    spike_h = head_r // 2 + (i % 2) * (head_r // 3)  # 交替高低
                    spike_w = max(ps, 2)
                    # 画三角形尖刺（v0.3.48: 顶部偏移更大）
                    for dy in range(spike_h):
                        # v0.3.48: 尖刺越高sway越大（距离加权）
                        _spike_dist = min(1.0, dy / max(1, spike_h * 0.5))
                        _spike_dx = int(_spike_sway * _spike_dist)
                        tip_y = spike_base_y - spike_h + dy
                        half_w = max(1, (spike_h - dy) * spike_w // spike_h)
                        for dx in range(-half_w, half_w + 1):
                            px = spike_x + dx + _spike_dx
                            if 0 <= tip_y < H and 0 <= px < W:
                                canvas[tip_y][px] = (*hair_color, 255)
                    # 尖端高光
                    tip_y = spike_base_y - spike_h
                    tip_x_final = spike_x + int(_spike_sway * 1.0)
                    if 0 <= tip_y < H and 0 <= tip_x_final < W:
                        canvas[tip_y][tip_x_final] = (*hair_light, 255)
                # 底部连接层（头顶填充）
                for y in range(max(0, head_cy - head_r - ps), spike_base_y):
                    for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps)):
                        dx, dy = x - cx, y - head_cy
                        if dx*dx + (dy+ps)*(dy+ps) <= (head_r+ps)*(head_r+ps) and dy < -head_r//3:
                            canvas[y][x] = (*hair_color, 255)

            elif hair_style == "ponytail":
                # 马尾：头顶覆盖 + 一根辫子垂到背后
                # v0.3.48: 次级运动 — 马尾辫受body_dx反向延迟摆动（跟随通过原则）
                _tail_sway = -body_dx if body_dx != 0 else 0
                # 头顶部分（类似medium）
                for y in range(max(0, head_cy - head_r - ps), head_cy):
                    for x in range(max(0, cx - head_r - ps), min(W, cx + head_r + ps)):
                        dx, dy = x - cx, y - head_cy
                        if dx*dx + (dy+ps)*(dy+ps) <= (head_r+ps)*(head_r+ps) and dy < -head_r//3:
                            canvas[y][x] = (*hair_color, 255)
                # 马尾辫：从头顶右侧偏后延伸向下，带轻微波浪
                # v0.3.48: 增加tail_sway次级运动偏移
                tail_start_x = cx + head_r // 2
                tail_start_y = head_cy - head_r + ps
                tail_len = min(H - tail_start_y, body_h + leg_h // 2)
                for dy in range(tail_len):
                    wave = int(math.sin(dy * 0.15 + frame_idx * 0.2) * ps)
                    # v0.3.48: 次级运动 — 越靠近辫尾，sway影响越大（距离加权）
                    _tail_dist_factor = min(1.0, dy / max(1, tail_len * 0.3))
                    _tail_offset = int(_tail_sway * _tail_dist_factor)
                    ty = tail_start_y + dy
                    for dx in range(-ps, ps + 1):
                        tx = tail_start_x + wave + _tail_offset + dx
                        if 0 <= ty < H and 0 <= tx < W:
                            canvas[ty][tx] = (*hair_dark, 255)
                    # 马尾高光线
                    if 0 <= ty < H and 0 <= tail_start_x + wave + _tail_offset < W:
                        canvas[ty][tail_start_x + wave + _tail_offset] = (*hair_light, 255)
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
        
        # ---- v0.3.38: 头发体积渐变着色（Hair Volumetric Gradient） ----
        # 原理：头发包裹在头部球体上方，应有与头部类似的3D光照效果。
        #       目前头发使用flat纯色（hair_color），缺乏立体感，看起来像"贴片"。
        #       本后处理对所有头发像素施加基于位置的亮度偏移：
        #       - 靠近光源方向（左上）的头发像素变亮
        #       - 远离光源方向（右下）的头发像素变暗
        #       与v0.3.21头部球面法线使用同一光源方向(-0.5, -0.7)
        # 实现：扫描头发区域像素，通过颜色距离识别hair_color/hair_dark/hair_light像素，
        #       计算与头心的偏移→法线点积→亮度偏移(±12)，模拟头发球面光照
        if hair_style != "bald":
            _hgx0 = max(0, cx - head_r - ps * 3)
            _hgx1 = min(W, cx + head_r + ps * 3)
            _hgy0 = max(0, head_cy - head_r - ps * 5)
            _hgy1 = min(H, head_cy + head_r + ps * 2)
            for y in range(_hgy0, _hgy1):
                for x in range(_hgx0, _hgx1):
                    _hp = canvas[y][x]
                    if _hp[3] == 0:
                        continue
                    # 识别头发像素：检查是否匹配hair_color/hair_dark/hair_light（颜色距离<50）
                    _is_h = False
                    for _hc in (hair_color, hair_dark, hair_light):
                        if (abs(int(_hp[0]) - _hc[0]) + abs(int(_hp[1]) - _hc[1]) + abs(int(_hp[2]) - _hc[2])) < 50:
                            _is_h = True
                            break
                    if not _is_h:
                        continue
                    # 计算与头心的偏移
                    _hdx = x - cx
                    _hdy = y - head_cy
                    # 使用与v0.3.21相同的光源方向
                    _hinv_r = 1.0 / max(1, head_r + ps)
                    _hnx = _hdx * _hinv_r
                    _hny = _hdy * _hinv_r
                    # 光源方向(归一化)：与头部球面着色一致
                    _hdot = _hnx * _lx + _hny * _ly
                    # v0.3.58: 色带量化(Banded Quantization) — 将连续渐变分4级离散色带
                    # 原理：像素美术经典技法"banding"——将连续光照量化为3-4个明度级别，
                    #       形成清晰的亮/中间亮/中间暗/暗四个色带，比平滑渐变更有像素感。
                    #       这是最专业像素美术工作流的标准操作：先用连续渐变定光照方向，
                    #       再量化为离散色阶保持每个色带纯净一致。
                    #       参考：slynyrd(2024)像素教程"Posterize your gradients for cleaner pixel art"
                    #       量化后每个色带内的像素颜色完全一致，消除亚像素色彩噪声，
                    #       同时在色带边界形成锐利过渡——这是像素艺术的核心美学特征。
                    # v0.3.66: 色相偏移渐变(Hue-Shift Gradient) — 用暖/冷色温替代纯亮度偏移
                    #       与v0.3.30身体着色一致：高光区向暖黄色旋转色相(+饱和度降低)，
                    #       阴影区向冷蓝色旋转色相(+饱和度增加)。头发不再只是明暗变化，
                    #       而是有真实的色温过渡，大幅提升立体感和材质真实感。
                    # 实现：4级色带分别用_warm_shift/_cool_shift替代纯亮度加减
                    _hband = _hdot * 2 + 2  # 映射到[0, 4]
                    _hbase = (int(_hp[0]), int(_hp[1]), int(_hp[2]))
                    if _hband < 1.0:
                        _hshifted = _cool_shift(_hbase, 18)   # 深阴影带→冷色温（强冷偏移）
                    elif _hband < 2.0:
                        _hshifted = _cool_shift(_hbase, 7)    # 过渡暗带→微冷色温
                    elif _hband < 3.0:
                        _hshifted = _warm_shift(_hbase, 8)    # 过渡亮带→微暖色温
                    else:
                        _hshifted = _warm_shift(_hbase, 20)   # 高光带→暖色温（强暖偏移）
                    canvas[y][x] = (*_hshifted, _hp[3])
        
        # ---- v0.3.39: 发丝纹理(Strand Texture) — 竖直交替条纹模拟发丝走向 ----
        # 原理：真实头发由数千根独立发丝组成，在光照下形成规律的光影条纹。
        #       像素美术经典技法：用交替的亮暗竖条纹模拟发丝走向，是最有效也最常用的
        #       头发质感提升手法。slynyrd(2024)教程将其列为"必做"技法之一。
        #       竖条纹让头发从"平面色块"变成"有纤维纹理的表面"，视觉质量飞跃式提升。
        # 实现：对每个头发像素，根据其X坐标对4取模交替加减亮度(±7)，
        #       形成每2px宽一组的亮暗交替竖条纹。受光侧条纹加强，背光侧减弱。
        #       叠加在v0.3.38体积渐变之上，两者正交互补（渐变=球面光照，纹理=发丝走向）。
        if hair_style != "bald":
            for y in range(_hgy0, _hgy1):
                for x in range(_hgx0, _hgx1):
                    _sp = canvas[y][x]
                    if _sp[3] == 0:
                        continue
                    # 识别头发像素（颜色距离阈值60，兼容体积渐变后的色偏）
                    _is_hs = False
                    for _hc in (hair_color, hair_dark, hair_light):
                        if (abs(int(_sp[0]) - _hc[0]) + abs(int(_sp[1]) - _hc[1]) + abs(int(_sp[2]) - _hc[2])) < 60:
                            _is_hs = True
                            break
                    if not _is_hs:
                        continue
                    # 竖直条纹：每4px一个周期，前2px亮(+7)，后2px暗(-7)
                    # 使用相对于角色中心的X坐标，保证条纹对称居中
                    _strand_mod = (x - cx) % 4
                    if _strand_mod < 2:
                        _strand_off = 7   # 亮条纹（模拟受光发丝束）
                    else:
                        _strand_off = -7  # 暗条纹（模拟阴影中的发丝间隙）
                    # 受光侧(左)增强条纹对比度，背光侧(右)减弱
                    # 这符合真实光照：受光面高光更锐利，背光面散射使纹理模糊
                    _h_side = (x - cx) / max(1, head_r + ps)
                    if _h_side < -0.2:
                        _strand_off = int(_strand_off * 1.3)  # 受光侧加粗条纹
                    elif _h_side > 0.2:
                        _strand_off = int(_strand_off * 0.7)  # 背光侧柔化条纹
                    canvas[y][x] = (
                        min(255, max(0, int(_sp[0]) + _strand_off)),
                        min(255, max(0, int(_sp[1]) + _strand_off)),
                        min(255, max(0, int(_sp[2]) + _strand_off)),
                        _sp[3]
                    )
        
        # ---- v0.3.59: 动漫发型高光带(Anime Highlight Bands) — 对角线状亮带模拟动漫反光 ----
        # 原理：在动漫/游戏角色插图中，头发常有斜向的亮色带状高光（俗称"丝带高光"），
        #       这是光源从斜上方照射头发时，光滑发丝表面形成的镜面反射带。
        #       参考：Pixiv/wiki教科书风格"アニメ塗り"(anime cel shading)技法——
        #       先平涂底色→画暗面→画斜高光带→点缀最亮锐利高光。
        #       在像素美术中，用2-3px宽的对角线亮带即可暗示这个效果，
        #       让头发从"素色色块"变成"有光泽的动漫发型"，辨识度大幅提升。
        # 实现：基于(x+y)的对角线周期，在受光侧(左上)生成周期性亮带，
        #       带宽由head_r缩放，强度随受光方向衰减，与v0.3.39竖条纹正交互补。
        if hair_style != "bald":
            _hl_period = max(4, head_r)       # 对角线亮带周期(像素)
            _hl_width = max(1, head_r // 6)   # 亮带宽度(像素)
            _hl_offset = int(-cx * 0.3)       # 相对角色中心偏移，保证对称
            for y in range(_hgy0, _hgy1):
                for x in range(_hgx0, _hgx1):
                    _bp = canvas[y][x]
                    if _bp[3] == 0:
                        continue
                    # 识别头发像素
                    _is_hb = False
                    for _hc in (hair_color, hair_dark, hair_light):
                        if (abs(int(_bp[0]) - _hc[0]) + abs(int(_bp[1]) - _hc[1]) + abs(int(_bp[2]) - _hc[2])) < 70:
                            _is_hb = True
                            break
                    if not _is_hb:
                        continue
                    # 对角线位置：斜向带状，沿(x+y)方向分布
                    _diag_pos = (x + y + _hl_offset) % _hl_period
                    # 仅在受光侧(左上方)产生高光带，背光侧跳过
                    _hside = (x - cx) / max(1, head_r + ps)
                    _vside = (y - head_cy) / max(1, head_r + ps)
                    if _hside > 0.15 and _vside > 0:
                        continue  # 右下方(背光侧)不画高光带
                    # 高光带强度：受光侧最强，渐向背光侧衰减
                    _hl_strength = 1.0
                    if _hside > -0.1:
                        _hl_strength = max(0.0, 0.5 - _hside)
                    if _vside > -0.3:
                        _hl_strength *= max(0.0, 1.0 - _vside * 1.5)
                    # 判断当前像素是否在高光带内
                    if _diag_pos < _hl_width and _hl_strength > 0.1:
                        _hl_boost = int(20 * _hl_strength)
                        canvas[y][x] = (
                            min(255, max(0, int(_bp[0]) + _hl_boost + 5)),
                            min(255, max(0, int(_bp[1]) + _hl_boost + 3)),
                            min(255, max(0, int(_bp[2]) + _hl_boost)),
                            _bp[3]
                        )
        
        # ---- v0.3.37: 发际线轮廓高光(Rim Light) ----
        # 原理：在像素美术中，rim light（边缘光/轮廓光）是专业技法：
        #   - 在物体外轮廓添加一条亮线，模拟背光照射效果
        #   - 作用1：将角色从背景中"剥离"出来，增强可读性（尤其深色背景）
        #   - 作用2：给头发增加体积感，暗示头发是包裹在头部的3D球体而非平面色块
        #   - 作用3：强化头发纹理质感，让发丝边缘有光泽感
        # 实现：扫描头发像素，找到外侧轮廓（相邻有透明/非头发像素的边缘），
        #       在轮廓外侧1px添加半透明高光，强度略弱于顶部高光（hair_light-20）
        #       仅应用于头顶和两侧，不应用于底部（底部已有投射阴影系统v0.3.33）
        if hair_style != "bald":
            _rim_color = (min(255, hair_light[0] + 15),
                          min(255, hair_light[1] + 15),
                          min(255, hair_light[2] + 15))
            _rim_bg_alpha = 180  # 轮廓光透明度（0-255），180≈70%不透明，柔和不刺眼
            # 扫描范围：头部上方和两侧
            for y in range(max(0, head_cy - head_r - ps * 2), min(H, head_cy + head_r // 2)):
                for x in range(max(0, cx - head_r - ps * 2), min(W, cx + head_r + ps * 2)):
                    _px = canvas[y][x]
                    # 只处理非头发、非空像素（跳过已有头发色和空像素）
                    if _px[3] > 0:
                        _is_hair_px = False
                        for _hc in (hair_color, hair_dark, hair_light):
                            if (abs(int(_px[0]) - _hc[0]) + abs(int(_px[1]) - _hc[1]) + abs(int(_px[2]) - _hc[2])) < 80:
                                _is_hair_px = True
                                break
                        if _is_hair_px:
                            continue
                    # 检查4邻域是否有头发像素（仅上/左/右，不检查下方以避免与投射阴影冲突）
                    _has_hair_neighbor = False
                    for _ny, _nx in ((y - 1, x), (y, x - 1), (y, x + 1)):
                        if 0 <= _ny < H and 0 <= _nx < W:
                            _np = canvas[_ny][_nx]
                            if _np[3] > 0:
                                for _hc in (hair_color, hair_dark, hair_light):
                                    if (abs(int(_np[0]) - _hc[0]) + abs(int(_np[1]) - _hc[1]) + abs(int(_np[2]) - _hc[2])) < 80:
                                        _has_hair_neighbor = True
                                        break
                            if _has_hair_neighbor:
                                break
                    # 仅在上方1/3的头部区域添加rim light（头顶和侧面）
                    _dy = y - head_cy
                    if _has_hair_neighbor and _dy < head_r // 4:
                        # 检查当前像素是否为空（在画布外区域添加新像素）
                        if _px[3] == 0:
                            canvas[y][x] = (*_rim_color, _rim_bg_alpha)
                        else:
                            # 与现有像素混合（alpha blending）
                            _a = _rim_bg_alpha / 255.0
                            _oa = _px[3] / 255.0
                            _fa = _a + _oa * (1 - _a)
                            if _fa > 0:
                                canvas[y][x] = (
                                    min(255, int((_rim_color[0] * _a + _px[0] * _oa * (1 - _a)) / _fa)),
                                    min(255, int((_rim_color[1] * _a + _px[1] * _oa * (1 - _a)) / _fa)),
                                    min(255, int((_rim_color[2] * _a + _px[2] * _oa * (1 - _a)) / _fa)),
                                    min(255, int(_fa * 255))
                                )
        
        # ---- v0.3.33: 发型投射阴影 — 头发在脸部/额头的投影增加深度层次 ----
        # 原理：真实光照中，头发会在额头和面部投射阴影，这是头部最重要的深度线索之一。
        #       缺少这个阴影会让头发看起来像"贴在"头皮上，而非自然覆盖在头部上方。
        #       在像素美术中，这个技法叫做"cast shadow"（投射阴影），与AO（环境光遮蔽）互补：
        #       AO是物体自身缝隙的暗化，投射阴影是一个物体在另一个物体表面的投影。
        # 实现：扫描头发像素的底部边缘，在下方1-2px的皮肤区域添加偏冷暗化。
        #       偏冷是因为头发遮挡了暖色主光源，剩余光是偏冷的天空/环境散射光。
        #       阴影只应用于头部球体范围内的皮肤像素，避免影响耳朵和身体。
        if hair_style != "bald":
            _hs_primary = 18    # 主阴影暗化量（紧贴头发下方1px）
            _hs_secondary = 8   # 次级阴影暗化量（再下方1px，渐淡消失）
            for y in range(max(1, head_cy - head_r - ps * 2), min(H - 2, head_cy + head_r // 3)):
                for x in range(max(0, cx - head_r - ps * 2), min(W, cx + head_r + ps * 2)):
                    # 限制在头部球体范围内（避免在耳朵/身体区域误投阴影）
                    _hs_dx = x - cx
                    _hs_dy = y - head_cy
                    if _hs_dx * _hs_dx + _hs_dy * _hs_dy > (head_r + ps + 2) * (head_r + ps + 2):
                        continue
                    # 检查上方像素是否为头发色
                    _above = canvas[y - 1][x]
                    if _above[3] == 0:
                        continue
                    _above_is_hair = False
                    for _hc in (hair_color, hair_dark, hair_light):
                        if (abs(int(_above[0]) - _hc[0]) + abs(int(_above[1]) - _hc[1]) + abs(int(_above[2]) - _hc[2])) < 80:
                            _above_is_hair = True
                            break
                    if not _above_is_hair:
                        continue
                    # 检查当前像素是否为皮肤色（匹配基础肤色，允许光照偏移）
                    _curr = canvas[y][x]
                    if _curr[3] == 0:
                        continue
                    _cr, _cg, _cb, _ca = _curr
                    _skin_dist = abs(_cr - skin[0]) + abs(_cg - skin[1]) + abs(_cb - skin[2])
                    if _skin_dist < 80:
                        # 主阴影：偏冷暗化（蓝色少减→偏冷色调）
                        canvas[y][x] = (max(0, _cr - _hs_primary + 2),
                                        max(0, _cg - _hs_secondary),
                                        max(0, _cb - _hs_primary + 5),
                                        _ca)
                        # 次级阴影：再下方1px，更淡的暗化
                        if y + 1 < H:
                            _below = canvas[y + 1][x]
                            if _below[3] > 0:
                                _br, _bg, _bb, _ba = _below
                                _below_skin = abs(_br - skin[0]) + abs(_bg - skin[1]) + abs(_bb - skin[2])
                                if _below_skin < 80:
                                    canvas[y + 1][x] = (max(0, _br - _hs_secondary + 1),
                                                        max(0, _bg - _hs_secondary),
                                                        max(0, _bb - _hs_secondary + 3),
                                                        _ba)
        
        # ---- v0.3.36: 绘制耳朵（内耳细节：耳甲阴影+耳轮高光+耳垂） ----
        # 耳朵位于头部两侧中部，为肤色椭圆（2x3像素）
        # 被头发遮挡时不绘制（检查是否有头发像素）
        # v0.3.36增强：添加耳甲腔阴影（中心深色凹陷）、耳轮高光（上边缘亮色）
        # 和耳垂（底部圆润凸起），使耳朵从"贴面色块"升级为有立体感的器官
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
                            ear_edge = (abs(edx) >= ear_w // 2 or abs(edy) >= ear_h // 2)
                            # v0.3.36: 内耳细节判定
                            _ear_center = (abs(edx) <= max(0, ear_w // 2 - 1) and 
                                          abs(edy) <= max(0, ear_h // 2 - 1))
                            _ear_upper_edge = (edy < 0 and ear_edge)
                            _ear_lobe = (edy > 0 and abs(edy) >= ear_h // 2 - 1 and 
                                        abs(edx) <= max(0, ear_w // 2 - 1))
                            
                            if _ear_center:
                                # 耳甲腔阴影：中心偏暗偏红（模拟凹陷处的散射光）
                                canvas[ey][ex] = (max(0, skin[0]-18), 
                                                  max(0, skin[1]-20), 
                                                  max(0, skin[2]-15), 255)
                            elif _ear_upper_edge:
                                # 耳轮高光：上边缘偏亮（受光面凸起反射）
                                canvas[ey][ex] = (min(255, skin[0]+8), 
                                                  min(255, skin[1]+6), 
                                                  min(255, skin[2]+4), 255)
                            elif _ear_lobe:
                                # 耳垂：略偏暖的肤色（耳垂血供丰富，偏红润）
                                canvas[ey][ex] = (min(255, skin[0]+5), 
                                                  max(0, skin[1]-2), 
                                                  max(0, skin[2]-5), 255)
                            elif ear_edge:
                                # 外轮廓（略深肤色）
                                canvas[ey][ex] = (max(0, skin[0]-30), max(0, skin[1]-30), max(0, skin[2]-20), 255)
                            else:
                                canvas[ey][ex] = (*skin, 255)
        
        # ---- v0.3.57b: 下颌轮廓线（Jawline Contour）— 头部底部弧形暗线定义下颌形状 ----
        # 原理：真实人脸中，下颌线(jawline)是头部底部的一道弧形转折线——从耳前延伸到下巴尖。
        #       在3D视角下，下颌线是头部和颈部之间的几何分界线，具有明显的明暗转折。
        #       专业像素美术中，在头部球体底部添加一条弧形暗线来暗示下颌骨结构：
        #       (1)让头部从"圆球"变为"有骨骼结构的脸"
        #       (2)增强头-颈分离感（与v0.3.50a下巴投射阴影互补）
        #       (3)为不同角色类型提供面部差异化基础（战士方颌/法师尖颌等）
        # 实现：在头部球体底部（head_cy + head_r*0.6 ~ head_cy + head_r），
        #       沿球面弧线绘制1px宽的暗化线。暗化量沿弧线变化：
        #       中间（下巴尖）最浅（-8），两侧（下颌角）最深（-15），
        #       因为下颌角处骨骼转折更锐利，产生更深的阴影。
        _jaw_y_start = head_cy + int(head_r * 0.60)
        _jaw_y_end = head_cy + head_r
        for _jy in range(max(0, _jaw_y_start), min(H, _jaw_y_end)):
            # 计算当前Y对应的头部球面X范围
            _jdy = _jy - head_cy
            # 球面方程: dx^2 + dy^2 <= r^2 → dx范围
            _jdx_max_sq = head_r * head_r - _jdy * _jdy
            if _jdx_max_sq <= 0:
                continue
            _jdx_max = int(_jdx_max_sq ** 0.5)
            # 在球面边缘的左右各1px处画暗线
            for _jside in [-1, 1]:
                _jx = cx + _jside * _jdx_max
                if 0 <= _jx < W:
                    _jpx = canvas[_jy][_jx]
                    if _jpx[3] > 0:
                        # 纵向位置因子：0=顶部(jaw_start) 1=底部(jaw_end)
                        _jt = (_jy - _jaw_y_start) / max(1, _jaw_y_end - _jaw_y_start)
                        # 横向位置因子：靠近中心（下巴尖）浅，靠近两侧（下颌角）深
                        _jh_factor = abs(_jx - cx) / max(1, _jdx_max)
                        _j_darken = int(8 + 7 * _jh_factor)
                        # 光照补偿：左侧受光面稍浅
                        if _jside == -1:
                            _j_darken = max(4, _j_darken - 3)
                        canvas[_jy][_jx] = (
                            max(0, _jpx[0] - _j_darken),
                            max(0, _jpx[1] - _j_darken),
                            max(0, _jpx[2] - _j_darken + 1),
                            _jpx[3]
                        )
            # 也暗化下巴尖底部1px弧线（中间区域）
            if _jy >= _jaw_y_end - 2:
                for _jmx in range(max(0, cx - max(1, _jdx_max // 2)), min(W, cx + max(1, _jdx_max // 2) + 1)):
                    _jmpx = canvas[_jy][_jmx]
                    if _jmpx[3] > 0:
                        canvas[_jy][_jmx] = (
                            max(0, _jmpx[0] - 6),
                            max(0, _jmpx[1] - 6),
                            max(0, _jmpx[2] - 5),
                            _jmpx[3]
                        )

        # ---- v0.3.50a: 下巴投射阴影（Chin Cast Shadow）— 下巴在下颈部/上胸部的柔和投影 ----
        # 原理：真实光照中，下巴作为突出结构会在下方产生一道弧形阴影投射到颈部和上胸部。
        #       这是头-颈区域最重要的深度线索之一，缺少它会让下巴看起来"融进"脖子。
        #       与v0.3.33头发投射阴影不同：头发阴影投在额头上（上方→下方，冷色调），
        #       下巴阴影投在颈部/胸口（头部→身体，偏暖色调因为距离近且受环境反射影响）。
        #       专业像素美术技法（Slynyrd, MortMort教程）：在头部底端画一道弧形暗带，
        #       宽度与下巴弧度一致，向下渐淡2-3px，是区分"业余"和"专业"角色的关键细节。
        # 实现：扫描头部球体底部边缘（head_cy + head_r*0.6 ~ head_cy + head_r），
        #       在其下方2-3px的皮肤/身体像素上添加偏暖暗化（R-15,G-12,B-8）。
        #       阴影形状随头部球体底部弧线：中间最深（下巴尖正下方），两侧渐浅（下颌角）。
        #       偏暖是因为颈部皮肤反射了衣物和环境的暖色光。
        _chin_shadow_base = head_cy + head_r  # 下巴底端Y坐标
        _chin_shadow_depth = 3  # 阴影延伸深度（px）
        for _cs_dy in range(_chin_shadow_depth):
            _cs_y = _chin_shadow_base + _cs_dy
            if _cs_y < 0 or _cs_y >= H:
                continue
            # 阴影宽度随深度增加：下巴尖处窄，往下渐宽（模拟光锥扩散）
            _cs_half_w = int(head_r * (0.5 + _cs_dy * 0.15))
            for _cs_x in range(max(0, cx - _cs_half_w), min(W, cx + _cs_half_w)):
                _cs_px = canvas[_cs_y][_cs_x]
                if _cs_px[3] == 0:
                    continue
                # 横向衰减：中间最深，两侧渐浅（弧形阴影）
                _cs_hdx = abs(_cs_x - cx) / max(1, _cs_half_w)
                if _cs_hdx > 1.0:
                    continue
                # 纵向衰减：越往下越淡
                _cs_vfade = 1.0 - _cs_dy / _chin_shadow_depth
                # 综合强度（横向弧形 × 纵向渐淡）
                _cs_intensity = (1.0 - _cs_hdx * _cs_hdx) * _cs_vfade
                if _cs_intensity < 0.1:
                    continue
                # 暗化量：偏暖色调（R多减，B少减→阴影偏暖）
                _cs_dark = int(_cs_intensity * 20)
                if _cs_dark > 1:
                    canvas[_cs_y][_cs_x] = (
                        max(0, int(_cs_px[0]) - _cs_dark - 3),     # R多减3偏暖阴影
                        max(0, int(_cs_px[1]) - _cs_dark),          # G标准减
                        max(0, int(_cs_px[2]) - _cs_dark + 5),      # B少减5（偏暖）
                        _cs_px[3]
                    )
        
        # v0.3.72: 恢复 head_dx 偏移 — 身体部分使用 torso_cx（不含head_dx）
        if _head_dx != 0:
            cx = cx - _head_dx
        
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
        
        # ---- v0.3.50b: 领口分色线（Neckline Edge Line）— 颈部与身体的衣物边界线 ----
        # 原理：像素美术中"内部分色线(inner separation line)"的经典应用：
        #       在颈部（皮肤）和身体（衣物）的交界处画一道水平暗线，
        #       让角色看起来像"穿着领口"而不是"头长在身体上"。
        #       与v0.3.39袖口分色线同理：都是不同材质交界处的视觉分隔线。
        #       这条线暗示了衣物的领口/领子存在，即使没有画具体的领子形状，
        #       也能让观者自动脑补出"这里有一件衣服的上边缘"。
        # 实现：在body_top行画1px水平暗线，宽度等于身体实际渲染宽度，
        #       颜色比身体色深30-40单位。仅覆盖不透明像素。
        #       左侧受光面稍浅（+8暖光补偿），右侧背光面更深，保持光照一致性。
        _nl_y = body_top
        if 0 <= _nl_y < H:
            for _nl_x in range(max(0, cx - _contour_hw), min(W, cx + _contour_hw)):
                _nl_px = canvas[_nl_y][_nl_x]
                if _nl_px[3] == 0:
                    continue
                # 左侧受光面稍浅，右侧背光面更深
                _nl_light_bias = 0
                if _nl_x < cx:
                    _nl_light_bias = 6  # 受光侧补偿
                _nl_dark_r = max(0, body_color[0] - 35 + _nl_light_bias)
                _nl_dark_g = max(0, body_color[1] - 32 + _nl_light_bias)
                _nl_dark_b = max(0, body_color[2] - 28 + _nl_light_bias)
                canvas[_nl_y][_nl_x] = (_nl_dark_r, _nl_dark_g, _nl_dark_b, 255)
        
        # ---- v0.3.34: 身体椭球法线渐变着色 ----
        # 将身体近似为椭球体，计算每个像素的法线方向与光源方向的点积
        # 补充已有的纵向三区渐变（body_light/body_color/body_dark），增加横向立体感
        # 与头部v0.3.21球面法线着色使用相同的光源方向，确保全身光照一致
        _body_nx_factor = 1.0 / max(1, _contour_hw)  # 横向归一化因子
        _body_ny_factor = 1.0 / max(1, body_draw_h // 2)  # 纵向归一化因子
        _body_light_len = (0.5*0.5 + 0.7*0.7) ** 0.5
        _blx, _bly = -0.5/_body_light_len, -0.7/_body_light_len  # 光源方向（与头部一致）
        for y in range(body_top, min(H, body_bot)):
            for x in range(max(0, cx - _contour_hw - 2), min(W, cx + _contour_hw + 2)):
                r, g, b, a = canvas[y][x]
                if a == 0:
                    continue
                # 只影响身体区域的像素（排除已画的手臂等非身体像素）
                # 简单判断：在身体矩形范围内的非透明像素
                bdx = x - cx
                bdy = y - (body_top + body_draw_h // 2)
                # 椭球法线计算
                nx = bdx * _body_nx_factor
                ny = bdy * _body_ny_factor
                n_len = (nx*nx + ny*ny) ** 0.5
                if n_len > 1.0:
                    continue  # 椭球外的像素不处理
                if n_len < 0.01:
                    nx_n, ny_n = 0.0, -1.0  # 中心点法线朝上
                else:
                    # 椭球表面法线方向（梯度方向）
                    nx_n = nx / max(0.01, n_len)
                    ny_n = ny / max(0.01, n_len)
                # 法线·光源 → 光照强度
                dot = nx_n * _blx + ny_n * _bly
                brightness = int(dot * 8)  # 微妙调节（±8），不覆盖原有渐变
                if brightness != 0:
                    canvas[y][x] = (
                        min(255, max(0, r + brightness)),
                        min(255, max(0, g + brightness)),
                        min(255, max(0, b + brightness)),
                        a
                    )
        
        # ---- v0.3.63: 身体边缘光(Body Rim Light) — 光照侧轮廓亮线增强3D立体感 ----
        # 原理：与v0.3.37头发轮廓光(rim light)同理，在身体外轮廓的光照侧（左侧）
        #       添加一条明亮的边缘线，模拟主光源从左上方照射时在身体边缘产生的高光。
        #       这是专业像素美术中区分"平面着色"和"3D光照"的关键技法：
        #       (1) 让身体看起来像被光源包裹的3D物体，而非扁平色块
        #       (2) 与头发rim light形成统一的光照语言，全身一致
        #       (3) 在深色背景上增强角色可读性（轮廓剥离效果）
        #       (4) 与已有的边缘暗化(h_dist>0.75)互补：暗侧边缘暗化+亮侧边缘提亮=完整的光照包裹
        # 实现：扫描身体每行，找到光照侧（左侧）最外缘的非透明像素，
        #       对最外侧1px提亮+12暖色偏移，次外侧1px提亮+6暖色（渐变过渡）。
        #       范围：肩部到腰部上方（跳过领口线和腰带/腿部过渡区）。
        _brim_y0 = body_top + int(body_draw_h * 0.05)  # 跳过领口分色线区域
        _brim_y1 = body_top + int(body_draw_h * 0.65)  # 到腰部上方（腰带在50-55%）
        for _bry in range(max(0, _brim_y0), min(H, _brim_y1)):
            # 从左侧扫描身体边缘（光照侧）
            _edge_count = 0
            for _brx in range(max(0, cx - body_draw_w), min(W, cx)):
                _bp = canvas[_bry][_brx]
                if _bp[3] > 0:
                    _edge_count += 1
                    if _edge_count <= 2:
                        # 外侧1px: 强提亮+暖色; 内侧1px: 弱提亮（渐变过渡）
                        _rim_bst = 12 if _edge_count == 1 else 6
                        canvas[_bry][_brx] = (
                            min(255, _bp[0] + _rim_bst + 3),    # 红+3偏暖
                            min(255, _bp[1] + _rim_bst),        # 绿正常提亮
                            min(255, _bp[2] + max(0, _rim_bst - 4)),  # 蓝少提→整体偏暖
                            _bp[3]
                        )
                    else:
                        break  # 只处理最外缘2px
        
        # ---- v0.3.56a: 肩线暗带 (Shoulder Line Shadow) — 肩部横向阴影增强上体立体感 ----
        # 原理：真实人体中，锁骨下方/三角肌前方存在一条自然的阴影过渡带，
        #       由肩部凸起到胸部平坦的几何转折造成。在像素美术中，在肩部区域
        #       添加一条柔和的横向暗带（约身体宽度70%），可以：
        #       (1)暗示肩胛骨和三角肌的存在，让上半身不再是一个平面色块
        #       (2)与v0.3.29的服装高光带形成上下对比：肩线暗→胸部高光→腰部暗，
        #         建立起纵向上"暗-亮-暗"的节奏感
        #       (3)让角色看起来"有肩膀"而非"圆柱体上画了衣服"
        # 实现：在身体顶部8%-18%区域（肩线位置），画一条横向暗带，
        #       颜色比body_color深15-22单位，宽度约为身体渲染宽度的70%。
        #       暗带上下缘使用Bayer抖动过渡（与整体着色风格一致），避免硬边。
        #       左侧受光面稍浅（+5补偿），右侧稍深，保持光照方向一致性。
        _shoulder_band_y0 = body_top + int(body_draw_h * 0.08)
        _shoulder_band_y1 = body_top + int(body_draw_h * 0.18)
        _shoulder_band_hw = int(_contour_hw * 0.70)  # 肩线宽度=身体的70%
        if _shoulder_band_hw >= 2:
            _sb_dither = [
                [ 0,  8,  2, 10],
                [12,  4, 14,  6],
                [ 3, 11,  1,  9],
                [15,  7, 13,  5],
            ]
            for _sby in range(max(0, _shoulder_band_y0), min(H, _shoulder_band_y1 + 1)):
                _sb_local_y = _sby - body_top
                for _sbx in range(max(0, cx - _shoulder_band_hw), min(W, cx + _shoulder_band_hw)):
                    _sb_px = canvas[_sby][_sbx]
                    if _sb_px[3] == 0:
                        continue
                    # 横向衰减：中心暗、边缘正常（避免叠加到已有边缘暗化上）
                    _sb_hdist = abs(_sbx - cx) / max(1, _shoulder_band_hw)
                    if _sb_hdist > 0.85:
                        continue  # 太靠边缘，跳过
                    # 纵向衰减：带中心最深，上下渐淡（Bayer抖动平滑过渡）
                    _sb_vert_center = (_shoulder_band_y0 + _shoulder_band_y1) / 2.0
                    _sb_vdist = abs(_sby - _sb_vert_center) / max(1, (_shoulder_band_y1 - _shoulder_band_y0) / 2.0)
                    _sb_dt = _sb_dither[_sb_local_y % 4][_sbx % 4] / 16.0
                    if _sb_vdist > _sb_dt:
                        continue  # Bayer抖动过滤
                    # 基础暗化量：中心15，边缘渐减
                    _sb_darken = int(18 * (1.0 - _sb_hdist * 0.6))
                    # 光照一致性：左侧受光面稍浅
                    if _sbx < cx:
                        _sb_darken = max(5, _sb_darken - 5)
                    _r, _g, _b, _a = _sb_px
                    canvas[_sby][_sbx] = (
                        max(0, _r - _sb_darken),
                        max(0, _g - _sb_darken),
                        max(0, _b - _sb_darken + 2),  # 微偏蓝→阴影冷色调
                        _a
                    )
        
        # ---- v0.3.57a: 胸甲V形线 (Chest Plate V-Line) — 从肩到胸口的V形暗线暗示胸甲/胸肌结构 ----
        # 原理：在专业像素美术中，胸甲/胸肌区域常通过V形暗线来定义形状。
        #       经典RPG角色（如《最终幻想》战士、《塞尔达》林克）的躯干都有明显的
        #       胸肌分界线——从肩部两侧向胸骨中心汇聚成V字形状。
        #       这条线的视觉效果：
        #       (1)将躯干从一个"平面色块"变为"有结构的3D表面"
        #       (2)与v0.3.56a肩线暗带配合：肩线暗→V线分界→胸骨中线，形成完整上体结构
        #       (3)暗示角色穿着装甲/紧身衣，而非简单地"涂了一块颜色"
        #       (4)V形线条收敛点指向腰带扣(v0.3.56b)，形成视觉引导
        # 实现：在身体20%-42%高度区域（胸部），画两条对称的斜线：
        #   左线：从(cx - _contour_hw*0.75, body_top+20%h) → (cx, body_top+42%h)
        #   右线：从(cx + _contour_hw*0.75, body_top+20%h) → (cx, body_top+42%h)
        #   线条颜色=底色暗化8-16单位，宽度1px
        #   受光侧(左)线稍浅（暗化8-14），背光侧(右)线稍深（暗化12-18）
        _vline_top = body_top + int(body_draw_h * 0.20)
        _vline_bot = body_top + int(body_draw_h * 0.42)
        _vline_hw = max(2, int(_contour_hw * 0.75))
        if _vline_bot > _vline_top and _vline_hw >= 2:
            # 左V线（受光侧，稍浅）
            for _vly in range(max(0, _vline_top), min(H, _vline_bot + 1)):
                _vlt = (_vly - _vline_top) / max(1, _vline_bot - _vline_top)
                _vlx = int((cx - _vline_hw) + _vline_hw * _vlt)
                if 0 <= _vlx < W:
                    _vpx = canvas[_vly][_vlx]
                    if _vpx[3] > 0:
                        _vl_darken = int(8 + 6 * _vlt)
                        canvas[_vly][_vlx] = (
                            max(0, _vpx[0] - _vl_darken),
                            max(0, _vpx[1] - _vl_darken),
                            max(0, _vpx[2] - _vl_darken),
                            _vpx[3]
                        )
            # 右V线（背光侧，稍深）
            for _vly in range(max(0, _vline_top), min(H, _vline_bot + 1)):
                _vlt = (_vly - _vline_top) / max(1, _vline_bot - _vline_top)
                _vlx = int((cx + _vline_hw) - _vline_hw * _vlt)
                if 0 <= _vlx < W:
                    _vpx = canvas[_vly][_vlx]
                    if _vpx[3] > 0:
                        _vl_darken = int(12 + 6 * _vlt)
                        canvas[_vly][_vlx] = (
                            max(0, _vpx[0] - _vl_darken),
                            max(0, _vpx[1] - _vl_darken),
                            max(0, _vpx[2] - _vl_darken + 2),
                            _vpx[3]
                        )

        # ---- v0.3.56b: 腰带细节 (Belt Detail) — 腰部分色带+带扣高光增强装备层次 ----
        # 原理：在RPG/冒险类像素角色中，腰带(belt)是核心视觉元素之一：
        #       (1) 它标记了上体（胸/腹）和下体（腿/裙）的分界线
        #       (2) 带扣(buckle)是一个视觉锚点，常作为角色的标志性装饰
        #       (3) 腰带的存在让"穿衣服"的感觉从"涂了颜色"升级为"有装备"
        #       没有→有的区别类似于"一个色块"vs"一个角色"。
        # 实现：在身体50%-55%位置（腰部区域），画一条2px高的暗色横带，
        #       颜色比body_color深25-30单位，宽度等于身体渲染宽度。
        #       在正中央(cx)添加1-2px的accent_light色亮块作为带扣高光。
        #       左侧受光面的腰带稍浅（+4），保持光照一致性。
        _belt_y0 = body_top + int(body_draw_h * 0.50)
        _belt_y1 = body_top + int(body_draw_h * 0.55)
        _belt_hw = max(2, _contour_hw)
        if _belt_y1 > _belt_y0:
            for _bly in range(max(0, _belt_y0), min(H, _belt_y1 + 1)):
                for _blx in range(max(0, cx - _belt_hw), min(W, cx + _belt_hw)):
                    _bl_px = canvas[_bly][_blx]
                    if _bl_px[3] == 0:
                        continue
                    # 基础腰带色：比body_color深28
                    _bl_darken = 28
                    # 光照补偿：左侧受光面稍浅
                    if _blx < cx - 1:
                        _bl_darken = 24
                    _r, _g, _b, _a = _bl_px
                    canvas[_bly][_blx] = (
                        max(0, _r - _bl_darken),
                        max(0, _g - _bl_darken),
                        max(0, _b - _bl_darken + 3),  # 微偏蓝→皮革冷色调
                        _a
                    )
            # 带扣高光：腰带中央1-2px的accent_light色亮块
            _buckle_y = (_belt_y0 + _belt_y1) // 2
            _buckle_w = max(1, ps)
            for _bkx in range(max(0, cx - _buckle_w), min(W, cx + _buckle_w + 1)):
                for _bky in range(max(0, _buckle_y - 1), min(H, _buckle_y + 1)):
                    if canvas[_bky][_bkx][3] > 0:
                        # 带扣用accent_light色（金属光泽感）
                        canvas[_bky][_bkx] = (*accent_light, 255)
        
        # ---- v0.3.76: 呼吸亮度脉冲(Breath Luminance Pulse) — 吸气亮/呼气暗，与胸腔扩张同步 ----
        # 原理：真实呼吸中，胸腔扩张(吸气)时肺内气压降低、血氧增加，皮肤在吸气瞬间微充血发亮。
        #       同时，胸腔扩张使更多体表面积暴露在光照下，整体亮度确实会微增。
        #       这是微妙的"活着"信号——v0.3.8呼吸动画已有形状变化(body_scale_x)，
        #       但缺少光照响应：胸腔膨胀时应该微亮(更多面积受光)，收缩时微暗。
        #       综合效果：形状变化+亮度变化 → 呼吸从"机械缩放"升级为"有生理基础的呼吸"。
        #       迪士尼动画12原则中的"Slow In and Slow Out"：呼吸不是匀速线性运动，
        #       吸气阶段有个加速→减速过程，亮度脉冲也跟随这个节奏。
        # 实现：body_scale_x偏离1.0的量×40=亮度偏移(±2~3单位)。
        #       仅在idle/cast动画下生效（walk/run/jump/attack等剧烈运动时呼吸效果被运动模糊淹没）。
        #       使用暖色偏移(R+1,G+1,B-1)：吸气充血偏暖，呼气退血偏冷，模拟真实生理反应。
        if anim in ("idle", "cast"):
            _breath_scale = pose.get("body_scale_x", 1.0)
            _breath_delta = (_breath_scale - 1.0) * 40  # ±2.4亮度单位
            if abs(_breath_delta) > 0.5:
                _breath_boost = int(_breath_delta)
                for _bpy in range(max(0, body_top), min(H, body_bot)):
                    for _bpx in range(max(0, cx - _contour_hw - 1), min(W, cx + _contour_hw + 1)):
                        _bp_px = canvas[_bpy][_bpx]
                        if _bp_px[3] == 0:
                            continue
                        # 暖色亮度偏移：吸气+暖(偏红黄), 呼气-暖(偏蓝)
                        canvas[_bpy][_bpx] = (
                            min(255, max(0, _bp_px[0] + _breath_boost + 1)),  # R额外+1偏暖
                            min(255, max(0, _bp_px[1] + _breath_boost + 1)),  # G同步+1
                            min(255, max(0, _bp_px[2] + _breath_boost - 1)),  # B减1偏暖
                            _bp_px[3]
                        )
        
        # v0.3.27: 恢复原始cx — 腿部使用无偏移的中心保持地面锚定
        # （腿已经有自己的ldx/rdx偏移，不需要body_dx影响）
        if body_dx != 0:
            cx = _original_cx
        
        # ---- 绘制腿（v0.3.36: Bayer抖动渐变着色，匹配身体渲染品质） ----
        # v0.3.20 原有3区硬切换(0.3/0.7阈值)替换为与身体相同的Bayer有序抖动渐变
        # 让腿部与身体的渲染品质一致，消除明显的色带分界线
        leg_w = body_w // 3
        # Bayer 4x4 抖动矩阵（与身体渲染使用同一矩阵）
        _leg_dither = [
            [ 0,  8,  2, 10],
            [12,  4, 14,  6],
            [ 3, 11,  1,  9],
            [15,  7, 13,  5],
        ]
        
        def _leg_color_at(leg_t, local_y, local_x):
            """根据纵向位置leg_t和像素坐标计算腿部颜色（Bayer抖动渐变）"""
            dt = _leg_dither[local_y % 4][local_x % 4] / 16.0
            if leg_t < 0.15:
                return body_light
            elif leg_t < 0.35:
                # 高光→原色过渡带
                blend = (leg_t - 0.15) / 0.20
                return body_color if blend > dt else body_light
            elif leg_t < 0.60:
                return body_color
            elif leg_t < 0.80:
                # 原色→深色过渡带
                blend = (leg_t - 0.60) / 0.20
                return body_dark if blend > dt else body_color
            else:
                return body_dark
        
        # ---- v0.3.54: 腿部轮廓塑形(Leg Contour Taper) — 大腿→膝盖→脚踝锥形 ----
        # 原理：真实腿部轮廓从大腿（较宽，连接髋部）→膝盖（收窄）→小腿中部（略宽）→脚踝（最窄）。
        #       当前腿部是纯矩形，与身体v0.3.28的smoothstep轮廓塑形形成品质落差。
        #       像素美术中，腿部锥形是"自然感"的关键要素：矩形腿看起来像"柱子"，
        #       而锥形腿看起来像"有肌肉结构的肢体"。
        # 实现：使用与身体相同的Hermite smoothstep插值，分3区：
        #       0~40%(大腿): 保持全宽1.0（连接髋部需要完整宽度）
        #       40~70%(膝盖区): smoothstep收窄到0.75（膝盖处最细）
        #       70~100%(小腿→脚踝): 平滑回升到0.88（小腿肌肉）再微收到0.82（脚踝）
        _leg_taper_thigh = 1.0     # 大腿宽度比例
        _leg_taper_knee = 0.75     # 膝盖宽度比例（最窄）
        _leg_taper_calf = 0.88     # 小腿宽度比例
        _leg_taper_ankle = 0.82    # 脚踝宽度比例

        def _leg_contour_hw(leg_t, base_w):
            """根据纵向位置leg_t(0=顶,1=底)计算腿部半宽度"""
            if leg_t < 0.40:
                # 大腿区：保持全宽
                ratio = _leg_taper_thigh
            elif leg_t < 0.70:
                # 大腿→膝盖收窄：smoothstep过渡
                t = (leg_t - 0.40) / 0.30  # 0→1
                t = t * t * (3 - 2 * t)  # Hermite smoothstep
                ratio = _leg_taper_thigh + (_leg_taper_knee - _leg_taper_thigh) * t
            elif leg_t < 0.85:
                # 膝盖→小腿：微回升（小腿肌肉隆起）
                t = (leg_t - 0.70) / 0.15
                t = t * t * (3 - 2 * t)
                ratio = _leg_taper_knee + (_leg_taper_calf - _leg_taper_knee) * t
            else:
                # 小腿→脚踝：微收（脚踝是最细的部分）
                t = (leg_t - 0.85) / 0.15
                t = t * t * (3 - 2 * t)
                ratio = _leg_taper_calf + (_leg_taper_ankle - _leg_taper_calf) * t
            return max(1, int(base_w / 2 * ratio))

        # 左腿（带偏移 + Bayer抖动渐变 + v0.3.54轮廓塑形）
        ldx, ldy = pose["left_leg_dx"], pose["left_leg_dy"]
        _lleg_x0 = cx - body_w//2 + ldx
        _lleg_cx = _lleg_x0 + leg_w // 2  # 左腿中心X
        for y in range(leg_top + ldy, min(H, leg_top + ldy + leg_h)):
            leg_t = (y - leg_top - ldy) / max(1, leg_h - 1)  # 0=顶 1=底
            _ly = y - (leg_top + ldy)  # 腿部局部Y坐标
            # v0.3.54: 使用轮廓塑形计算实际渲染宽度
            _leg_hw = _leg_contour_hw(leg_t, leg_w)
            for x in range(max(0, _lleg_cx - _leg_hw), min(W, _lleg_cx + _leg_hw)):
                if 0 <= y < H:
                    _lx = x - _lleg_x0  # 腿部局部X坐标
                    leg_c = _leg_color_at(leg_t, _ly, _lx)
                    canvas[y][x] = (*leg_c, 255)
        # 右腿（带偏移 + Bayer抖动渐变 + v0.3.54轮廓塑形）
        rdx, rdy = pose["right_leg_dx"], pose["right_leg_dy"]
        _rleg_x0 = cx + body_w//2 - leg_w + rdx
        _rleg_cx = _rleg_x0 + leg_w // 2  # 右腿中心X
        for y in range(leg_top + rdy, min(H, leg_top + rdy + leg_h)):
            leg_t = (y - leg_top - rdy) / max(1, leg_h - 1)  # 0=顶 1=底
            _ly = y - (leg_top + rdy)  # 腿部局部Y坐标
            # v0.3.54: 使用轮廓塑形计算实际渲染宽度
            _leg_hw = _leg_contour_hw(leg_t, leg_w)
            for x in range(max(0, _rleg_cx - _leg_hw), min(W, _rleg_cx + _leg_hw)):
                if 0 <= y < H:
                    _lx = x - _rleg_x0  # 腿部局部X坐标
                    leg_c = _leg_color_at(leg_t, _ly, _lx)
                    canvas[y][x] = (*leg_c, 255)

        # ---- v0.3.54: 膝盖关节细节(Knee Joint Detail) — 膝盖位置微暗线+高光 ----
        # 原理：与v0.3.50领口分色线、v0.3.39袖口分色线统一设计语言：
        #       在肢体关节处添加1px微暗线暗示骨骼/关节结构。
        #       真实膝盖在弯曲时有明显的髌骨凸起和后方腘窝凹陷，
        #       像素美术用一条微暗线+上方微高光模拟此结构。
        # 实现：在腿部42%位置（膝盖高度）：
        #       - 膝盖线：1px水平暗线，受光侧+4亮度补偿
        #       - 膝盖上缘：1px微亮线 body_color+5，暗示髌骨凸起反射
        #       使用canvas已有的腿部像素（仅修改不透明像素），不绘制到透明区域
        _knee_t = 0.42  # 膝盖位置（腿部42%处）
        for _ks in ("left", "right"):
            if _ks == "left":
                _ks_dx, _ks_dy = ldx, ldy
                _ks_cx = _lleg_cx
            else:
                _ks_dx, _ks_dy = rdx, rdy
                _ks_cx = _rleg_cx
            # 计算膝盖Y位置
            _knee_y = leg_top + _ks_dy + int(leg_h * _knee_t)
            if 0 <= _knee_y < H and 0 <= _knee_y - 1 < H:
                _knee_hw = _leg_contour_hw(_knee_t, leg_w)
                # 膝盖上缘微高光（暗示髌骨凸起反射）
                _knee_hi_y = _knee_y - 1
                for _kx in range(max(0, _ks_cx - _knee_hw + 1), min(W, _ks_cx + _knee_hw - 1)):
                    _kp = canvas[_knee_hi_y][_kx]
                    if _kp[3] > 0:
                        # 微亮：受光侧(左)更亮+7，背光侧(右)微亮+3
                        _k_bright = 7 if _kx < _ks_cx else 3
                        canvas[_knee_hi_y][_kx] = (
                            min(255, int(_kp[0]) + _k_bright),
                            min(255, int(_kp[1]) + _k_bright),
                            min(255, int(_kp[2]) + _k_bright),
                            _kp[3]
                        )
                # 膝盖线（微暗，暗示关节凹陷）
                for _kx in range(max(0, _ks_cx - _knee_hw + 1), min(W, _ks_cx + _knee_hw - 1)):
                    _kp = canvas[_knee_y][_kx]
                    if _kp[3] > 0:
                        # 受光侧补偿+4（左侧亮，有光泽感），背光侧更深-2
                        _k_dark = -10 if _kx < _ks_cx else -14
                        canvas[_knee_y][_kx] = (
                            max(0, min(255, int(_kp[0]) + _k_dark + (4 if _kx < _ks_cx else 0))),
                            max(0, min(255, int(_kp[1]) + _k_dark + (2 if _kx < _ks_cx else 0))),
                            max(0, min(255, int(_kp[2]) + _k_dark)),
                            _kp[3]
                        )
        
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

        # v0.3.44: 鞋子抖动渐变着色（Shoe Bayer Dithered Gradient）
        # 与 body/legs/arms 的 Bayer 4×4 抖动矩阵一致
        # 将鞋子从硬三层渐变（highlight/color/sole）升级为抖动平滑渐变
        # 过渡带：0.25~0.45(高光→原色), 0.65~0.85(原色→鞋底)
        _shoe_bayer = [
            [ 0,  8,  2, 10],
            [12,  4, 14,  6],
            [ 3, 11,  1,  9],
            [15,  7, 13,  5],
        ]

        def _shoe_dithered_color(boot_t, y, x):
            """根据垂直位置和 Bayer 抖动计算鞋子颜色"""
            if boot_t < 0.25:
                return shoe_highlight
            elif boot_t < 0.45:
                # 高光→原色过渡带
                blend = (boot_t - 0.25) / 0.2
                threshold = _shoe_bayer[y % 4][x % 4] / 16.0
                return shoe_color if blend > threshold else shoe_highlight
            elif boot_t < 0.65:
                return shoe_color
            elif boot_t < 0.85:
                # 原色→鞋底过渡带
                blend = (boot_t - 0.65) / 0.2
                threshold = _shoe_bayer[y % 4][x % 4] / 16.0
                return shoe_sole if blend > threshold else shoe_color
            else:
                return shoe_sole

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
                            # v0.3.44: 抖动渐变替代硬三层渐变
                            sc = _shoe_dithered_color(boot_t, y, x)
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
                        # v0.3.44: 抖动渐变替代硬三层渐变
                        sc = _shoe_dithered_color(boot_t, y, x)
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
                        # v0.3.44: 抖动渐变替代硬三层渐变
                        sc = _shoe_dithered_color(boot_t, y, x)
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
                        # v0.3.44: 抖动渐变替代硬三层渐变
                        sc = _shoe_dithered_color(boot_t, y, x)
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
                        # v0.3.44: 抖动渐变替代硬三层渐变
                        sc = _shoe_dithered_color(boot_t, y, x)
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
                        # v0.3.44: 抖动渐变替代硬两层渐变
                        sc = _shoe_dithered_color(boot_t, y, x)
                        canvas[y][x] = (*sc, 255)
        
        # v0.3.27: 手臂恢复躯干偏移cx — 手臂跟随上半身横移
        if body_dx != 0:
            cx = torso_cx
        
        # ---- 绘制手臂（v0.3.38: Bayer抖动渐变着色，匹配身体和腿部渲染品质） ----
        # v0.3.19 原有3区硬切换(0.3/0.7阈值)替换为Bayer有序抖动渐变
        # 与v0.3.36腿部升级和身体渲染使用相同的过渡算法，消除手臂色带分界线
        arm_w = max(ps * 2, int(leg_w * arm_ratio))
        arm_top_y = body_top + ps
        arm_bot_y = body_bot - ps
        arm_h = max(1, arm_bot_y - arm_top_y)
        # Bayer 4x4 抖动矩阵（与身体、腿部使用同一矩阵）
        _arm_dither = [
            [ 0,  8,  2, 10],
            [12,  4, 14,  6],
            [ 3, 11,  1,  9],
            [15,  7, 13,  5],
        ]
        def _arm_color_at(arm_t, local_y, local_x):
            """根据纵向位置arm_t和像素坐标计算手臂颜色（Bayer抖动渐变）"""
            dt = _arm_dither[local_y % 4][local_x % 4] / 16.0
            if arm_t < 0.15:
                return skin_light
            elif arm_t < 0.35:
                # 高光→原色过渡带
                blend = (arm_t - 0.15) / 0.20
                return skin if blend > dt else skin_light
            elif arm_t < 0.60:
                return skin
            elif arm_t < 0.80:
                # 原色→深色过渡带
                blend = (arm_t - 0.60) / 0.20
                return skin_dark if blend > dt else skin
            else:
                return skin_dark
        # 左臂（带偏移 + Bayer抖动渐变：顶部受光偏亮，底部阴影偏暗）
        ladx, lady = pose["left_arm_dx"], pose["left_arm_dy"]
        _larm_x0 = cx - body_w//2 - arm_w + ladx
        for y in range(arm_top_y + lady, min(H, arm_bot_y + lady)):
            arm_t = (y - arm_top_y - lady) / max(1, arm_h - 1)  # 0=顶 1=底
            _ay = y - (arm_top_y + lady)  # 手臂局部Y坐标
            for x in range(max(0, _larm_x0), min(W, _larm_x0 + arm_w)):
                if 0 <= y < H:
                    _ax = x - _larm_x0  # 手臂局部X坐标
                    arm_c = _arm_color_at(arm_t, _ay, _ax)
                    canvas[y][x] = (*arm_c, 255)
        # 右臂（带偏移 + Bayer抖动渐变，武器侧）
        radx, rady = pose["right_arm_dx"], pose["right_arm_dy"]
        _rarm_x0 = cx + body_w//2 + radx
        for y in range(arm_top_y + rady, min(H, arm_bot_y + rady)):
            arm_t = (y - arm_top_y - rady) / max(1, arm_h - 1)  # 0=顶 1=底
            _ay = y - (arm_top_y + rady)  # 手臂局部Y坐标
            for x in range(max(0, _rarm_x0), min(W, _rarm_x0 + arm_w)):
                if 0 <= y < H:
                    _ax = x - _rarm_x0  # 手臂局部X坐标
                    arm_c = _arm_color_at(arm_t, _ay, _ax)
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
        
        # ---- v0.3.39: 袖口分色线(Sleeve Edge Line) — 衣物与皮肤交界处的内部分色线 ----
        # 原理：像素美术核心技法"内部分色线(inner separation line)"：
        #       在两种不同材质(布料/皮肤)交界处画1px深色线，让部件分离清晰可读。
        #       没有这条线，手臂看起来像"涂在"身体上的色块；有了这条线，手臂看起来像
        #       "从袖子里伸出来的"，有明显的衣物→皮肤材质切换感。
        #       这在专业像素美术中是"必须做"的细节处理（reference: MortMort, slynyrd）。
        # 实现：在手臂顶部行(arm_top_y)画1px深色横线，颜色比肤色深35-40单位，
        #       宽度等于手臂宽度。仅覆盖手臂区域的不透明像素。
        _sleeve_line_color = (max(0, skin[0] - 35), max(0, skin[1] - 30), max(0, skin[2] - 25))
        # 左臂袖口线
        _sl_y_l = arm_top_y + lady
        if 0 <= _sl_y_l < H:
            for _slx in range(max(0, _larm_x0), min(W, _larm_x0 + arm_w)):
                if canvas[_sl_y_l][_slx][3] > 0:
                    canvas[_sl_y_l][_slx] = (*_sleeve_line_color, 255)
        # 右臂袖口线
        _sl_y_r = arm_top_y + rady
        if 0 <= _sl_y_r < H:
            for _slx in range(max(0, _rarm_x0), min(W, _rarm_x0 + arm_w)):
                if canvas[_sl_y_r][_slx][3] > 0:
                    canvas[_sl_y_r][_slx] = (*_sleeve_line_color, 255)
        
        # ---- v0.3.42: 手臂椭球法线着色（Arm Ellipsoid Normal Shading） ----
        # 原理：与身体v0.3.34椭球法线着色相同的3D体积感技术，应用于手臂。
        #       手臂是细长的椭圆柱体，用椭球近似。法线·光源方向→横向明暗变化。
        #       光源从左上方照射，因此手臂左侧偏亮、右侧偏暗，与身体的光照一致。
        #       此前手臂只有Bayer抖动纵向渐变（v0.3.38），缺少横向3D立体感，
        #       使手臂看起来比身体"扁平"。添加椭球法线后，手臂与身体的3D感统一。
        # 实现：遍历左右手臂区域的像素，计算椭球法线与光源方向的点积，
        #       微调亮度（±6），不影响已有的Bayer纵向渐变。
        _arm_nx_factor = 1.0 / max(1, arm_w // 2)   # 手臂横向归一化（窄椭球）
        _arm_ny_factor = 1.0 / max(1, arm_h // 2)    # 手臂纵向归一化
        _arm_brightness = 6  # 手臂比身体细，亮度调节幅度略小（身体是±8）
        # 左臂椭球法线着色
        for y in range(max(0, arm_top_y + lady), min(H, arm_bot_y + lady)):
            for x in range(max(0, _larm_x0), min(W, _larm_x0 + arm_w)):
                r, g, b, a = canvas[y][x]
                if a == 0:
                    continue
                adx = x - (_larm_x0 + arm_w / 2)  # 手臂中心x
                ady = y - (arm_top_y + lady + arm_h / 2)  # 手臂中心y
                nx = adx * _arm_nx_factor
                ny = ady * _arm_ny_factor
                n_len = (nx*nx + ny*ny) ** 0.5
                if n_len > 1.0:
                    continue  # 椭球外不处理
                if n_len < 0.01:
                    nx_n, ny_n = 0.0, -1.0
                else:
                    nx_n = nx / n_len
                    ny_n = ny / n_len
                dot = nx_n * _blx + ny_n * _bly  # 复用身体的光源方向
                brightness = int(dot * _arm_brightness)
                if brightness != 0:
                    canvas[y][x] = (
                        min(255, max(0, r + brightness)),
                        min(255, max(0, g + brightness)),
                        min(255, max(0, b + brightness)),
                        a
                    )
        # 右臂椭球法线着色
        for y in range(max(0, arm_top_y + rady), min(H, arm_bot_y + rady)):
            for x in range(max(0, _rarm_x0), min(W, _rarm_x0 + arm_w)):
                r, g, b, a = canvas[y][x]
                if a == 0:
                    continue
                adx = x - (_rarm_x0 + arm_w / 2)
                ady = y - (arm_top_y + rady + arm_h / 2)
                nx = adx * _arm_nx_factor
                ny = ady * _arm_ny_factor
                n_len = (nx*nx + ny*ny) ** 0.5
                if n_len > 1.0:
                    continue
                if n_len < 0.01:
                    nx_n, ny_n = 0.0, -1.0
                else:
                    nx_n = nx / n_len
                    ny_n = ny / n_len
                dot = nx_n * _blx + ny_n * _bly
                brightness = int(dot * _arm_brightness)
                if brightness != 0:
                    canvas[y][x] = (
                        min(255, max(0, r + brightness)),
                        min(255, max(0, g + brightness)),
                        min(255, max(0, b + brightness)),
                        a
                    )
        
        # ---- v0.3.55a: 肘关节细节(Elbow Joint Detail) — 手臂中段关节结构线增强 ----
        # 原理：与v0.3.54膝关节细节同理，手臂在肘部处有关节弯曲，
        #       在手臂中段(约45%位置)添加1px高光线+1px暗线可以暗示肘关节结构，
        #       让手臂看起来不只是"一根色条"而是有关节弯曲可能的肢体。
        #       在像素美术中，即使手臂没有实际弯曲，暗示关节位置也能提升可读性。
        # 实现：在手臂纵向约45%位置（肘部），画1px暗线增强关节深度感，
        #       在暗线上方1px画1px高光线暗示骨骼突出。
        _elbow_t = 0.45  # 肘关节相对位置（上臂:前臂 ≈ 45:55）
        _elbow_highlight_color = (min(255, skin[0] + 12), min(255, skin[1] + 10), min(255, skin[2] + 8))
        _elbow_shadow_color = (max(0, skin[0] - 18), max(0, skin[1] - 16), max(0, skin[2] - 14))
        # 左臂肘关节
        _le_y = int(arm_top_y + lady + arm_h * _elbow_t)
        if 0 <= _le_y < H:
            for _ex in range(max(0, _larm_x0), min(W, _larm_x0 + arm_w)):
                if canvas[_le_y][_ex][3] > 0:
                    # 高光线（肘上1px）
                    if _le_y - 1 >= 0 and canvas[_le_y - 1][_ex][3] > 0:
                        canvas[_le_y - 1][_ex] = (*_elbow_highlight_color, 255)
                    # 暗线（肘关节位置）
                    canvas[_le_y][_ex] = (*_elbow_shadow_color, 255)
        # 右臂肘关节
        _re_y = int(arm_top_y + rady + arm_h * _elbow_t)
        if 0 <= _re_y < H:
            for _ex in range(max(0, _rarm_x0), min(W, _rarm_x0 + arm_w)):
                if canvas[_re_y][_ex][3] > 0:
                    if _re_y - 1 >= 0 and canvas[_re_y - 1][_ex][3] > 0:
                        canvas[_re_y - 1][_ex] = (*_elbow_highlight_color, 255)
                    canvas[_re_y][_ex] = (*_elbow_shadow_color, 255)

        # ---- v0.3.76: 手部镜面高光点(Hand Specular Highlight) — 手掌椭球顶部1px镜面反射 ----
        # 原理：手掌是用skin_light色填充的椭球(v0.3.24)，但椭球顶部(朝光源侧)应该有
        #       一个小镜面高光点——这是球面/椭球面在光源直射方向上的菲涅尔反射集中点。
        #       在像素美术中，1px的纯白/近白高光点就能把"flat色块"变成"3D球体"，
        #       因为人类视觉系统对高光点极其敏感：高光位置暗示曲面朝向和光源方向。
        #       参考： MortMort教程"Pixel Art Shading Guide"——"One pixel of highlight
        #       can sell the 3D form more than 10 pixels of gradient."
        # 实现：在每只手的椭球顶部偏左1/3处（光源从左上方照射）放置1px高光点。
        #       颜色为skin_light再提亮25单位但不超过255。仅在手掌椭球内有效像素上添加。
        #       高光位置选在(hand_x + hand_w*1//3, hand_y)，即椭球顶部偏左，
        #       与全局光源方向(-0.5, -0.7)一致。
        _hand_spec_color = (min(255, skin_light[0] + 25), min(255, skin_light[1] + 25), min(255, skin_light[2] + 20))
        # 左手镜面高光 — 椭球顶部偏左
        _lsp_x = lh_x + max(0, hand_w * 1 // 3)
        _lsp_y = lh_y
        if 0 <= _lsp_y < H and 0 <= _lsp_x < W and canvas[_lsp_y][_lsp_x][3] > 0:
            canvas[_lsp_y][_lsp_x] = (*_hand_spec_color, 255)
        # 右手镜面高光 — 椭球顶部偏左
        _rsp_x = rh_x + max(0, hand_w * 1 // 3)
        _rsp_y = rh_y
        if 0 <= _rsp_y < H and 0 <= _rsp_x < W and canvas[_rsp_y][_rsp_x][3] > 0:
            canvas[_rsp_y][_rsp_x] = (*_hand_spec_color, 255)

        # ---- 类型专属配件 ----
        # 战士：盾牌（v0.3.74: 金属法线着色升级 Metal Normal Shading）
        # 将扁平纯色盾牌升级为椭球法线光照+金属镜面高光+边缘高光环+深色边框
        # 原理：与v0.3.34身体椭球法线着色相同技术，盾牌近似为圆形平面，
        #       法线点积光源方向(-0.5,-0.7)产生左上亮右下暗的3D凸面效果，
        #       加上边缘高光和中心十字纹饰的高光点模拟金属抛光反射
        if type_cfg.get("has_shield"):
            shield_x = cx - body_w//2 - arm_w - ps*2
            shield_cy = (body_top + body_bot) // 2
            shield_r = max(ps*2, arm_w + ps)
            # v0.3.74: 预计算盾牌金属色阶
            _shld_metal = _cool_shift(accent, 12)  # 偏冷金属质感
            _shld_highlight = _warm_shift(accent, 25)  # 暖色高光
            _shld_dark = _cool_shift(accent, 20)  # 冷色暗面
            _shld_spec = (min(255, accent[0]+60), min(255, accent[1]+55), min(255, accent[2]+45))  # 镜面反射点
            for y in range(max(0, shield_cy - shield_r), min(H, shield_cy + shield_r)):
                for x in range(max(0, shield_x - shield_r), min(W, shield_x + shield_r)):
                    sdx, sdy = x - shield_x, y - shield_cy
                    dist_sq = sdx*sdx + sdy*sdy
                    if dist_sq <= shield_r*shield_r:
                        # v0.3.74: 椭球法线光照（与v0.3.34/v0.3.21b相同的左上光源）
                        _s_nx = sdx / max(1, shield_r)
                        _s_ny = sdy / max(1, shield_r)
                        _s_dot = _s_nx * (-0.5) + _s_ny * (-0.7)  # 光源方向(-0.5,-0.7)
                        _s_dot = max(-1.0, min(1.0, _s_dot))
                        # 根据法线点积选择色阶：亮面/中间面/暗面
                        if _s_dot > 0.3:
                            _sc = _shld_highlight  # 左上受光面
                        elif _s_dot > -0.2:
                            _sc = _shld_metal  # 中间面（金属色）
                        else:
                            _sc = _shld_dark  # 右下暗面
                        canvas[y][x] = (*_sc, 255)
                        # 盾牌十字纹饰（高亮色）
                        if abs(sdx) <= ps or abs(sdy) <= ps:
                            canvas[y][x] = (min(255, _sc[0]+40), min(255, _sc[1]+35), min(255, _sc[2]+30), 255)
                        # v0.3.74: 中心镜面高光点（仅左上象限）
                        if abs(sdx) <= ps and sdy <= 0 and abs(sdy) <= ps:
                            canvas[y][x] = (*_shld_spec, 255)
                        # v0.3.74: 边缘高光环（距边缘1px的轮廓高光，模拟金属边缘反光）
                        _s_edge_dist = shield_r - int(dist_sq**0.5)
                        if _s_edge_dist <= 1 and _s_dot > 0:
                            _s_rim = min(255, _sc[0]+20), min(255, _sc[1]+18), min(255, _sc[2]+15)
                            canvas[y][x] = (*_s_rim, 255)

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
                # v0.3.41: 腰带金属扣渲染（Metallic Buckle）— 模拟黄铜/钢铁扣环的金属反射
                # 原理：真实腰带扣是弧形金属片，光照时中心有明亮锐利的镜面反射点，
                #       边缘因弧面弯曲过渡到暗色。金属扣与布料腰带的视觉对比
                #       是区分"装备"与"衣物"的关键视觉线索。
                # 实现：腰带带身用accent_dark，扣环外框用accent，内部用accent_light，
                #       中心1px添加暖白镜面点(max+40,+30,+20)模拟金属锐反射。
                belt_y = body_top + body_h * 2 // 3
                for x in range(max(0, cx - body_draw_w//2 - 1), min(W, cx + body_draw_w//2 + 1)):
                    for dy2 in range(max(0, ps)):
                        by = belt_y + dy2
                        if 0 <= by < H:
                            canvas[by][x] = (*accent_dark, 255)
                # 腰带金属扣 — 外框
                buckle_w = max(ps + 1, 3)
                buckle_h = max(ps, 2)
                buckle_y = belt_y
                for dy2 in range(buckle_h):
                    for dx2 in range(-buckle_w, buckle_w + 1):
                        bx = cx + dx2
                        bby = buckle_y + dy2
                        if 0 <= bx < W and 0 <= bby < H:
                            # 扣环边缘（外1px用accent色，模拟弧面暗边）
                            if abs(dx2) >= buckle_w - 1 or dy2 == 0 or dy2 == buckle_h - 1:
                                canvas[bby][bx] = (*accent, 255)
                            else:
                                canvas[bby][bx] = (*accent_light, 255)
                # 扣环中心镜面高光点（金属锐反射）
                if buckle_h >= 2:
                    _sp_y = buckle_y + buckle_h // 2
                    _sp_x = cx - 1  # 偏左（受光侧），与全局光源方向一致
                    if 0 <= _sp_y < H and 0 <= _sp_x < W:
                        canvas[_sp_y][_sp_x] = (
                            min(255, accent_light[0] + 40),
                            min(255, accent_light[1] + 30),
                            min(255, accent_light[2] + 20), 255)

            elif acc == "shoulder_pads":
                # v0.3.41: 肩甲金属高光（Metallic Specular）— 模拟弧形金属板的法线高光反射
                # 原理：金属表面的高光比布料更锐利、更亮，且有明显的明暗分界线。
                #       护甲肩片通常是弧面，光照时形成经典的"金属高光带"：
                #       受光侧（左上）有窄而亮的镜面反射带，背光侧（右下）快速过渡到暗色。
                #       与布料的v0.3.29 Clothing Specular Band不同：金属高光更窄更亮更锐利。
                # 实现：将肩甲分为4个渐变区域（高光带/亮面/中间面/暗面），
                #       用对角线位置(normal_t)决定颜色，模拟弧面法线变化。
                #       额外在高光带中心画1px白色镜面点模拟金属锐反射。
                pad_w = max(ps*2, arm_w)
                pad_h = max(ps*2, body_h // 5)
                pad_y = body_top
                # 金属高光色阶（比布料的高光更亮更暖）
                _metal_bright = (min(255, accent_light[0] + 18), min(255, accent_light[1] + 12), min(255, accent_light[2] + 5))  # 金属亮面
                _metal_dark = (max(0, accent_dark[0] - 10), max(0, accent_dark[1] - 8), max(0, accent_dark[2] - 5))  # 金属暗面
                # 左肩甲
                for y in range(pad_y, min(H, pad_y + pad_h)):
                    for x in range(max(0, cx - body_draw_w//2 - pad_w), min(W, cx - body_draw_w//2)):
                        # 计算该像素在肩甲上的归一化位置 (0~1, 0~1)
                        _px_t = (y - pad_y) / max(1, pad_h - 1)  # 纵向: 0=顶 1=底
                        _py_t = (x - (cx - body_draw_w//2 - pad_w)) / max(1, pad_w - 1)  # 横向: 0=左 1=右
                        # 法线方向模拟：对角线梯度（左上亮，右下暗），模拟左上方光源
                        _normal_t = (_px_t + (1.0 - _py_t)) / 2.0  # 0=最亮(左上) 1=最暗(右下)
                        if _normal_t < 0.25:
                            # 高光带：窄而亮的镜面反射区域
                            canvas[y][x] = (*_metal_bright, 255)
                            # 高光带中心的锐反射点（最亮1px，模拟金属锐高光）
                            if _normal_t < 0.12:
                                canvas[y][x] = (min(255, _metal_bright[0] + 25), min(255, _metal_bright[1] + 20), min(255, _metal_bright[2] + 15), 255)
                        elif _normal_t < 0.45:
                            # 亮面
                            canvas[y][x] = (*accent_light, 255)
                        elif _normal_t < 0.7:
                            # 中间面
                            canvas[y][x] = (*accent, 255)
                        else:
                            # 暗面
                            canvas[y][x] = (*_metal_dark, 255)
                # 右肩甲（镜像：右上亮，左下暗）
                for y in range(pad_y, min(H, pad_y + pad_h)):
                    for x in range(max(0, cx + body_draw_w//2), min(W, cx + body_draw_w//2 + pad_w)):
                        _px_t = (y - pad_y) / max(1, pad_h - 1)
                        _py_t = (x - (cx + body_draw_w//2)) / max(1, pad_w - 1)
                        # 右肩：右上亮，左下暗（光源从左上方照射）
                        _normal_t = (_px_t + _py_t) / 2.0
                        if _normal_t < 0.25:
                            canvas[y][x] = (*_metal_bright, 255)
                            if _normal_t < 0.12:
                                canvas[y][x] = (min(255, _metal_bright[0] + 25), min(255, _metal_bright[1] + 20), min(255, _metal_bright[2] + 15), 255)
                        elif _normal_t < 0.45:
                            canvas[y][x] = (*accent_light, 255)
                        elif _normal_t < 0.7:
                            canvas[y][x] = (*accent, 255)
                        else:
                            canvas[y][x] = (*_metal_dark, 255)

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

            elif acc == "wrist_guards":
                # v0.3.35: 护腕 — 手腕处的环形装饰带，增加战斗类角色的武装感
                # 护腕绘制在手臂末端附近（手部上方），使用accent色+金属扣
                guard_h = max(ps, 2)  # 护腕高度
                guard_color = (*accent_dark, 255)
                guard_highlight = (*accent_light, 255)
                ladx = pose.get("left_arm_dx", 0)
                lady = pose.get("left_arm_dy", 0)
                radx2 = pose.get("right_arm_dx", 0)
                rady2 = pose.get("right_arm_dy", 0)
                # 左臂护腕（手臂中间偏下位置）
                lg_x = cx - body_w//2 - arm_w + ladx
                lg_y = body_top + arm_h * 2 // 3 + lady
                for dy2 in range(guard_h):
                    gy = lg_y + dy2
                    for dx2 in range(arm_w + ps):
                        gx = lg_x + dx2
                        if 0 <= gx < W and 0 <= gy < H:
                            canvas[gy][gx] = guard_color
                # 左臂护腕金属扣（中心亮点）
                buckle_x = lg_x + arm_w // 2
                buckle_y = lg_y + guard_h // 2
                if 0 <= buckle_x < W and 0 <= buckle_y < H:
                    canvas[buckle_y][buckle_x] = guard_highlight
                # 右臂护腕
                rg_x = cx + body_w//2 + radx2
                rg_y = body_top + arm_h * 2 // 3 + rady2
                for dy2 in range(guard_h):
                    gy = rg_y + dy2
                    for dx2 in range(arm_w + ps):
                        gx = rg_x + dx2
                        if 0 <= gx < W and 0 <= gy < H:
                            canvas[gy][gx] = guard_color
                # 右臂护腕金属扣
                buckle_x2 = rg_x + arm_w // 2
                buckle_y2 = rg_y + guard_h // 2
                if 0 <= buckle_x2 < W and 0 <= buckle_y2 < H:
                    canvas[buckle_y2][buckle_x2] = guard_highlight

            elif acc == "cloak":
                # v0.3.39: 斗篷 — 从肩部两侧垂落的宽松外袍，增强角色戏剧感
                # 设计：比cape更宽，两侧对称，从肩部延伸到膝盖，带波浪褶皱
                # v0.3.48: 斗篷物理次级运动 — 运动时斗篷反向飘动，模拟空气阻力
                cloak_color = (*accent_dark, 255)
                cloak_highlight = (
                    min(255, accent_dark[0] + 18),
                    min(255, accent_dark[1] + 14),
                    min(255, accent_dark[2] + 10), 255)
                cloak_shadow = (
                    max(0, accent_dark[0] - 20),
                    max(0, accent_dark[1] - 18),
                    max(0, accent_dark[2] - 15), 255)
                cloak_w = max(ps * 2, arm_w + ps)  # 斗篷宽度略宽于手臂
                cloak_top = body_top - ps  # 从肩部开始
                cloak_bot = min(H, body_bot + leg_h // 2)  # 延伸到膝盖
                # v0.3.48: 斗篷风力偏移 — body_dx反方向（惯性），越往下越大
                _cloak_wind = -body_dx if body_dx != 0 else 0
                # 左侧斗篷（身体左侧外沿）
                for y in range(max(0, cloak_top), cloak_bot):
                    # v0.3.48: 斗篷底部受风力更大（距离加权）
                    _cloak_dist = min(1.0, (y - cloak_top) / max(1, cloak_bot - cloak_top))
                    _cloak_sway = int(_cloak_wind * _cloak_dist * 1.5)
                    # 波浪褶皱效果：宽度随y轴正弦波动（v0.3.48: 加入frame_idx动态飘动）
                    wave = int(math.sin((y - cloak_top) * 0.25 + (rng.seed % 100) * 0.1 + frame_idx * 0.15) * ps)
                    left_x = max(0, cx - body_w // 2 - cloak_w + wave + _cloak_sway)
                    right_x = max(0, cx - body_w // 2 - ps // 2 + wave + _cloak_sway)
                    for x in range(left_x, min(W, right_x)):
                        if 0 <= x < W and 0 <= y < H and canvas[y][x][3] == 0:
                            # 渐变着色：中心亮，边缘暗
                            dist_from_edge = x - left_x
                            total_w = right_x - left_x
                            if total_w > 0 and dist_from_edge > total_w * 0.6:
                                canvas[y][x] = cloak_highlight
                            elif total_w > 0 and dist_from_edge < total_w * 0.25:
                                canvas[y][x] = cloak_shadow
                            else:
                                canvas[y][x] = cloak_color
                # 右侧斗篷（身体右侧外沿）
                for y in range(max(0, cloak_top), cloak_bot):
                    _cloak_dist = min(1.0, (y - cloak_top) / max(1, cloak_bot - cloak_top))
                    _cloak_sway = int(_cloak_wind * _cloak_dist * 1.5)
                    wave = int(math.sin((y - cloak_top) * 0.25 + (rng.seed % 100) * 0.1 + 1.5 + frame_idx * 0.15) * ps)
                    left_x2 = min(W, cx + body_w // 2 + ps // 2 + wave + _cloak_sway)
                    right_x2 = min(W, cx + body_w // 2 + cloak_w + wave + _cloak_sway)
                    for x in range(max(0, left_x2), min(W, right_x2)):
                        if 0 <= x < W and 0 <= y < H and canvas[y][x][3] == 0:
                            dist_from_edge = right_x2 - x
                            total_w = right_x2 - left_x2
                            if total_w > 0 and dist_from_edge > total_w * 0.6:
                                canvas[y][x] = cloak_highlight
                            elif total_w > 0 and dist_from_edge < total_w * 0.25:
                                canvas[y][x] = cloak_shadow
                            else:
                                canvas[y][x] = cloak_color
                # 斗篷领扣（颈部前方的装饰扣环）
                clasp_y = cloak_top + ps
                clasp_x = cx
                if 0 <= clasp_x < W and 0 <= clasp_y < H:
                    canvas[clasp_y][clasp_x] = (*accent_light, 255)

            elif acc == "potion_bottles":
                # v0.3.66: 腰带药水瓶(Belt Potion Bottles) — 法师/治疗师/诗人腰间的小药水瓶
                # 原理：奇幻角色经常在腰带上挂着彩色药水瓶，这是角色职业辨识的经典视觉元素。
                #       药水瓶用鲜艳的宝石色调（红/蓝/绿）在暗色腰带/衣物上形成视觉焦点，
                #       同时暗示角色的炼金/治疗/魔法能力。
                # 实现：在腰带位置右侧画2-3个微小瓶形（圆底+细颈+瓶塞），用预定义药水色，
                #       瓶身用该色+高光+暗面3级渐变，瓶塞用棕色。随seed决定瓶数和颜色。
                _pot_y = body_top + body_h * 2 // 3 + max(1, ps // 2)  # 瓶子起始Y（腰带下方）
                _pot_colors = [
                    (180, 50, 50),   # 红色药水（生命）
                    (50, 80, 180),   # 蓝色药水（魔力）
                    (50, 160, 70),   # 绿色药水（解毒）
                ]
                # 用seed选择药水颜色和数量
                _pot_seed = rng.seed if hasattr(rng, 'seed') else 0
                _n_pots = 2 + (_pot_seed % 2)  # 2或3个瓶子
                _bottle_w = max(ps, 2)  # 瓶身宽度
                _bottle_h = max(ps + 1, 3)  # 瓶身高度
                _neck_h = max(1, ps // 2)  # 瓶颈高度
                _bottle_gap = _bottle_w + 1  # 瓶子间距
                for i in range(_n_pots):
                    pot_color = _pot_colors[(i + _pot_seed // 7) % len(_pot_colors)]
                    pot_highlight = (min(255, pot_color[0] + 50), min(255, pot_color[1] + 50), min(255, pot_color[2] + 50))
                    pot_shadow = (max(0, pot_color[0] - 40), max(0, pot_color[1] - 40), max(0, pot_color[2] - 40))
                    # 瓶子X位置：身体右侧，依次排列
                    bx = cx + body_draw_w // 2 + ps + i * _bottle_gap
                    # 瓶颈（上方细窄部分）
                    for dy2 in range(_neck_h):
                        ny = _pot_y - _neck_h + dy2
                        if 0 <= ny < H and 0 <= bx < W:
                            canvas[ny][bx] = (*pot_shadow, 255)
                    # 瓶塞（瓶颈顶部1px棕色）
                    cork_y = _pot_y - _neck_h - 1
                    if 0 <= cork_y < H and 0 <= bx < W:
                        canvas[cork_y][bx] = (139, 90, 43, 255)  # 棕色木塞
                    # 瓶身（圆底矩形）
                    for dy2 in range(_bottle_h):
                        by = _pot_y + dy2
                        for dx2 in range(_bottle_w):
                            bxx = bx + dx2
                            if 0 <= bxx < W and 0 <= by < H:
                                # 3级渐变：左侧暗面，中间基色，右侧高光
                                if dx2 == 0:
                                    canvas[by][bxx] = (*pot_shadow, 255)
                                elif dx2 == _bottle_w - 1:
                                    canvas[by][bxx] = (*pot_highlight, 255)
                                else:
                                    canvas[by][bxx] = (*pot_color, 255)
                    # 瓶底圆弧（底行中间向左右扩展1px）
                    bot_y = _pot_y + _bottle_h
                    if 0 <= bot_y < H:
                        for dx2 in range(-1, _bottle_w + 1):
                            bxx = bx + dx2
                            if 0 <= bxx < W:
                                canvas[bot_y][bxx] = (*pot_shadow, 255)

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
            
            # ---- v0.3.32: 武器渲染升级 ----
            if weapon == "sword":
                # 剑刃渐变：尖端明亮(240,240,250)→基底暗淡(150,150,165)
                # 剑脊(中脊): 比刃色更亮的高光线
                # 剑柄: 棕色护手 + accent色柄缠绕
                x0, y0 = weapon_base_x, weapon_base_y
                x1, y1 = tip_x, min(H-1, tip_y)
                dx_w = abs(x1 - x0)
                dy_w = abs(y1 - y0)
                sx = 1 if x0 < x1 else -1
                sy = 1 if y0 < y1 else -1
                err = dx_w - dy_w
                px_count = 0
                blade_total = max(1, abs(x1 - weapon_base_x) + abs(y1 - weapon_base_y))
                while True:
                    if 0 <= y0 < H and 0 <= x0 < W:
                        # 渐变进度: 0=base(暗), 1=tip(亮)
                        progress = px_count / max(1, blade_total)
                        # 剑刃色: 暗端(150,150,165) → 亮端(240,240,250)
                        blade_r = int(150 + progress * 90)
                        blade_g = int(150 + progress * 90)
                        blade_b = int(165 + progress * 85)
                        canvas[y0][x0] = (blade_r, blade_g, blade_b, 255)
                        # 剑脊高光线（中脊）: 右侧偏移1px更亮的白色线
                        if x0 + 1 < W and px_count > 1 and px_count < blade_total - 1:
                            ridge_bright = min(255, blade_r + 30)
                            canvas[y0][x0 + 1] = (ridge_bright, ridge_bright, min(255, blade_b + 25), 255)
                    px_count += 1
                    if px_count > blade_total + 2:
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
                # v0.3.70: 剑刃金属光泽脉冲(Blade Sheen Pulse) — idle/walk时刃面光斑沿刃线游走
                # 原理：金属表面在光线角度微变时会产生移动的高光带，这种现象在游戏中
                #       用"sheen pulse"模拟——一个沿刀刃移动的亮斑，让武器"活"起来。
                #       就像现实中旋转刀片时看到的反射光游走效果。
                #       只在非战斗动画(idle/walk/run)中触发，战斗时用已有的挥动轨迹。
                if anim in ("idle", "walk", "run") and blade_total > 4:
                    # 光斑位置随帧索引在刃线上来回移动（正弦波）
                    _sheen_phase = (frame_idx / 5.0) * math.pi + 0.5  # 每周期约5帧
                    _sheen_pos = 0.3 + 0.4 * (0.5 + 0.5 * math.sin(_sheen_phase))  # 刃线30%~70%
                    _sheen_idx = int(_sheen_pos * blade_total)
                    # 重新追踪刃线路径找到光斑像素坐标
                    _sx0, _sy0 = weapon_base_x, weapon_base_y
                    _sx1, _sy1 = tip_x, min(H-1, tip_y)
                    _sdx = abs(_sx1 - _sx0); _sdy = abs(_sy1 - _sy0)
                    _ssx = 1 if _sx0 < _sx1 else -1; _ssy = 1 if _sy0 < _sy1 else -1
                    _serr = _sdx - _sdy; _spc = 0
                    while _spc <= _sheen_idx + 1:
                        if _spc == _sheen_idx and 0 <= _sy0 < H and 0 <= _sx0 < W:
                            # 光斑中心: 提亮+冷白色偏移
                            _sc = canvas[_sy0][_sx0]
                            if _sc[3] > 0:
                                canvas[_sy0][_sx0] = (
                                    min(255, _sc[0] + 35),
                                    min(255, _sc[1] + 35),
                                    min(255, _sc[2] + 40),  # 蓝更多→冷白金属光泽
                                    _sc[3]
                                )
                            # 光斑扩散: 左右±1px半透明光晕
                            for _soff in [-1, 1]:
                                _sox = _sx0 + _soff
                                if 0 <= _sy0 < H and 0 <= _sox < W:
                                    _soc = canvas[_sy0][_sox]
                                    if _soc[3] > 0:
                                        canvas[_sy0][_sox] = (
                                            min(255, _soc[0] + 18),
                                            min(255, _soc[1] + 18),
                                            min(255, _soc[2] + 22),
                                            _soc[3]
                                        )
                            break
                        _spc += 1
                        if _spc > blade_total + 2:
                            break
                        if _sx0 == _sx1 and _sy0 == _sy1:
                            break
                        _se2 = 2 * _serr
                        if _se2 > -_sdy:
                            _serr -= _sdy; _sx0 += _ssx
                        if _se2 < _sdx:
                            _serr += _sdx; _sy0 += _ssy
                # 剑柄护手(十字格): 在base位置画2px宽的横线
                guard_y = weapon_base_y - 1
                for gx_off in range(-2, 3):
                    guard_x = weapon_base_x + gx_off
                    if 0 <= guard_y < H and 0 <= guard_x < W:
                        canvas[guard_y][guard_x] = (160, 140, 80, 255)  # 金色护手
                # 剑柄缠绕: accent色
                for h_off in range(1, min(3, H - weapon_base_y)):
                    h_y = weapon_base_y - 2 - h_off
                    if 0 <= h_y < H and 0 <= weapon_base_x < W:
                        canvas[h_y][weapon_base_x] = (*accent, 255)
                # 剑尖
                if 0 <= tip_y < H and 0 <= tip_x < W:
                    canvas[tip_y][min(W-1, tip_x)] = (250, 250, 255, 255)
                    
            elif weapon == "staff":
                # 法杖: 棕色杖身 + 符文雕刻(交替亮点) + 杖顶宝石
                x0, y0 = weapon_base_x, weapon_base_y
                x1, y1 = tip_x, min(H-1, tip_y)
                dx_w = abs(x1 - x0)
                dy_w = abs(y1 - y0)
                sx = 1 if x0 < x1 else -1
                sy = 1 if y0 < y1 else -1
                err = dx_w - dy_w
                px_count = 0
                staff_total = max(1, abs(x1 - weapon_base_x) + abs(y1 - weapon_base_y))
                while True:
                    if 0 <= y0 < H and 0 <= x0 < W:
                        # 杖身棕色(140,110,70) + 纵向渐变(上深下浅)
                        progress = px_count / max(1, staff_total)
                        staff_r = int(120 + progress * 40)
                        staff_g = int(90 + progress * 30)
                        staff_b = int(50 + progress * 25)
                        canvas[y0][x0] = (staff_r, staff_g, staff_b, 255)
                        # v0.3.32: 符文雕刻 — 每隔3个像素画一个亮色符文点
                        # 符文使用accent色，亮度交替变化模拟雕刻纹理
                        if px_count % 3 == 0 and px_count > 2 and px_count < staff_total - 2:
                            rune_bright = 0.5 + 0.5 * math.sin(px_count * 0.8)
                            rr = min(255, int(accent[0] * rune_bright + 100 * (1 - rune_bright)))
                            rg = min(255, int(accent[1] * rune_bright + 80 * (1 - rune_bright)))
                            rb = min(255, int(accent[2] * rune_bright + 60 * (1 - rune_bright)))
                            # 符文在杖身左侧偏移1px
                            rune_x = x0 - 1
                            if 0 <= rune_x < W:
                                canvas[y0][rune_x] = (rr, rg, rb, 255)
                    px_count += 1
                    if px_count > staff_total + 2:
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
                # 杖顶宝石（保留原有逻辑，但增加发光外圈）
                if 0 <= tip_y < H and 0 <= tip_x < W:
                    for gy in range(max(0, tip_y-ps*2), min(H, tip_y+1)):
                        for gx in range(max(0, tip_x-ps), min(W, tip_x+ps+1)):
                            if 0 <= gy < H and 0 <= gx < W:
                                canvas[gy][gx] = (*accent, 255)
                    # 宝石高光点
                    hl_x, hl_y = tip_x - 1, tip_y - ps + 1
                    if 0 <= hl_y < H and 0 <= hl_x < W:
                        canvas[hl_y][hl_x] = (min(255, accent[0]+80), min(255, accent[1]+80), min(255, accent[2]+80), 255)
                    
            elif weapon == "bow":
                # v0.3.32: 弓弧渲染 — 曲线弓身 + 弦线
                # 弓身: 弯曲的弧线(用sin偏移模拟弯曲), 木色渐变
                # 弦: 从弓顶到弓底的直线(紧绷)
                bx0, by0 = weapon_base_x, weapon_base_y  # 弓中部
                bow_h = weapon_len  # 弓全长
                bow_curve = max(3, bow_h // 4)  # 弯曲偏移量
                # 画弓身（从上端到下端，中间向外弯曲）
                for step in range(bow_h + 1):
                    t = step / max(1, bow_h)  # 0=上端, 1=下端
                    by = by0 + step
                    # sin曲线偏移: 中间最大偏移(弯曲), 两端为0
                    curve_offset = int(math.sin(t * math.pi) * bow_curve)
                    bx = bx0 + curve_offset
                    if 0 <= by < H and 0 <= bx < W:
                        # 木色渐变: 中间深(120,80,40), 两端浅(160,110,60)
                        wood_t = abs(t - 0.5) * 2  # 0=中间, 1=端
                        wr = int(120 + wood_t * 40)
                        wg = int(80 + wood_t * 30)
                        wb = int(40 + wood_t * 20)
                        canvas[by][bx] = (wr, wg, wb, 255)
                        # 弓身宽度(2px): 内侧稍亮
                        if bx - 1 >= 0:
                            canvas[by][bx - 1] = (min(255, wr + 15), min(255, wg + 10), min(255, wb + 8), 255)
                # 画弦线: 从弓上端到弓下端的直线（紧绷的弦）
                bow_top_y = by0
                bow_bot_y = min(H - 1, by0 + bow_h)
                string_x = bx0  # 弦在弓的直线上（无弯曲偏移）
                for sy2 in range(bow_top_y, bow_bot_y + 1):
                    if 0 <= sy2 < H and 0 <= string_x < W:
                        # 弦色: 浅灰白(200,195,185), 比弓身细
                        canvas[sy2][string_x] = (200, 195, 185, 200)  # 半透明弦
                tip_x, tip_y = bx0, bow_bot_y  # 更新tip位置给发光效果
                    
            else:  # dagger
                # 匕首: 短刃 + 渐变(同剑但更短更暗)
                x0, y0 = weapon_base_x, weapon_base_y
                x1, y1 = tip_x, min(H-1, tip_y)
                dx_w = abs(x1 - x0)
                dy_w = abs(y1 - y0)
                sx = 1 if x0 < x1 else -1
                sy = 1 if y0 < y1 else -1
                err = dx_w - dy_w
                px_count = 0
                dag_total = max(1, abs(x1 - weapon_base_x) + abs(y1 - weapon_base_y))
                while True:
                    if 0 <= y0 < H and 0 <= x0 < W:
                        progress = px_count / max(1, dag_total)
                        # 匕首刃色: 暗端(130,135,140) → 亮端(200,210,220)
                        dr = int(130 + progress * 70)
                        dg = int(135 + progress * 75)
                        db = int(140 + progress * 80)
                        canvas[y0][x0] = (dr, dg, db, 255)
                    px_count += 1
                    if px_count > dag_total + 2:
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
                # 匕首柄: accent色短柄
                for h_off in range(2):
                    h_y = weapon_base_y - 1 - h_off
                    if 0 <= h_y < H and 0 <= weapon_base_x < W:
                        canvas[h_y][weapon_base_x] = (*accent, 255)
                if 0 <= tip_y < H and 0 <= tip_x < W:
                    canvas[tip_y][min(W-1, tip_x)] = (210, 220, 230, 255)
            
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
            elif anim == "attack":
                # v0.3.53: 攻击武器发光 — 蓄力微光→挥出峰值→收招渐熄
                # 原理：格斗游戏中武器挥击的发光变化是打击感(satisfakti)的核心要素，
                #       蓄力阶段微光暗示"能量聚集"，挥出峰值产生视觉冲击，
                #       收招阶段渐熄给出节奏感。与施法不同，攻击发光用暖白色调
                #       模拟金属摩擦/空气灼热的物理质感。
                _atk_nframes = 6
                _atk_t = frame_idx / max(1, _atk_nframes - 1)
                if _atk_t < 0.33:
                    # 蓄力阶段：微弱发光暗示能量聚集
                    glow_intensity = 0.15 + 0.35 * (_atk_t / 0.33)  # 0.15→0.50
                elif _atk_t < 0.60:
                    # 挥出峰值：武器最快速度通过空气，发光最强
                    glow_intensity = 0.50 + 0.40 * ((_atk_t - 0.33) / 0.27)  # 0.50→0.90
                else:
                    # 收招渐熄：能量消散
                    glow_intensity = 0.90 * (1.0 - (_atk_t - 0.60) / 0.40)  # 0.90→0
            elif anim == "defend":
                # v0.3.53: 防御微弱发光 — 格挡成功时武器微微闪光
                _def_nframes = 5
                _def_t = frame_idx / max(1, _def_nframes - 1)
                glow_intensity = 0.15 if _def_t < 0.3 else 0.08  # 准备阶段稍亮，稳守阶段微光
            
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
            
            # v0.3.49: 攻击武器挥动轨迹（Weapon Swing Trail）
            # 在攻击动画的挥出阶段(t>0.4)，武器尖端后方绘制半透明弧线残影
            # 原理：格斗游戏的经典技法"拖影"(afterimage)，用2-4个递减透明度的
            #       历史武器尖端位置模拟运动模糊，让攻击的力度感和速度感倍增
            if anim == "attack" and weapon in ("sword", "staff", "dagger", "bow"):
                # 获取当前帧的 t 值
                _trail_nframes = 6  # attack动画总帧数
                _trail_t = frame_idx / max(1, _trail_nframes - 1)
                # 只在挥出阶段(t>0.4)绘制轨迹
                if _trail_t > 0.4:
                    _trail_swing_raw = (_trail_t - 0.4) / 0.6  # 0→1
                    _trail_swing = self._ease_out(_trail_swing_raw)
                    _trail_retract = max(0, 1 - _trail_swing * 1.5)
                    _trail_current_angle = (1 - _trail_retract) * 1.0
                    # 画3个历史位置（角度从当前往回插值）
                    _trail_steps = 3
                    for _ti in range(1, _trail_steps + 1):
                        # 历史角度：从当前角度向之前的角度回溯
                        _trail_frac = _ti / (_trail_steps + 1)  # 0.25, 0.5, 0.75
                        # 插值回更早的角度（更大=更早的挥出位置）
                        _trail_hist_angle = _trail_current_angle + _trail_frac * 0.6
                        _trail_hist_angle = min(1.0, _trail_hist_angle)
                        # 计算历史武器尖端位置
                        _trail_tip_dx = int(_trail_hist_angle * weapon_len * 0.4)
                        _trail_tip_x = weapon_base_x + _trail_tip_dx
                        _trail_tip_y = weapon_base_y + weapon_len
                        # 透明度递减：最近的残影最亮，最远的最淡
                        _trail_alpha = int(90 * (1 - _trail_frac))
                        # 轨迹颜色：武器accent色的亮化版
                        if weapon == "sword":
                            _trail_color = (255, 240, 200)
                        elif weapon == "dagger":
                            _trail_color = (140, 230, 250)
                        else:
                            _trail_color = (min(255, accent[0] + 60), min(255, accent[1] + 60), min(255, accent[2] + 60))
                        # 在历史尖端位置画2x2半透明像素
                        for _ty in range(max(0, _trail_tip_y - 1), min(H, _trail_tip_y + 1)):
                            for _tx in range(max(0, _trail_tip_x - 1), min(W, _trail_tip_x + 1)):
                                if canvas[_ty][_tx][3] == 0:  # 只在空白区域画
                                    canvas[_ty][_tx] = (_trail_color[0], _trail_color[1], _trail_color[2], _trail_alpha)
                        # 沿轨迹弧线画1-2个中间点（连接当前尖端和历史尖端）
                        if _ti == 1:
                            _mid_dx = (_trail_tip_dx + tip_dx) // 2
                            _mid_x = weapon_base_x + _mid_dx
                            _mid_y = weapon_base_y + weapon_len
                            _mid_alpha = int(60 * (1 - _trail_frac))
                            if 0 <= _mid_y < H and 0 <= _mid_x < W and canvas[_mid_y][_mid_x][3] == 0:
                                canvas[_mid_y][_mid_x] = (_trail_color[0], _trail_color[1], _trail_color[2], _mid_alpha)
        
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
        
        # v0.3.49: 行走/奔跑地面扬尘粒子（Walk/Run Dust Particles）
        # 在walk/run动画中，脚底附近绘制微小的灰尘/沙尘颗粒
        # 原理：2D平台游戏的经典细节，角色移动时地面扬起灰尘让运动有"重量感"
        #       dust只在脚落地帧(踏地相位)出现，模拟脚掌撞击地面的效果
        if anim in ("walk", "run") and weapon != "none":
            # 脚底Y坐标：鞋底位置（leg_top + leg_h + shoe_h）
            _dust_ground_y = leg_top + leg_h + shoe_h
            if _dust_ground_y < H:
                # 脚落地相位检测：walk时每隔半周期有踏地帧
                _dust_t = frame_idx / max(1, 5)  # walk/run都是6帧
                _dust_phase = _dust_t * math.pi * 2
                # 踏地强度：sin波在接近0或π时代表脚着地
                _dust_impact = abs(math.sin(_dust_phase))
                # run时扬尘更多
                _dust_count = 4 if anim == "run" else 2
                _dust_alpha_base = 70 if anim == "run" else 45
                if _dust_impact > 0.3:  # 只在脚着地时产生扬尘
                    # 用帧索引作为伪随机种子，确保帧间一致
                    _dust_seed = frame_idx * 7 + 13
                    for _di in range(_dust_count):
                        # 扬尘X偏移：以角色中心为基准，向两侧散开
                        _dust_px = cx + ((_dust_seed + _di * 11) % 9) - 4  # -4到+4范围
                        # 扬尘Y偏移：地面向上1-2像素
                        _dust_py = _dust_ground_y - ((_dust_seed + _di * 3) % 2)
                        # 透明度：随粒子索引递减，加上踏地强度影响
                        _dust_alpha = int(_dust_alpha_base * (1 - _di * 0.25) * min(1.0, _dust_impact))
                        if 0 <= _dust_py < H and 0 <= _dust_px < W and _dust_alpha > 10:
                            if canvas[_dust_py][_dust_px][3] == 0:  # 不覆盖已有像素
                                # 灰尘色：暖灰色（偏土黄）
                                canvas[_dust_py][_dust_px] = (180, 165, 140, _dust_alpha)
        
        # v0.3.73: 跳跃落地冲击扬尘（Jump Landing Impact Dust）
        # 原理：角色从空中落地时，重力势能转化为地面冲击——比行走扬尘更剧烈。
        #       经典2D平台游戏(如Hollow Knight、Ori)中，落地扬尘是关键的"着陆反馈"，
        #       告诉玩家"你落地了"——这是游戏手感的隐形基础。
        #       与v0.3.49 walk/run扬尘的区别：粒子更多(8颗 vs 2-4颗)、
        #       扩散更广(±6 vs ±4)、alpha更高(100 vs 45-70)、颜色偏亮(模拟冲击扬起)
        #       只在jump动画最后一帧(落地帧)触发一次性爆发
        if anim == "jump" and frame_idx == 5:
            _jdust_ground_y = leg_top + leg_h + shoe_h
            if _jdust_ground_y < H:
                _jdust_count = 8  # 比walk(2)和run(4)更多，模拟冲击波
                _jdust_alpha_base = 100  # 比walk(45)更不透明，更明显
                _jdust_seed = 42  # 固定种子，落地帧确定性
                for _jdi in range(_jdust_count):
                    # X偏移：±6范围，比walk(±4)更宽，模拟落地冲击波扩散
                    _jdust_px = cx + ((_jdust_seed + _jdi * 13) % 13) - 6
                    # Y偏移：地面向上0-2像素，模拟扬尘高度
                    _jdust_py = _jdust_ground_y - ((_jdust_seed + _jdi * 5) % 3)
                    # Alpha递减：每颗粒子逐渐变淡，模拟扬尘消散
                    _jdust_alpha = int(_jdust_alpha_base * (1 - _jdi * 0.1))
                    if 0 <= _jdust_py < H and 0 <= _jdust_px < W and _jdust_alpha > 10:
                        if canvas[_jdust_py][_jdust_px][3] == 0:
                            # 落地扬尘色：比walk扬尘略亮（偏白灰），模拟高速冲击扬起的细尘
                            canvas[_jdust_py][_jdust_px] = (200, 190, 170, _jdust_alpha)
        
        # v0.3.74: 攻击速度线（Attack Speed Lines）— 攻击挥出阶段角色身后对角线速度线
        # 原理：格斗游戏和漫画的经典视觉技法"集中线/速度线"(speed lines)，
        #       在角色高速运动的反方向绘制放射状细线，瞬间传达速度感和力度感。
        #       Street Fighter/Guilty Gear系列大量使用这种技法增强打击感。
        #       速度线只在挥出阶段(t>0.4)出现，透明度随t递增后递减，
        #       3-5条对角线从角色左后方（远离攻击方向的对侧）向外辐射，
        #       颜色使用半透明白/灰色，不干扰角色本身的可读性。
        if anim == "attack":
            _spd_nframes = 6  # attack动画总帧数
            _spd_t = frame_idx / max(1, _spd_nframes - 1)
            if _spd_t > 0.35 and _spd_t < 0.85:
                # 速度线强度：中间最强(t≈0.6)，两端渐弱，sin钟形曲线
                _spd_intensity = math.sin((_spd_t - 0.35) / 0.5 * math.pi)
                _spd_intensity = max(0.0, min(1.0, _spd_intensity))
                if _spd_intensity > 0.2:
                    # 速度线数量：3-5条，根据强度调整
                    _spd_count = 3 + int(_spd_intensity * 2)
                    # 速度线起点：角色左后方区域（攻击方向为右侧/武器侧）
                    _spd_origin_x = cx - body_draw_w - ps * 2
                    _spd_origin_y = body_top + body_draw_h // 3
                    _spd_alpha_base = int(55 * _spd_intensity)
                    _spd_seed_base = frame_idx * 17 + 7
                    for _sli in range(_spd_count):
                        # 每条线的方向：从左后方向左上方/左下方辐射
                        _sli_angle_offset = (_spd_seed_base + _sli * 23) % 60 - 30  # -30到+30度变化
                        _sli_len = 3 + ((_spd_seed_base + _sli * 7) % 4)  # 3-6px长度
                        # 方向向量：左后方→左外方（攻击的反方向）
                        _sli_dx = -1 - abs(_sli_angle_offset) // 30  # -1或-2
                        _sli_dy = (_sli_angle_offset) // 15  # -2到+2
                        _sli_start_x = _spd_origin_x - _sli * 2
                        _sli_start_y = _spd_origin_y + (_sli - _spd_count // 2) * 3
                        # 透明度递减：第一条最亮，后面的渐淡
                        _sli_alpha = max(10, _spd_alpha_base - _sli * 12)
                        # 绘制速度线（逐像素Bresenham式）
                        for _sl_step in range(_sli_len):
                            _sl_px = _sli_start_x + _sl_step * _sli_dx
                            _sl_py = _sli_start_y + _sl_step * _sli_dy
                            if 0 <= _sl_py < H and 0 <= _sl_px < W:
                                if canvas[_sl_py][_sl_px][3] == 0:  # 不覆盖角色像素
                                    canvas[_sl_py][_sl_px] = (220, 215, 205, _sli_alpha)

        # v0.3.77: 攻击前冲扬尘(Attack Lunge Dust) — 攻击前冲时脚底向后飞溅的灰尘
        # 原理：动作游戏经典细节——角色攻击前冲时，脚掌蹬地产生向后的扬尘，
        #       模拟真实格斗中选手前进步伐的地面冲击。Street Fighter的前冲步法、
        #       Samurai Champloo的滑步扬尘都有类似效果。
        #       与v0.3.49 walk/run扬尘的区别：攻击扬尘方向性更强（向后扩散），
        #       粒子数量随前冲力度(body_dx)成正比，只在攻击前冲阶段(t≈0.5)出现。
        #       与v0.3.74攻击速度线互补：速度线是身后的运动轨迹线，扬尘是脚底的地面反馈。
        # 实现：检测attack动画中body_dx>0的前冲帧，从脚底向后(负X方向)喷射3-5颗暖灰粒子。
        if anim == "attack":
            _al_nframes = 6
            _al_t = frame_idx / max(1, _al_nframes - 1)
            # 前冲阶段：t=0.35~0.65（与body_dx前冲同步）
            if 0.3 < _al_t < 0.7:
                # 获取当前body_dx（v0.3.69攻击前冲机制）
                _al_pose = self._calc_pose("attack", _al_t)
                _al_dx = _al_pose.get("body_dx", 0)
                if _al_dx > 0:  # 只有前冲时才产生扬尘
                    _al_ground_y = leg_top + leg_h + shoe_h
                    if _al_ground_y < H:
                        _al_intensity = _al_dx / 3.0  # 归一化：dx=3时intensity=1.0
                        _al_count = int(3 + _al_intensity * 3)  # 3-6颗
                        _al_alpha_base = int(60 * _al_intensity)
                        _al_seed = frame_idx * 13 + 5
                        for _ali in range(_al_count):
                            # X偏移：向后（负X方向）飞溅，距离1-5px
                            _al_px = cx + body_dx - 1 - ((_al_seed + _ali * 7) % 5)
                            # Y偏移：脚底上方0-2px
                            _al_py = _al_ground_y - ((_al_seed + _ali * 3) % 3)
                            _al_alpha = int(_al_alpha_base * (1.0 - _ali / max(1, _al_count)))
                            if 0 <= _al_py < H and 0 <= _al_px < W and _al_alpha > 10:
                                if canvas[_al_py][_al_px][3] == 0:
                                    # 暖灰色扬尘（比walk扬尘偏暖，模拟前冲摩擦热量）
                                    canvas[_al_py][_al_px] = (195, 175, 150, _al_alpha)

        # v0.3.53: 受击冲击粒子（Hurt Impact Sparks）— 受击时飞溅的小火花/碎片粒子
        # 原理：格斗游戏和动作游戏的经典反馈特效，角色被击中时从受击点飞出
        #       小型发光粒子（火花/碎片），提供即时的视觉冲击反馈。
        #       命中火花(hit spark)是游戏打击感(juice)的核心元素之一，
        #       它让攻击的"命中瞬间"变得可感知——玩家通过火花就知道"打中了"。
        #       粒子从身体中心向外扩散，首帧最亮最大，后续帧渐淡渐小。
        #       颜色使用accent色变亮变暖，模拟受击瞬间的能量释放/灼热点。
        if anim == "hurt":
            _hurt_nframes = 3  # hurt动画固定3帧
            _hurt_t = frame_idx / max(1, _hurt_nframes - 1)  # 0→1
            _spark_fade = max(0.0, 1.0 - _hurt_t * 1.2)  # 首帧1.0，最后帧~0
            if _spark_fade > 0.1:
                # 冲击粒子中心：身体中心位置
                _spark_cx = cx + body_dx  # 跟随身体偏移
                _spark_cy = body_top + body_h // 2
                # 粒子数量：首帧6颗，逐帧减少
                _spark_count = max(1, int(6 * _spark_fade))
                # 粒子颜色：accent色变亮+暖色偏移（模拟能量释放）
                _spark_r = min(255, accent[0] + 80)
                _spark_g = min(255, accent[1] + 60)
                _spark_b = min(255, accent[2] + 30)
                for _si in range(_spark_count):
                    # 粒子方向：从中心向外扩散（8方向均匀分布）
                    _spark_angle = _si * (360.0 / 6) + 30  # 30°起始偏移避免正交对称
                    _spark_rad = math.radians(_spark_angle)
                    # 粒子距离：随帧增加向外飞散
                    _spark_dist = int((2 + _hurt_t * 4) * (0.8 + _si * 0.15))
                    _spark_px = int(_spark_cx + math.cos(_spark_rad) * _spark_dist)
                    _spark_py = int(_spark_cy + math.sin(_spark_rad) * _spark_dist)
                    # 粒子alpha：随fade和距离递减
                    _spark_alpha = int(200 * _spark_fade * max(0.3, 1.0 - _si * 0.12))
                    if 0 <= _spark_py < H and 0 <= _spark_px < W and _spark_alpha > 15:
                        if canvas[_spark_py][_spark_px][3] == 0:  # 不覆盖角色像素
                            canvas[_spark_py][_spark_px] = (_spark_r, _spark_g, _spark_b, _spark_alpha)

            # v0.3.77: 受击冲击波纹(Hurt Shockwave Ring) — 从身体中心向外扩展的圆形冲击波
            # 原理：动作游戏/格斗游戏经典技法——角色被击中时，以身体为中心产生一圈向外扩散的
            #       能量波纹(冲击波/shockwave)，强化"被重击"的视觉冲击感。
            #       Street Fighter的命中特效、Guilty Gear的冲击波、Hollow Knight受击都有类似效果。
            #       波纹是accent色的半透明环，半径随帧数扩大，alpha随距离递减。
            #       与冲击粒子(v0.3.53)互补：粒子是离散的飞溅碎片，波纹是连续的能量扩散面。
            # 实现：绘制一个圆环(外半径-内半径=1~2px)，中心在身体中心，半径随t增大。
            #       波纹仅在透明像素上绘制，不覆盖角色内容。
            if _spark_fade > 0.05:
                _ring_cx = cx + body_dx
                _ring_cy = body_top + body_h // 2
                _ring_radius = int(4 + _hurt_t * 12)  # 首帧4px → 末帧16px
                _ring_width = max(1, 2 - int(_hurt_t * 2))  # 首帧2px宽 → 末帧1px宽
                _ring_alpha_base = int(120 * _spark_fade)  # 随fade衰减
                if _ring_alpha_base > 10:
                    _ring_r = min(255, accent[0] + 40)
                    _ring_g = min(255, accent[1] + 35)
                    _ring_b = min(255, accent[2] + 25)
                    for _ry in range(max(0, _ring_cy - _ring_radius - _ring_width),
                                     min(H, _ring_cy + _ring_radius + _ring_width + 1)):
                        for _rx in range(max(0, _ring_cx - _ring_radius - _ring_width),
                                         min(W, _ring_cx + _ring_radius + _ring_width + 1)):
                            _rdist = math.sqrt((_rx - _ring_cx) ** 2 + (_ry - _ring_cy) ** 2)
                            if abs(_rdist - _ring_radius) <= _ring_width:
                                _r_falloff = 1.0 - abs(_rdist - _ring_radius) / max(1, _ring_width)
                                _r_alpha = int(_ring_alpha_base * _r_falloff)
                                if _r_alpha > 8 and canvas[_ry][_rx][3] == 0:
                                    canvas[_ry][_rx] = (_ring_r, _ring_g, _ring_b, _r_alpha)

        # ---- v0.3.69: 腋窝层间投射阴影(Axilla Inter-Part Cast Shadow) — 手臂在躯干上的定向投影 ----
        # 原理：真实光照中，抬起的物体会在其下方表面投射阴影。手臂与躯干之间
        #       形成的腋窝区域应该比周围更暗，因为来自主光源（左上方）的光线
        #       被手臂本身遮挡。这是经典的"cast shadow"（投射阴影）——不同于AO（环境光遮蔽），
        #       投射阴影具有明确的方向性：光源左上方→阴影出现在手臂右下方。
        #       这让手臂与身体的衔接更立体，增强"手臂是独立立体部件浮在身体前方"的深度层次。
        # 实现：在手臂绘制区域下方、身体区域内部，按光源方向偏移检测手臂遮挡，
        #       对被手臂阴影覆盖的身体像素施加柔和暗化（-12~-18亮度，带距离衰减）。
        #       左臂（远离光源侧）阴影较弱（手臂本身在阴影面），右臂（靠近光源侧）阴影较强。
        _axilla_shadow_radius = 3  # 阴影扩散半径（像素）
        _axilla_search_y_start = body_top + ps
        _axilla_search_y_end = body_top + body_draw_h // 2  # 只在上半身（手臂连接区域）
        # 构建不透明掩码，区分手臂/身体区域
        for _as_y in range(max(0, _axilla_search_y_start), min(H, _axilla_search_y_end)):
            for _as_x in range(max(0, cx - body_draw_w - arm_w - 2), min(W, cx + body_draw_w + arm_w + 2)):
                _as_px = canvas[_as_y][_as_x]
                if _as_px[3] == 0:
                    continue  # 跳过透明像素
                # 检查左上方是否有手臂像素（主光源从左上方照射→手臂阴影投向右下方）
                # 检查偏移位置(+1,+1)是否有不透明像素（代表手臂）
                _as_occluded = False
                _as_strength = 0
                for _as_dy, _as_dx, _as_w in [(1, 1, 1.0), (1, 2, 0.6), (2, 1, 0.4)]:
                    _as_check_y = _as_y - _as_dy
                    _as_check_x = _as_x - _as_dx
                    if 0 <= _as_check_y < H and 0 <= _as_check_x < W:
                        if canvas[_as_check_y][_as_check_x][3] > 0:
                            # 检查该像素是否在身体外侧（即手臂区域）
                            _as_rel_x = abs(_as_check_x - (cx + body_dx))
                            if _as_rel_x > body_draw_w // 2:
                                _as_occluded = True
                                _as_strength = max(_as_strength, _as_w)
                if _as_occluded and _as_strength > 0:
                    # 该像素在身体区域内、被手臂遮挡 → 暗化
                    _as_dark = int(15 * _as_strength)
                    _as_r = max(0, _as_px[0] - _as_dark)
                    _as_g = max(0, _as_px[1] - _as_dark - 2)  # 冷偏移：蓝少减→偏冷
                    _as_b = max(0, _as_px[2] - _as_dark)
                    canvas[_as_y][_as_x] = (_as_r, _as_g, _as_b, _as_px[3])
        
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
            
            # v0.3.40: Selout(选择性描边) — 描边亮度跟随相邻表面色，增强3D弹出效果
            # 原理：像素美术技法"selout"(selective outlining)：描边颜色不是纯黑固定色，
            #       而是根据相邻的表面色微调亮度。靠近亮色表面(如高光、皮肤)的描边像素
            #       会稍微变亮，靠近暗色表面(如深色服装、阴影)的保持深色。
            #       这让描边与角色色融合而不是生硬的纯黑切割线，创造微妙的3D弹出效果。
            # 实现：对每个描边像素，找最近的不透明邻居，取其颜色与描边色按3:1混合。
            #       75%描边+25%表面色：保留描边的轮廓功能，同时让描边"呼吸"融入角色。
            for y in range(H):
                for x in range(W):
                    if outline_layer[y][x]:
                        # 找到最近的不透明邻居颜色（优先4方向，再8方向对角线）
                        _near_r, _near_g, _near_b = 0, 0, 0
                        _found = False
                        for dx2, dy2 in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1)]:
                            nx, ny = x+dx2, y+dy2
                            if 0 <= nx < W and 0 <= ny < H and opaque[ny][nx]:
                                _nr, _ng, _nb, _na = canvas[ny][nx]
                                if _na > 0:
                                    _near_r, _near_g, _near_b = _nr, _ng, _nb
                                    _found = True
                                    break
                        if _found:
                            # 3:1混合 — 描边色为主，表面色微调
                            _sr = min(255, (outline[0] * 3 + _near_r) // 4)
                            _sg = min(255, (outline[1] * 3 + _near_g) // 4)
                            _sb = min(255, (outline[2] * 3 + _near_b) // 4)
                            canvas[y][x] = (_sr, _sg, _sb, 255)
                        else:
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
        
        # ---- v0.3.47: 辅助填充光(Fill Light) — 三点布光之Fill，照亮阴影区域防止死黑 ----
        # 原理：专业摄影/3D渲染的标准三点布光系统：Key(主光)+Fill(补光)+Rim(背光)。
        #       当前系统已有Key(v0.3.14左上主光)和Rim(v0.3.14右侧轮廓光)，
        #       但缺少Fill Light。Fill Light从主光反方向(右下方)提供微弱环境散射光，
        #       防止阴影区域完全"死黑"（纯暗无细节），同时为阴影面增加色彩变化。
        #       真实世界Fill Light来自天空散射光（偏冷蓝色调）+ 地面反射光（偏暖）。
        #       本实现使用冷色调模拟天空散射填充光，与主光暖色调形成互补。
        # 实现：对主光阴影侧(h_bias>0.15 或 v_bias>0.25)的像素施加微弱冷色提亮，
        #       强度约为主光的~15%(+3~+5)，模拟天空环境散射填充光。
        #       蓝通道额外+1 → 阴影面获得冷蓝色彩对比，增强整体色彩层次。
        # 位置：在主光着色之后、AO之前。AO会在Fill Light基础上叠加遮蔽暗化，
        #       这样凹面区域仍然偏暗，但不会像没有Fill Light时那样全黑。
        for y in range(H):
            for x in range(W):
                _fr, _fg, _fb, _fa = canvas[y][x]
                if _fa == 0:
                    continue
                # 填充光方向：从右下方（主光左上方的反方向）
                _fh = (x - cx) / max(1, W // 2)  # 水平偏移 -1~1
                _fv = (y - H * 0.3) / max(1, H * 0.7)  # 垂直偏移
                # 填充光强度：仅在阴影侧生效
                _fill_i = 0
                if _fh > 0.15:
                    _fill_i += int(_fh * 3)  # 右侧阴影：最大+3
                if _fv > 0.25:
                    _fill_i += int(_fv * 2)  # 底部阴影：最大+2
                if _fill_i > 0:
                    # 冷色调填充光：蓝>绿>红（模拟天空散射）
                    canvas[y][x] = (
                        min(255, _fr + max(0, _fill_i - 1)),  # 红略弱
                        min(255, _fg + _fill_i),                # 绿正常
                        min(255, _fb + _fill_i + 1),            # 蓝偏强→冷色
                        _fa
                    )
        
        # ---- v0.3.13→v0.3.45: 距离场体积AO（Distance-Field Volumetric AO）----
        # 原理：真实环境光遮蔽(Ambient Occlusion)的强度取决于该点与最近暴露面的距离。
        #       旧版Edge AO仅做2层硬切换（边缘-15/内1px-7），有两个问题：
        #       1) 渐变不平滑，在像素级别产生明显的色阶跳跃
        #       2) 不区分凸面(单侧遮挡)和凹面(双侧遮挡)——腋下、下颌下、
        #          肢体间等凹面区域应该比胳膊外侧获得更深的AO
        #       新版使用曼哈顿距离场计算每个不透明像素到最近透明像素的距离，
        #       并统计遮挡邻居数（concavity）调节AO深度：
        #       - 距离1px（边缘）: 基础AO -15，凹面增强至 -20
        #       - 距离2px（内层）: AO -10，凹面增强至 -14
        #       - 距离3px（深层）: AO -5（新增，旧版无此层）
        #       凹面检测：统计8方向中接触透明/边界的方向数(0-8)，
        #       ≥3个方向有遮挡视为凹面，AO强度×1.3
        # 实现：两趟扫描——第一趟BFS从透明像素扩散计算距离场，
        #       第二趟根据距离+凹度应用AO暗化
        _ao_max_dist = 3  # AO影响最大距离（像素）
        _ao_dist = [[_ao_max_dist + 1] * W for _ in range(H)]  # 距离场，初始=远处
        # 第一趟：BFS从所有透明像素（包括边界外的虚拟透明）向外扩散
        _ao_queue = []  # BFS队列 (y, x)
        # 标记透明像素和边界外为距离0
        for y in range(H):
            for x in range(W):
                if canvas[y][x][3] == 0:
                    _ao_dist[y][x] = 0
                    _ao_queue.append((y, x))
        # BFS扩散（曼哈顿距离）
        _ao_qi = 0
        while _ao_qi < len(_ao_queue):
            _qy, _qx = _ao_queue[_ao_qi]
            _ao_qi += 1
            _cd = _ao_dist[_qy][_qx]
            if _cd >= _ao_max_dist:
                continue
            for _ddx, _ddy in ((-1,0),(1,0),(0,-1),(0,1)):
                _nx, _ny = _qx + _ddx, _qy + _ddy
                if 0 <= _nx < W and 0 <= _ny < H and _ao_dist[_ny][_nx] > _cd + 1:
                    _ao_dist[_ny][_nx] = _cd + 1
                    _ao_queue.append((_ny, _nx))
        # 第二趟：根据距离+凹度应用AO
        # 凹度：对每个边缘像素，统计8方向中有多少方向在2px内接触透明
        for y in range(H):
            for x in range(W):
                _d = _ao_dist[y][x]
                if _d == 0 or _d > _ao_max_dist:
                    continue  # 透明或距离太远，跳过
                _px = canvas[y][x]
                if _px[3] == 0:
                    continue
                # 基础AO强度：距离1=-15, 距离2=-10, 距离3=-5（线性衰减）
                _ao_base = max(2, int(15 * (1.0 - (_d - 1) / _ao_max_dist)))
                # 凹度检测：统计8方向中接触透明/边界的方向数
                _concave_count = 0
                for _ddx, _ddy in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
                    _nx, _ny = x + _ddx, y + _ddy
                    if _nx < 0 or _nx >= W or _ny < 0 or _ny >= H:
                        _concave_count += 1  # 边界外视为遮挡
                    elif _ao_dist[_ny][_nx] <= 1:
                        _concave_count += 1  # 透明或边缘像素
                # 凹面增强：≥3个方向有遮挡视为凹面，AO×1.3
                if _concave_count >= 3:
                    _ao_base = int(_ao_base * 1.3)
                # 应用AO暗化
                canvas[y][x] = (
                    max(0, _px[0] - _ao_base),
                    max(0, _px[1] - _ao_base),
                    max(0, _px[2] - _ao_base),
                    _px[3]
                )
        
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
        
        # ---- v0.3.40: 垂直色温梯度（Vertical Color Temperature Gradient）----
        # 原理：真实光照中存在两种环境色温来源：
        #   1) 地面反射暖色光到角色下半身（间接光照 bounce light，偏暖黄/橙）
        #   2) 天空提供冷色环境光到角色上半身（sky ambient，偏冷蓝）
        #   这种纵向色温变化让角色"嵌入"环境中，而非漂浮在虚空中。
        # 实现：对每个不透明像素根据纵向位置微调色温：
        #   底部(y/H > 0.7): 暖偏移 R+4/G+2/B-3（模拟地面反射暖光）
        #   顶部(y/H < 0.3): 冷偏移 R-3/G-1/B+4（模拟天空冷色环境光）
        #   中间区域自然过渡，不做额外处理。
        #   偏移量极小（4-6单位），不影响角色本身色调，只增加环境色温感。
        for y in range(H):
            _vt = y / max(1, H - 1)  # 0=顶 1=底
            if _vt < 0.3:
                # 顶部冷偏移（天空环境光：蓝↑红↓）
                _cold = (0.3 - _vt) / 0.3  # 0→1 强度渐变
                _cold_amt = int(_cold * 5)  # 最大5个单位
                if _cold_amt > 0:
                    for x in range(W):
                        _px = canvas[y][x]
                        if _px[3] == 0:
                            continue
                        canvas[y][x] = (
                            max(0, _px[0] - _cold_amt),       # R↓ 冷色
                            _px[1],                             # G不变
                            min(255, _px[2] + _cold_amt),      # B↑ 冷色
                            _px[3]
                        )
            elif _vt > 0.7:
                # 底部暖偏移（地面反射光：红↑蓝↓）
                _warm = (_vt - 0.7) / 0.3  # 0→1 强度渐变
                _warm_amt = int(_warm * 6)  # 最大6个单位
                if _warm_amt > 0:
                    for x in range(W):
                        _px = canvas[y][x]
                        if _px[3] == 0:
                            continue
                        canvas[y][x] = (
                            min(255, _px[0] + _warm_amt),     # R↑ 暖色
                            min(255, _px[1] + _warm_amt // 2), # G微↑
                            max(0, _px[2] - _warm_amt // 2),  # B↓ 暖色
                            _px[3]
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
        
        # ---- v0.3.23→v0.3.44: 调色板色彩快照（OKLCH Palette Snap）— 感知距离色彩量化 ----
        # 将角色像素颜色量化到调色板附近的有限色阶，减少后处理引入的连续色调噪点
        # 原理：经过光照/AO/rim等多pass处理后，原始调色板的离散颜色被渐变为连续色，
        #       导致像素画看起来像缩小的位图而非真正的像素美术。本pass将颜色重新snap到
        #       调色板色阶上，保留光照方向但消除过度平滑。
        # v0.3.44: 使用OKLCH感知色彩空间距离替代RGB加权欧氏距离
        #   - OKLCH比RGB更符合人眼感知：相同ΔE值在任何色相区域都对应相同视觉差异
        #   - 解决RGB距离的已知问题：蓝色区域过度敏感（RGB距离夸大蓝色差异），
        #     黄色区域不敏感（RGB距离低估黄色差异），导致snap偏色
        #   - OKLCH极坐标距离公式：ΔE = sqrt(ΔL² + ΔC² + 2·C₁·C₂·(1-cosΔH))
        #   - 阈值0.015 OKLCH ≈ 2-3 JND（刚可分辨差异），足够保留光照梯度但消除噪点
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

            # v0.3.44: 预计算所有调色板色的OKLCH值，避免内循环重复计算
            def _snap_rgb_to_oklch(r, g, b):
                """RGB → OKLCH（简化版，纯算术，零依赖）"""
                def _lin(c):
                    c = c / 255.0
                    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                lr, lg, lb = _lin(r), _lin(g), _lin(b)
                l = lr * 0.4122214708 + lg * 0.5363325363 + lb * 0.0514459929
                m = lr * 0.2119034982 + lg * 0.6806995451 + lb * 0.1073969566
                s = lr * 0.0883024619 + lg * 0.2817188376 + lb * 0.6299787005
                l_ = l ** (1.0/3.0) if l > 0 else 0.0
                m_ = m ** (1.0/3.0) if m > 0 else 0.0
                s_ = s ** (1.0/3.0) if s > 0 else 0.0
                L = l_ * 0.2104542553 + m_ * 0.7936177850 + s_ * (-0.0040720468)
                a_ok = l_ * 1.9779984951 + m_ * (-2.4285922050) + s_ * 0.4505937099
                b_ok = l_ * 0.0259040371 + m_ * 0.7827717662 + s_ * (-0.8086757660)
                C = (a_ok * a_ok + b_ok * b_ok) ** 0.5
                H = math.degrees(math.atan2(b_ok, a_ok)) % 360
                return L, C, H

            snap_oklch = [_snap_rgb_to_oklch(c[0], c[1], c[2]) for c in snap_palette]
            # 预计算OKLCH缓存：对于每个不透明像素，仅计算一次OKLCH值
            # 缓存用字典存储，key=(r,g,b)
            _oklch_cache = {}

            for y in range(H):
                for x in range(W):
                    r, g, b, a = canvas[y][x]
                    if a == 0:
                        continue
                    # 查缓存或计算像素的OKLCH值
                    _px_key = (r, g, b)
                    if _px_key not in _oklch_cache:
                        _oklch_cache[_px_key] = _snap_rgb_to_oklch(r, g, b)
                    px_lch = _oklch_cache[_px_key]
                    # 找最近调色板色（OKLCH极坐标感知距离）
                    best_dist = float('inf')
                    best_color = (r, g, b)
                    for idx, sc in enumerate(snap_palette):
                        sc_lch = snap_oklch[idx]
                        dL = px_lch[0] - sc_lch[0]
                        dC = px_lch[1] - sc_lch[1]
                        C1, C2 = px_lch[1], sc_lch[1]
                        dH_sq = 2.0 * C1 * C2 * (1.0 - math.cos(math.radians(px_lch[2] - sc_lch[2])))
                        d = (dL * dL + dC * dC + dH_sq) ** 0.5
                        if d < best_dist:
                            best_dist = d
                            best_color = sc
                    # 仅当OKLCH距离超过阈值时才snap
                    # 0.015 OKLCH ≈ 2-3 JND，保留光照梯度但消除连续色调噪点
                    if best_dist > 0.015:
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

        # ---- v0.3.31: 皮肤次表面散射（Subsurface Scattering）— 增强皮肤通透感和生命力 ----
        # 原理：真实光照中，光线穿过皮肤表面后会从内部散射出来，尤其在边缘处形成
        #       温暖的红/橙色光泽（耳廓、手指、鼻尖等薄皮肤区域最明显）。
        #       在像素美术中，用暖色边缘光模拟SSS可以让皮肤看起来"有血色"、
        #       更有生命力，而不是像塑料一样死板。
        # 实现：在角色左侧（受光侧）的皮肤区域边缘，添加微暖的散射光；
        #       在右侧（背光侧）的皮肤边缘，添加更强烈的SSS（背光穿透更明显）
        # 限制：仅在皮肤色（palette[0]）附近像素上应用，避免影响衣物和装备
        skin_ref = palette[0]
        # 构建皮肤色检测范围 — 允许经过光照调整后的色差
        skin_threshold = 80  # 允许的颜色距离（考虑光照偏移后的皮肤色）
        for y in range(1, H - 1):
            for x in range(1, W - 1):
                r, g, b, a = canvas[y][x]
                if a == 0:
                    continue
                # 检查是否为皮肤色（与 palette[0] 近似）
                dr_s, dg_s, db_s = r - skin_ref[0], g - skin_ref[1], b - skin_ref[2]
                color_dist = dr_s*dr_s + dg_s*dg_s + db_s*db_s
                if color_dist > skin_threshold * skin_threshold:
                    continue  # 非皮肤色，跳过
                # 检查是否靠近角色轮廓边缘（至少一个邻居是透明像素）
                is_edge = False
                for ddx, ddy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nx, ny = x+ddx, y+ddy
                    if nx < 0 or nx >= W or ny < 0 or ny >= H or canvas[ny][nx][3] == 0:
                        is_edge = True
                        break
                if not is_edge:
                    continue
                # 根据水平位置决定SSS强度：
                # 右侧（背光侧）：SSS更强 — 光从后方穿透薄皮肤
                # 左侧（受光侧）：SSS较弱 — 正面光照已充分照亮皮肤
                h_pos = (x - cx) / max(1, W // 2)  # -1=最左, +1=最右
                if h_pos > 0.1:
                    # 背光侧：强SSS（红橙色穿透光）
                    sss_r = 12
                    sss_g = 4
                    sss_b = -3
                elif h_pos < -0.1:
                    # 受光侧：弱SSS（微暖光晕）
                    sss_r = 6
                    sss_g = 3
                    sss_b = -1
                else:
                    # 中心区域：最弱的SSS
                    sss_r = 3
                    sss_g = 1
                    sss_b = 0
                canvas[y][x] = (
                    min(255, max(0, r + sss_r)),
                    min(255, max(0, g + sss_g)),
                    min(255, max(0, b + sss_b)),
                    a
                )

        # ---- v0.3.60: 色温偏移着色(Warm-Shadow / Cool-Highlight Tinting) — 增强色彩深度 ----
        # 原理：真实光照中，阴影区域因环境光散射呈冷蓝色调（蓝天散射光），
        #       高光区域因主光源照射呈暖黄/橙色调（阳光或暖色灯光）。
        #       这是印象派画家(Monet, Renior)的经典发现，也是专业像素美术色彩理论的核心：
        #       "暗面偏冷，亮面偏暖"（或反之）的色彩互补策略，能大幅提升画面层次感。
        #       参考：Lospec像素教程"Color theory for pixel art"(2024)——
        #       "Shift your hue as well as your value: warm highlights + cool shadows = instant depth"。
        #       单纯调整明度（加深/提亮）会产生"灰色泥巴"效果，而色相偏移让暗面保持饱和，
        #       每个色阶都有独特的色温特征，视觉更丰富。
        # 实现：扫描所有不透明像素，根据亮度判断偏移方向：
        #       暗像素→向暖色偏移（+R, -B, 微调色相），亮像素→向冷色偏移（+B, -R）。
        #       偏移量很小（±5），避免干扰已建立的色彩和谐，仅增加微妙的色温对比。
        #       跳过纯黑/纯白像素（瞳孔/高光），仅影响中间调肤色和服装色。
        _skin_ref = palette[0]
        _skin_thr_sq = 90 * 90  # 皮肤色检测阈值平方
        for y in range(H):
            for x in range(W):
                _tp = canvas[y][x]
                if _tp[3] == 0:
                    continue
                _tr, _tg, _tb = int(_tp[0]), int(_tp[1]), int(_tp[2])
                _tlum = (_tr * 2 + _tg * 5 + _tb) // 8  # 加权亮度近似(luma)
                # 跳过极端亮度像素
                if _tlum < 20 or _tlum > 240:
                    continue
                # 检测是否为皮肤色（与palette[0]近似）
                _tdr, _tdg, _tdb = _tr - _skin_ref[0], _tg - _skin_ref[1], _tb - _skin_ref[2]
                _tdist_sq = _tdr*_tdr + _tdg*_tdg + _tdb*_tdb
                if _tdist_sq > _skin_thr_sq:
                    continue  # 非皮肤色跳过（服装色不做色温偏移，保持原始和谐）
                # 根据亮度决定色温偏移方向
                # 暗部(lum < 120): 暖偏移（+R, +G微, -B）→ 偏橙
                # 亮部(lum > 160): 冷偏移（-R微, +B）→ 偏蓝
                # 中间调(120-160): 不偏移（保持原有平衡）
                if _tlum < 120:
                    _warm_f = (120 - _tlum) / 120.0  # 0→1，越暗越暖
                    _tshift_r = int(5 * _warm_f)
                    _tshift_g = int(2 * _warm_f)
                    _tshift_b = -int(4 * _warm_f)
                elif _tlum > 160:
                    _cool_f = (_tlum - 160) / 80.0  # 0→1，越亮越冷
                    _tshift_r = -int(3 * _cool_f)
                    _tshift_g = 0
                    _tshift_b = int(4 * _cool_f)
                else:
                    continue  # 中间调不偏移
                canvas[y][x] = (
                    min(255, max(0, _tr + _tshift_r)),
                    min(255, max(0, _tg + _tshift_g)),
                    min(255, max(0, _tb + _tshift_b)),
                    _tp[3]
                )

        # ---- v0.3.46: 选择性眼睛发光（Selective Eye Glow）— Hollow Knight/Ori风格的锐利眼神光 ----
        # 原理：在《空洞骑士》《奥日》等知名像素/独立游戏中，角色眼睛具有一种独特的
        #       "发光感"——不是简单的白色高光，而是高光周围散发柔和的辐射光芒。
        #       这种效果在视觉上让角色的眼睛成为画面的视觉焦点，赋予角色"灵魂感"。
        #       技术本质是一种局部bloom（泛光）效果：检测高亮度像素（眼睛高光），
        #       在其周围区域叠加渐变衰减的半透明亮色，模拟光晕散射。
        # 实现：扫描画布找到眼睛主高光(255,255,255)和副高光(210,225,255)像素，
        #       在其周围2-3px半径内叠加微暖的加法光晕，强度随距离二次衰减。
        #       光晕颜色偏冷白（R220,G230,B255），营造水晶般的清透感。
        _eye_glow_points = []  # 收集所有眼睛高光点坐标
        for y in range(H):
            for x in range(W):
                cr, cg, cb, ca = canvas[y][x]
                if ca == 0:
                    continue
                # 检测主高光（纯白）和副高光（淡蓝白）
                if (cr >= 245 and cg >= 245 and cb >= 245) or \
                   (cr >= 200 and cg >= 215 and cb >= 245 and cr <= 220 and cg <= 235):
                    _eye_glow_points.append((x, y))
        # 对每个高光点，在周围2px半径内添加光晕
        for _gx, _gy in _eye_glow_points:
            for _dy in range(-2, 3):
                for _dx in range(-2, 3):
                    if _dx == 0 and _dy == 0:
                        continue  # 跳过高光点本身
                    _nx, _ny = _gx + _dx, _gy + _dy
                    if _nx < 0 or _nx >= W or _ny < 0 or _ny >= H:
                        continue
                    _dist_sq = _dx * _dx + _dy * _dy
                    if _dist_sq > 4:  # 限制半径≤2px
                        continue
                    _nr, _ng, _nb, _na = canvas[_ny][_nx]
                    if _na == 0:
                        # 空白像素也添加光晕（眼神光的空气散射）
                        _falloff = 1.0 - (_dist_sq / 5.0)
                        _glow_a = int(_falloff * 40)  # 最大alpha=40，柔和散射
                        if _glow_a > 3:
                            canvas[_ny][_nx] = (200, 215, 240, _glow_a)
                    else:
                        # 已有像素：加法混合（additive blend）模拟光晕
                        _falloff = 1.0 - (_dist_sq / 5.0)
                        _add_r = int(_falloff * 25)   # 微暖白色光晕
                        _add_g = int(_falloff * 28)
                        _add_b = int(_falloff * 35)   # 偏冷蓝（眼神光的清透感）
                        if _add_r > 1 or _add_g > 1 or _add_b > 1:
                            canvas[_ny][_nx] = (
                                min(255, _nr + _add_r),
                                min(255, _ng + _add_g),
                                min(255, _nb + _add_b),
                                _na
                            )

        # ---- v0.3.46: 服装褶皱暗示线（Clothing Fold Implication）— 面料垂坠质感 ----
        # 原理：真实服装在重力作用下，面料会沿身体曲面形成自然的垂坠褶皱。
        #       在像素美术中，用1-2px的微暗竖线暗示褶皱走向，可以显著增加
        #       服装的立体感和材质感，而无需增加复杂的着色。
        #       参考Slynyrd像素美术教程中的"fabric folds"技法：
        #       褶皱线应从肩部/胸部发出，向腰部收敛，呈"V"字形走向。
        #       颜色比底色暗10-15个色阶，宽度1px，长度覆盖躯干中部。
        # 实现：在躯干区域(body_top~body_bot)绘制3条微暗竖线：
        #   - 中心线：从胸口到腰部，最淡（depth=-8）
        #   - 左斜线：从左肩到腰中，稍强（depth=-12）
        #   - 右斜线：从右肩到腰中，稍强（depth=-12）
        #   线条颜色=底色暗化，根据y位置做线性渐变（上部深、下部浅→模拟褶皱从上落下）
        _fold_body_top = body_top + max(1, body_draw_h // 6)   # 褶皱起点（略低于领口）
        _fold_body_mid = body_top + body_draw_h // 2           # 褶皱中点（腰部）
        _fold_body_bot = body_top + body_draw_h * 3 // 4       # 褶皱终点（不延伸到腿）
        # 中心褶皱线
        _fold_cx = cx
        for y in range(max(0, _fold_body_top), min(H, _fold_body_bot)):
            r, g, b, a = canvas[y][_fold_cx]
            if a == 0:
                continue
            # 上部深、下部浅（褶皱从肩部垂下，越往下越舒展）
            _fold_t = (y - _fold_body_top) / max(1, _fold_body_bot - _fold_body_top)
            _darkness = int(8 * (1.0 - _fold_t * 0.6))  # 8→3的渐变暗度
            if _darkness > 1:
                canvas[y][_fold_cx] = (max(0, r - _darkness), max(0, g - _darkness), max(0, b - _darkness), a)
        # 左斜褶皱线（从左肩到腰部中心偏左）
        _fold_lx_start = cx - body_draw_w // 3
        _fold_lx_end = cx - max(1, body_draw_w // 6)
        for y in range(max(0, _fold_body_top), min(H, _fold_body_mid)):
            r, g, b, a = canvas[y][_fold_cx]
            if a == 0:
                continue
            _fold_t = (y - _fold_body_top) / max(1, _fold_body_mid - _fold_body_top)
            _fx = int(_fold_lx_start + (_fold_lx_end - _fold_lx_start) * _fold_t)
            if 0 <= _fx < W:
                _fr, _fg, _fb, _fa = canvas[y][_fx]
                if _fa == 0:
                    continue
                _darkness = int(12 * (1.0 - _fold_t * 0.5))  # 12→6渐变
                if _darkness > 1:
                    canvas[y][_fx] = (max(0, _fr - _darkness), max(0, _fg - _darkness), max(0, _fb - _darkness), _fa)
        # 右斜褶皱线（从右肩到腰部中心偏右，与左线对称）
        _fold_rx_start = cx + body_draw_w // 3
        _fold_rx_end = cx + max(1, body_draw_w // 6)
        for y in range(max(0, _fold_body_top), min(H, _fold_body_mid)):
            r, g, b, a = canvas[y][_fold_cx]
            if a == 0:
                continue
            _fold_t = (y - _fold_body_top) / max(1, _fold_body_mid - _fold_body_top)
            _fx = int(_fold_rx_start + (_fold_rx_end - _fold_rx_start) * _fold_t)
            if 0 <= _fx < W:
                _fr, _fg, _fb, _fa = canvas[y][_fx]
                if _fa == 0:
                    continue
                _darkness = int(12 * (1.0 - _fold_t * 0.5))  # 12→6渐变
                if _darkness > 1:
                    canvas[y][_fx] = (max(0, _fr - _darkness), max(0, _fg - _darkness), max(0, _fb - _darkness), _fa)

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

        # ---- v0.3.42: 地面反射光（Ground Bounce Light）— 从地面向上反射的间接光照 ----
        # 原理：真实光照中，光线照射到地面后会反射回角色底部，形成向上的填充光。
        #       这就是"bounce light"或"indirect illumination"——角色下半身不会完全黑暗，
        #       因为地面反射的暖色光会照亮腿部和身体下缘。
        #       专业像素美术技法（MortMort 2024, Slynyrd教程）将其列为"必备"效果之一。
        #       与v0.3.40的垂直色温梯度不同：色温梯度是全局环境色，而bounce light是
        #       从地面特定方向反射的有色光，强度受角色与地面距离影响（跳跃时减弱）。
        # 实现：对角色底部区域的每个不透明像素，根据纵向位置和与地面的距离，
        #       添加一个微暖的亮度提升（R+6/G+3/B+1），模拟地面漫反射。
        #       底部像素（靠近脚部）最强，往上渐弱；跳跃时减弱。
        _bounce_ground_y = leg_top + leg_h + body_dy  # 地面Y位置
        _bounce_intensity = 0.18  # 基础强度
        if body_dy < -2:
            # 跳跃时地面反射光减弱（离地面越远，反射越弱）
            _bounce_intensity = max(0.04, 0.18 - abs(body_dy) * 0.008)
        for y in range(max(0, _bounce_ground_y - H // 3), min(H, _bounce_ground_y)):
            # 距离地面越近，反射光越强（二次衰减）
            _bounce_dist = (_bounce_ground_y - y) / max(1, H // 3)  # 0=地面 1=远
            if _bounce_dist >= 1.0:
                continue
            _bounce_t = (1.0 - _bounce_dist) ** 2  # 二次衰减：靠近地面强
            _bounce_r = int(_bounce_t * _bounce_intensity * 35)  # R提升（暖色反射）
            _bounce_g = int(_bounce_t * _bounce_intensity * 18)  # G微提升
            _bounce_b = int(_bounce_t * _bounce_intensity * 5)   # B微提升（地面偏暖）
            if _bounce_r < 1 and _bounce_g < 1:
                continue
            for x in range(W):
                _bp = canvas[y][x]
                if _bp[3] == 0:
                    continue
                canvas[y][x] = (
                    min(255, _bp[0] + _bounce_r),
                    min(255, _bp[1] + _bounce_g),
                    min(255, _bp[2] + _bounce_b),
                    _bp[3]
                )

        # ---- v0.3.52: 施法魔法阵（Cast Magic Circle）— 脚底发光法阵增强施法仪式感 ----
        # 原理：经典 RPG 中施法角色脚下出现魔法阵是标志性视觉符号。
        #       用 accent color 绘制两层：外环（旋转符文感）+ 内部渐变光晕。
        #       强度跟随施法时间线：蓄力渐亮 → 释放峰值 → 恢复渐消。
        if anim == "cast":
            _cast_magic_t = frame_idx / max(1, 7 - 1)  # cast 动画固定 7 帧
            # 计算魔法阵强度：蓄力渐强，释放峰值，恢复渐弱
            if _cast_magic_t < 0.29:
                _circle_alpha = int((_cast_magic_t / 0.29) * 80)  # 0→80 蓄力渐亮
            elif _cast_magic_t < 0.43:
                _circle_alpha = 80 + int(((_cast_magic_t - 0.29) / 0.14) * 60)  # 80→140 高位蓄力
            elif _cast_magic_t < 0.57:
                _circle_alpha = 180  # 释放峰值
            else:
                _circle_alpha = max(0, int(180 * (1.0 - (_cast_magic_t - 0.57) / 0.43)))  # 180→0 渐消

            if _circle_alpha > 3:
                _circle_cx = cx  # 阵中心 X
                _circle_cy = leg_top + leg_h + body_dy + 2  # 阵中心 Y（脚底略下方）
                _circle_rx = int(body_draw_w * 1.8)  # 水平半径（比身体宽）
                _circle_ry = max(3, int(leg_h * 0.45))  # 垂直半径（透视压缩）
                # accent color 作为魔法阵色
                _mc_r, _mc_g, _mc_b = accent if len(palette) > 2 else (100, 150, 255)

                # 绘制外环（虚线旋转感 — 用 sin/cos 角度调制透明度模拟符文间断）
                _ring_inner_rx = int(_circle_rx * 0.75)
                _ring_inner_ry = max(2, int(_circle_ry * 0.75))
                _ring_outer_rx = _circle_rx
                _ring_outer_ry = _circle_ry
                for y in range(max(0, _circle_cy - _ring_outer_ry - 1), min(H, _circle_cy + _ring_outer_ry + 2)):
                    for x in range(max(0, _circle_cx - _ring_outer_rx - 1), min(W, _circle_cx + _ring_outer_rx + 2)):
                        dx_n = (x - _circle_cx) / max(1, _ring_outer_rx)
                        dy_n = (y - _circle_cy) / max(1, _ring_outer_ry)
                        dist_sq = dx_n * dx_n + dy_n * dy_n
                        # 角度用于旋转调制
                        _angle = math.atan2(dy_n, dx_n)
                        # 旋转感：角度偏移随帧变化（frame_idx 驱动旋转）
                        _rot_offset = frame_idx * 0.5
                        _rotated_angle = _angle + _rot_offset
                        # 符文间断：8 个方向上用 sin 调制，模拟符文刻痕
                        _rune_mod = 0.5 + 0.5 * math.sin(_rotated_angle * 4)  # 4 次对称符文
                        if 0.55 <= dist_sq <= 0.85:
                            # 外环区域
                            _ring_dist = abs(dist_sq - 0.7) / 0.15  # 0 在中心环，1 在边缘
                            _ring_falloff = max(0, 1.0 - _ring_dist)
                            _pixel_a = int(_circle_alpha * 0.7 * _ring_falloff * _rune_mod)
                            if _pixel_a > 2 and canvas[y][x][3] == 0:
                                canvas[y][x] = (
                                    min(255, _mc_r + int((255 - _mc_r) * 0.4)),
                                    min(255, _mc_g + int((255 - _mc_g) * 0.4)),
                                    min(255, _mc_b + int((255 - _mc_b) * 0.4)),
                                    _pixel_a
                                )
                        elif dist_sq < 0.5:
                            # 内部光晕：柔和渐变
                            _inner_falloff = 1.0 - dist_sq / 0.5
                            _pixel_a = int(_circle_alpha * 0.25 * _inner_falloff)
                            if _pixel_a > 2 and canvas[y][x][3] == 0:
                                canvas[y][x] = (
                                    min(255, _mc_r + int((255 - _mc_r) * 0.3)),
                                    min(255, _mc_g + int((255 - _mc_g) * 0.3)),
                                    min(255, _mc_b + int((255 - _mc_b) * 0.3)),
                                    _pixel_a
                                )

        # ---- v0.3.75: 施法升腾魔法粒子(Cast Rising Aura Particles) — 蓄力阶段accent色光粒向上飘升 ----
        # 原理：经典RPG/动作游戏施法角色周围常有环绕上升的魔法粒子/符文碎片，
        #       与地面魔法阵(v0.3.52)和武器发光(v0.3.16/53)形成完整的三层视觉：
        #       地面阵(根基)→上升粒子(能量流动)→武器光(释放焦点)。
        #       Final Fantasy系列的施法特效大量使用这种能量柱结构。
        # 实现：在cast蓄力阶段(t<0.57)，从角色身体中部两侧生成3-5颗小光粒，
        #       每帧向上飘移2-4px，alpha从120渐减到0，颜色为accent色偏亮。
        #       粒子X位置在身体两侧±(body_draw_w*0.8~1.2)范围内伪随机分布。
        #       粒子有1px光晕（上下左右各1px半透明像素），与死亡消散粒子(v0.3.70)风格统一。
        if anim == "cast":
            _cast_nframes = 7
            _cast_rise_t = frame_idx / max(1, _cast_nframes - 1)
            # 仅在蓄力阶段生成粒子（释放后粒子消散）
            if _cast_rise_t < 0.57:
                _rise_intensity = _cast_rise_t / 0.57  # 0→1 随蓄力增强
                _rise_n_parts = 3 + int(_rise_intensity * 3)  # 3→6颗
                _rise_seed = frame_idx * 31 + 13
                _rise_body_mid_y = (body_top + body_bot) // 2 + body_dy
                for _rpi in range(_rise_n_parts):
                    # 粒子X：身体两侧伪随机分布
                    _rp_side = 1 if (_rise_seed + _rpi * 17) % 2 == 0 else -1
                    _rp_offset = int(body_draw_w * (0.6 + ((_rise_seed + _rpi * 7) % 5) * 0.12))
                    _rp_x = cx + _rp_side * _rp_offset
                    # 粒子Y：从身体中部向上飘移（帧号越大飘越高）
                    _rp_float = int(frame_idx * 2.5 + (_rpi * 5) % 8)
                    _rp_y = _rise_body_mid_y - _rp_float
                    # 粒子alpha：蓄力越强越亮，每颗粒子递减
                    _rp_alpha = int(100 * _rise_intensity * max(0.3, 1.0 - _rpi * 0.12))
                    # 粒子颜色：accent色偏亮+暖
                    _rp_r = min(255, accent[0] + 55)
                    _rp_g = min(255, accent[1] + 45)
                    _rp_b = min(255, accent[2] + 30)
                    if 0 <= _rp_y < H and 0 <= _rp_x < W and _rp_alpha > 8:
                        if canvas[_rp_y][_rp_x][3] == 0:  # 不覆盖角色像素
                            canvas[_rp_y][_rp_x] = (_rp_r, _rp_g, _rp_b, min(255, _rp_alpha))
                        # 1px光晕
                        for _rdx, _rdy, _ra_mult in [(1,0,0.35),(-1,0,0.35),(0,1,0.35),(0,-1,0.35)]:
                            _rgx, _rgy = _rp_x + _rdx, _rp_y + _rdy
                            _rga = int(_rp_alpha * _ra_mult)
                            if 0 <= _rgy < H and 0 <= _rgx < W and _rga > 5:
                                if canvas[_rgy][_rgx][3] < _rga:
                                    canvas[_rgy][_rgx] = (_rp_r, _rp_g, _rp_b, _rga)

        # ---- v0.3.13: 地面阴影投射 — 椭圆形渐变阴影增强空间感 ----
        # 在角色脚底位置绘制一个椭圆形半透明阴影，模拟地面投影
        # 阴影宽度约等于身体宽度+margin，高度很扁（透视压缩）
        # 受 body_dy 影响：角色上升时阴影缩小变淡，下降时扩大变深
        # v0.3.75: 阴影中心跟随body_dx水平偏移（Shadow Body-DX Follow）—
        #          当角色因idle重心转移/攻击前冲/受击后退等产生body_dx时，
        #          地面阴影同步偏移，让水平位移有物理基础的视觉反馈。
        #          偏移量衰减为body_dx的50%（阴影是投影，不需要100%跟随）
        _shadow_cx = cx + int(body_dx * 0.5)  # 阴影中心X，跟随body_dx
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
        
        # v0.3.33: 有色地面阴影（Tinted Drop Shadow）— 基于角色配色着色的投影
        # 原理：真实光照中，阴影不是纯黑色的——它会吸收物体表面的颜色并偏移。
        #       专业像素美术技法中，用角色互补色或深色变体替代纯黑阴影，
        #       可以让阴影成为画面的一部分而非"空洞"，增强色彩和谐感。
        #       具体做法：阴影色 = body色的深色偏冷变体，而非纯黑(0,0,0)。
        #       这样阴影会带有角色衣着的色调倾向，在视觉上更"统一"。
        _shadow_base_r = max(0, body_color[0] // 4 - 10)  # body色除4再偏暗
        _shadow_base_g = max(0, body_color[1] // 4 - 10)
        _shadow_base_b = max(0, body_color[2] // 4 + 5)   # 蓝色少减→偏冷色调
        
        # v0.3.68: Bayer抖动地面阴影（Dithered Ground Shadow）
        # 原理：像素美术中，纯实心阴影在低分辨率下显得粗糙生硬。
        #       用Bayer矩阵抖动(checkerboard pattern)替代实心填充，
        #       阴影边缘呈现像素化的半透明渐变——这是像素美术的经典技法，
        #       Celeste/Hyper Light Drifter等游戏都使用抖动阴影。
        #       抖动阈值从中心(低阈值=实心)向边缘(高阈值=稀疏)递增，
        #       结合高斯衰减alpha，形成"中心实心→边缘渐隐抖动"的自然过渡。
        # 4×4 Bayer矩阵阈值（0-15标准化到0.0-1.0）
        _bayer4 = [
            [ 0,  8,  2, 10],
            [12,  4, 14,  6],
            [ 3, 11,  1,  9],
            [15,  7, 13,  5],
        ]
        
        for y in range(max(0, shadow_y_base - shadow_ry), min(H, shadow_y_base + shadow_ry + 1)):
            for x in range(max(0, _shadow_cx - shadow_rx), min(W, _shadow_cx + shadow_rx)):
                dx_s = (x - _shadow_cx) / max(1, shadow_rx)
                dy_s = (y - shadow_y_base) / max(1, shadow_ry)
                dist_sq = dx_s * dx_s + dy_s * dy_s
                if dist_sq <= 1.0:
                    # 椭圆内部：中心深、边缘淡（高斯衰减）
                    falloff = 1.0 - dist_sq
                    sa = int(shadow_alpha_base * falloff * falloff)
                    if sa > 3 and canvas[y][x][3] == 0:
                        # Bayer抖动：归一化距离→抖动阈值比较
                        # 归一化距离 0.0(中心)→1.0(边缘) 映射到阈值 0.2→0.95
                        # 中心区域几乎所有Bayer值都通过→接近实心
                        # 边缘区域仅低Bayer值通过→稀疏像素点
                        _dither_threshold = 0.2 + (1.0 - falloff) * 0.75
                        _bayer_val = _bayer4[y % 4][x % 4] / 15.0
                        if _bayer_val >= _dither_threshold:
                            continue  # 抖动跳过：此像素不绘制，形成棋盘格稀疏
                        # 仅在空白区域绘制阴影（不覆盖角色像素）
                        # 边缘略微提亮阴影色（模拟环境光对阴影边缘的照亮）
                        _edge_bright = int((1.0 - falloff) * 15)
                        canvas[y][x] = (min(255, _shadow_base_r + _edge_bright),
                                        min(255, _shadow_base_g + _edge_bright),
                                        min(255, _shadow_base_b + _edge_bright),
                                        sa)
        
        # ---- v0.3.51: 选择性抗锯齿（Selective Anti-Aliasing）— 专业像素美术的阶梯平滑 ----
        # 原理：像素美术中，对角线和曲线边缘形成锯齿状"阶梯"(staircase)图案。
        #       专业像素画家在这些阶梯拐角处放置一个中间色的半透明像素，
        #       让边缘在视觉上显得更平滑，同时不破坏像素的锐利感。
        #       这不是全画面抗锯齿——只在轮廓边缘的对角线拐角添加"AA像素"。
        #       参考：slynyrd(2024)像素教程将此列为"AA像素"必做技法，
        #             PedrosMedeiros(像素艺术手册)称之为"选择性平滑"。
        # 检测方法：3×3邻域分析，找到"阶梯拐角"模式：
        #   模式A(右下阶梯): [空白][实心]    模式B(左下阶梯): [实心][空白]
        #                    [实心][空白]                      [空白][实心]
        #   在空白位放置半透明中间色像素，"填充"视觉阶梯。
        # 仅对描边样式的轮廓生效（pixel/cartoon/anime/dark），无描边样式(western)不处理。
        if outline is not None:
            _aa_pass = [[(0,0,0,0)]*W for _ in range(H)]  # AA层：单独收集，避免干扰检测
            for y in range(1, H - 1):
                for x in range(1, W - 1):
                    # 当前像素必须为空（透明），才可能放置AA像素
                    if canvas[y][x][3] > 0:
                        continue
                    # 获取3×3邻域的不透明掩码
                    _n = [
                        canvas[y-1][x-1][3] > 0, canvas[y-1][x][3] > 0, canvas[y-1][x+1][3] > 0,
                        canvas[y][x-1][3] > 0,   False,                  canvas[y][x+1][3] > 0,
                        canvas[y+1][x-1][3] > 0, canvas[y+1][x][3] > 0, canvas[y+1][x+1][3] > 0,
                    ]  # 索引: 0=TL 1=T 2=TR 3=L 4=skip 5=R 6=BL 7=B 8=BR
                    
                    # 检测4种阶梯拐角模式（每种2个不透明对角+2个透明正交邻居）
                    _match_color = None
                    
                    # 模式1: 右上角 ↗ — TL和R实心，T和L透明
                    #   [solid][empty][     ]
                    #   [empty][AA  ][solid]
                    if _n[0] and _n[5] and not _n[1] and not _n[3]:
                        _match_color = canvas[y-1][x-1]
                    # 模式2: 左上角 ↖ — TR和L实心，T和R透明
                    elif _n[2] and _n[3] and not _n[1] and not _n[5]:
                        _match_color = canvas[y-1][x+1]
                    # 模式3: 右下角 ↘ — L和B实心，BL和R透明（实际：BL实/BR透的变体）
                    #   [     ][empty][     ]
                    #   [solid][AA  ][empty]
                    #   [empty][solid][     ]
                    elif _n[3] and _n[7] and not _n[6] and not _n[5]:
                        _match_color = canvas[y][x-1]
                    # 模式4: 左下角 ↙ — R和B实心，BR和L透明
                    #   [     ][empty][     ]
                    #   [empty][AA  ][solid]
                    #   [     ][solid][empty]
                    elif _n[5] and _n[7] and not _n[8] and not _n[3]:
                        _match_color = canvas[y][x+1]
                    
                    if _match_color is not None and _match_color[3] > 0:
                        # AA像素：50%透明度的邻近表面色（标准像素美术AA比例）
                        _aa_alpha = max(40, _match_color[3] // 2)  # 至少40，或原色50%
                        _aa_pass[y][x] = (
                            min(255, _match_color[0]),
                            min(255, _match_color[1]),
                            min(255, _match_color[2]),
                            _aa_alpha
                        )
            # 将AA层叠加到canvas（仅覆盖透明像素，不破坏已有内容）
            for y in range(H):
                for x in range(W):
                    if _aa_pass[y][x][3] > 0 and canvas[y][x][3] == 0:
                        canvas[y][x] = _aa_pass[y][x]
        
        # ---- v0.3.55b: 角色氛围光晕(Character Ambient Aura) — accent色柔光背景增强角色存在感 ----
        # 原理：专业像素美术和游戏美术中常用技法——在角色周围添加一层微弱的彩色光晕，
        #       其颜色取自角色的强调色(accent)。效果类似于RPG游戏中角色被选中时的轮廓光，
        #       或Celeste/Owlboy等独立游戏中角色自带的微弱环境光。
        #       作用：(1)在任何背景下都能让角色"跳出"背景 (2)统一角色的色彩印象
        #            (3)暗示角色的"存在感/能量场"，尤其是法师/施法类角色
        # 实现：计算角色包围盒中心，在角色像素周围2-3px范围的空白区域，
        #       用accent色的极低透明度(alpha=18-25)绘制椭圆光晕。
        #       光晕仅在透明像素上绘制，不覆盖任何角色内容。
        _aura_cx = cx  # 角色水平中心（复用已有的cx变量）
        _aura_cy = (body_top + leg_top + leg_h + body_dy) // 2  # 角色垂直中心
        _aura_rx = int(body_draw_w * 1.8)  # 光晕水平半径（比身体宽80%）
        _aura_ry = int((leg_top + leg_h + body_dy - body_top) * 0.55)  # 光晕垂直半径
        _aura_color = (min(255, accent[0] + 30), min(255, accent[1] + 30), min(255, accent[2] + 30))
        if _aura_rx > 2 and _aura_ry > 2:
            for _ay in range(max(0, _aura_cy - _aura_ry), min(H, _aura_cy + _aura_ry)):
                for _ax in range(max(0, _aura_cx - _aura_rx), min(W, _aura_cx + _aura_rx)):
                    if canvas[_ay][_ax][3] > 0:
                        continue  # 跳过已有内容
                    _adx = (_ax - _aura_cx) / max(1, _aura_rx)
                    _ady = (_ay - _aura_cy) / max(1, _aura_ry)
                    _adist_sq = _adx * _adx + _ady * _ady
                    if _adist_sq <= 1.0:
                        # 内部渐变：边缘最亮(alpha=22)，中心最淡(alpha=8)
                        _a_falloff = _adist_sq  # 0=中心 1=边缘
                        _a_alpha = int(8 + 14 * _a_falloff)
                        if _a_alpha > 4:
                            canvas[_ay][_ax] = (*_aura_color, _a_alpha)
        
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
