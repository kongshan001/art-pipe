# ArtPipe - AI 2D Game Character Asset Pipeline

> **"Describe your character, get engine-ready 2D asset pack in 30 seconds"**

AI-powered 2D game character generation pipeline. From text description to rigged, animated, engine-exportable character assets.

## Features (MVP v0.1)

- **5 Art Styles**: Pixel Art, Cartoon, Anime, Western, Dark Fantasy
- **7 Character Types**: Warrior, Mage, Archer, Rogue, Healer, Monster, NPC
- **6 Animations**: Idle, Walk, Run, Attack, Hurt, Die
- **Real-time Canvas Preview**: Interactive animation playback with speed/scale controls
- **4 Export Formats**: Unity Package, Spine Project, Sprite Sheet, Godot Scene
- **Color Scheme Switching**: Generate color variants instantly
- **Character Variants**: 4 procedural variations per generation
- **Gallery**: Save and browse all generated characters
- **Zero Dependencies**: Pure Python backend + vanilla JS frontend

## Quick Start

```bash
# Clone
git clone https://github.com/kongshan001/art-pipe.git
cd art-pipe

# Run (no install needed!)
python3 app.py

# Open in browser
open http://localhost:8080
```

## Architecture

```
ArtPipe/
├── app.py                    # Python HTTP server (zero deps)
├── templates/
│   └── index.html            # Single-page application
├── static/
│   ├── css/style.css         # Dark theme UI
│   └── js/
│       ├── character.js      # Procedural character generation engine
│       ├── animator.js       # Canvas 2D renderer + animation engine
│       ├── exporter.js       # Multi-format export (Unity/Spine/Godot/SpriteSheet)
│       └── app.js            # Main application logic
└── docs/
    └── research-report.md    # Full market research & product analysis
```

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Backend | Python stdlib (http.server) | Zero dependencies, instant run |
| Frontend | Vanilla HTML/CSS/JS | No build step, fast loading |
| Rendering | Canvas 2D API | Hardware-accelerated, universal |
| Character Gen | Procedural (seeded RNG) | Deterministic, no GPU needed |
| Animation | Frame-based interpolation | Smooth 30fps playback |

## Roadmap

- [x] v0.1 MVP - Procedural character generation
- [ ] v0.2 - AI image generation (Stable Diffusion API integration)
- [ ] v0.3 - SAM-based automatic layer splitting
- [ ] v0.4 - Real Spine .skel binary export
- [ ] v0.5 - Style LoRA marketplace (UGC)
- [ ] v0.6 - 3D character generation pipeline
- [ ] v1.0 - Full platform with API, billing, team features

## Market Research

See `docs/research-report.md` for the full analysis covering:
- Complete 2D/3D/UI/VFX art production pipelines
- Price tiers ($0 to $100K+ per asset)
- AI disruption analysis across all pipeline stages
- Competitive landscape and positioning

## License

MIT

## Links

- **GitHub**: https://github.com/kongshan001/art-pipe
- **Research Report**: https://github.com/kongshan001/art-pipe/tree/main/docs
