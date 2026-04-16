# ArtPipe - AI 2D Game Character Asset API

> **POST /api/generate → 引擎就绪的2D角色美术资产包**

API-First 的 AI 2D 游戏角色生成服务。一个 POST 请求，从文字描述到可直接导入引擎的完整角色资产包。

## 一行调用

```bash
# 程序化生成（默认，毫秒级响应）
curl -X POST http://localhost:8080/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "一个穿红色斗篷的精灵猎人，手持弓箭"}'

# AI 图像生成（Pollinations.ai 免费，~30s）
curl -X POST http://localhost:8080/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "像素风蓝色法师，手持法杖", "render_mode": "ai"}'

# 混合模式（AI 参考图 + 程序化精灵表）
curl -X POST http://localhost:8080/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "日式RPG盗贼，穿皮甲", "render_mode": "hybrid"}'
```

**返回：** SpriteSheet PNG（base64）+ AI 图像（base64）+ Spine 骨骼 JSON + Unity Package + Godot Scene + 动画数据

## Quick Start

```bash
git clone https://github.com/kongshan001/art-pipe.git
cd art-pipe
python3 app.py
# API running at http://localhost:8080
```

**零依赖** — 纯 Python 标准库，无需 pip install。

## 渲染模式（v0.3 新增）

| 模式 | 说明 | 响应时间 | AI 图像 |
|------|------|---------|---------|
| `procedural` | 程序化生成（默认） | <1s | ❌ |
| `ai` | AI 图像生成（Pollinations/Flux） | ~30-60s | ✅ |
| `hybrid` | AI 参考图 + 增强程序化精灵表 | ~30-60s | ✅ |

### AI 后端

| 后端 | 免费 | 需要 API Key |
|------|------|-------------|
| [Pollinations.ai](https://pollinations.ai) | ✅ | ❌ |
| Stability AI | ❌ | `STABILITY_API_KEY` |
| Replicate | ❌ | `REPLICATE_API_TOKEN` |

```bash
# 查看 AI 后端可用性
curl http://localhost:8080/api/backends
```

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
  "render_mode": "procedural",           // 可选: procedural|ai|hybrid（v0.3 新增）
  "ai_backend": "pollinations",          // 可选: pollinations|stability（v0.3 新增）
  "formats": ["spine","unity","godot"],  // 可选: 默认全部格式
  "include_png": true                    // 可选: 是否返回base64 PNG
}
```

**Response:**
```json
{
  "id": "char_1234567890_5678",
  "prompt": "...",
  "render_mode": "ai",
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
  "ai_image": {
    "image_base64": "...",
    "backend": "pollinations",
    "generation_time": 24.5,
    "size": 39321,
    "format": "JPEG"
  },
  "skeleton": {
    "bones": [...],
    "slots": [...]
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

### 端点列表

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/info` | API 信息 |
| `GET` | `/api/styles` | 可用风格列表 |
| `GET` | `/api/types` | 可用角色类型 |
| `GET` | `/api/backends` | AI 后端可用性（v0.3 新增） |
| `GET` | `/preview/{id}` | 浏览器预览页（支持 AI 图像展示） |
| `POST` | `/api/generate` | 生成角色资产包 |
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
├── engine.py       # 角色生成引擎（种子RNG + 程序化渲染 + AI 集成）
├── sd_client.py    # AI 图像生成客户端（Pollinations/Flux，可扩展）  ← v0.3 新增
├── exporter.py     # 多格式导出（Spine/Unity/Godot/SpriteSheet）
├── png_writer.py   # 零依赖 PNG 生成器（struct + zlib）
└── __init__.py

app.py              # API 服务（纯标准库 http.server）
```

## Roadmap

- [x] v0.1 — Web UI 向导（Canvas 渲染）
- [x] v0.2 — **API-First 重构**（Python 引擎 + 4格式导出）
- [x] v0.3 — **AI 图像生成**（Pollinations/Flux + 3种渲染模式）
- [ ] v0.4 — SAM 自动拆层
- [ ] v0.5 — 真 Spine .skel 二进制导出
- [ ] v0.6 — 风格 LoRA 市场
- [ ] v1.0 — 完整平台（API + 计费 + 团队）

## License

MIT
