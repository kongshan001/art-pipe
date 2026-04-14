# ArtPipe - AI 2D Game Character Asset API

> **POST /api/generate → 引擎就绪的2D角色美术资产包**

API-First 的 AI 2D 游戏角色生成服务。一个 POST 请求，从文字描述到可直接导入引擎的完整角色资产包。

## 一行调用

```bash
curl -X POST http://localhost:8080/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "一个穿红色斗篷的精灵猎人，手持弓箭"}'
```

**返回：** SpriteSheet PNG（base64）+ Spine 骨骼 JSON + Unity Package + Godot Scene + 动画数据

## Quick Start

```bash
git clone https://github.com/kongshan001/art-pipe.git
cd art-pipe
python3 app.py
# API running at http://localhost:8080
```

**零依赖** — 纯 Python 标准库，无需 pip install。

## API Reference

### `POST /api/generate`

核心接口：提示词 → 完整角色资产包。

**Request:**
```json
{
  "prompt": "一个穿红色斗篷的精灵猎人",   // 必填
  "style": "pixel",                      // 可选: pixel|cartoon|anime|western|dark
  "char_type": "archer",                 // 可选: warrior|mage|archer|rogue|healer|monster|npc
  "seed": 12345,                         // 可选: 固定种子可复现结果
  "formats": ["spine","unity","godot"],  // 可选: 默认全部格式
  "include_png": true                    // 可选: 是否返回base64 PNG
}
```

**Response:**
```json
{
  "id": "char_1234567890_5678",
  "prompt": "...",
  "style": "pixel",
  "style_name": "像素风",
  "char_type": "archer",
  "char_type_name": "弓箭手",
  "seed": 1061095808,
  "palette": [[56,135,233], [220,60,60], ...],
  "animations": {
    "idle":   {"frame_count": 4, "fps": 8, "loop": true},
    "walk":   {"frame_count": 6, "fps": 8, "loop": true},
    "run":    {"frame_count": 6, "fps": 8, "loop": true},
    "attack": {"frame_count": 6, "fps": 8, "loop": true},
    "hurt":   {"frame_count": 3, "fps": 8, "loop": true},
    "die":    {"frame_count": 6, "fps": 8, "loop": false}
  },
  "spritesheet": {
    "png_base64": "...",
    "total_frames": 31,
    "cols": 8,
    "frame_width": 64,
    "frame_height": 80,
    "frame_map": {"idle": {"start": 0, "count": 4}, ...}
  },
  "skeleton": {
    "bones": [...],   // 13 根骨骼
    "slots": [...]    // 6 个插槽
  },
  "exports": {
    "spine": {"filename": "...", "content": "..."},
    "unity": {"filename": "...", "content": "...", "script": "..."},
    "godot": {"filename": "...", "content": "...", "script": "..."},
    "spritesheet": {"filename": "...", "content": "..."}
  },
  "preview_url": "/preview/char_1234567890_5678"
}
```

### 其他端点

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/info` | API 信息 |
| `GET` | `/api/styles` | 可用风格列表 |
| `GET` | `/api/types` | 可用角色类型 |
| `GET` | `/preview/{id}` | 浏览器预览页 |
| `POST` | `/api/export` | 对已生成角色重新导出 |

## 导出格式

### Spine
- 兼容 Spine 4.1 的骨骼 JSON
- 13 根骨骼层级（root → hip → spine → neck → head/arms/legs）
- 6 种动画关键帧（旋转/位移）
- 直接用 Spine Editor 打开即可编辑

### Unity
- `.controller` Animator Controller（含状态机 + 过渡条件）
- `C# Controller` 脚本（键盘输入 → 动画切换）
- Sprite Atlas 元数据
- Prefab 结构定义

### Godot
- `.tscn` 场景文件（CharacterBody2D + Sprite2D + AnimationPlayer）
- GDScript 控制器（移动 + 动画状态机）
- 完整动画轨道数据

### SpriteSheet
- PNG（base64）+ JSON 元数据
- 兼容 TexturePacker / Aseprite 格式
- frame tags 标记动画分组

## 自然语言提示词支持

API 自动从提示词中提取：
- **风格**：像素/卡通/日式/欧美/暗黑（关键词匹配）
- **角色类型**：战士/法师/弓箭手/盗贼/治疗师/怪物/NPC
- **颜色**：红/蓝/绿/紫/金/银/黑/白 等 10+ 色彩关键词

```bash
# 自动识别：pixel + archer + red
curl -X POST ... -d '{"prompt": "像素风红色猎人持弓"}'

# 自动识别：dark + monster
curl -X POST ... -d '{"prompt": "暗黑哥特恶魔boss"}'
```

## Architecture

```
artpipe/
├── engine.py       # 角色生成引擎（种子RNG + 程序化渲染 + 骨骼生成）
├── exporter.py     # 多格式导出（Spine/Unity/Godot/SpriteSheet）
├── png_writer.py   # 零依赖 PNG 生成器（struct + zlib）
└── __init__.py

app.py              # API 服务（纯标准库 http.server）
```

## Roadmap

- [x] v0.1 — Web UI 向导（Canvas 渲染）
- [x] v0.2 — **API-First 重构**（Python 引擎 + 4格式导出）
- [ ] v0.3 — AI 图像生成（Stable Diffusion API）
- [ ] v0.4 — SAM 自动拆层
- [ ] v0.5 — 真 Spine .skel 二进制导出
- [ ] v0.6 — 风格 LoRA 市场
- [ ] v1.0 — 完整平台（API + 计费 + 团队）

## License

MIT
