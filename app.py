#!/usr/bin/env python3
"""
ArtPipe API v0.3.0 - AI 2D Game Character Asset Generation
API-First: POST /api/generate → 完整引擎就绪美术资产包
v0.3 新增: AI图像生成 (render_mode=ai/hybrid)
v0.3.17: XSS修复(html.escape) + ThreadingHTTPServer并发支持

Usage:
    python3 app.py [port]

Endpoints:
    POST /api/generate   - 核心接口：提示词 → 美术资产包
    GET  /api/info       - 服务信息
    GET  /api/styles     - 可用风格列表
    GET  /api/types      - 可用角色类型
    GET  /api/backends   - AI图像生成后端列表
    GET  /preview/<id>   - 预览页（简单HTML）
"""

import json
import sys
import os
import html as html_module
import traceback
import base64
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from artpipe.engine import CharacterEngine, STYLES, CHAR_TYPES
from artpipe.exporter import AssetExporter


# ---- In-memory store for generated assets (production: use Redis/DB) ----
asset_store = {}


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """支持并发请求的HTTP服务器（每个请求独立线程）"""
    daemon_threads = True


class ArtPipeAPI(BaseHTTPRequestHandler):
    """ArtPipe REST API Handler"""

    engine = CharacterEngine()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        
        if path == "/api/info":
            self._json({
                "name": "ArtPipe API",
                "version": "0.3.0",
                "description": "AI-Powered 2D Game Character Asset Generation",
                "render_modes": ["procedural", "ai", "hybrid"],
                "endpoints": {
                    "POST /api/generate": "Generate character from prompt (supports AI rendering)",
                    "GET  /api/info": "API information",
                    "GET  /api/styles": "Available art styles",
                    "GET  /api/types": "Available character types",
                    "GET  /api/backends": "AI image generation backends",
                    "GET  /preview/{id}": "Preview generated character",
                },
            })
        elif path == "/api/styles":
            self._json({
                "styles": {
                    k: {"name": v["name"], "pixel_size": v["pixel_size"]}
                    for k, v in STYLES.items()
                }
            })
        elif path == "/api/types":
            self._json({
                "types": {
                    k: {"name": v["name"]}
                    for k, v in CHAR_TYPES.items()
                }
            })
        elif path == "/api/backends":
            from artpipe.sd_client import AIGenerator
            self._json({"backends": AIGenerator.get_backends()})
        elif path.startswith("/preview/"):
            char_id = path.split("/")[-1]
            self._serve_preview(char_id)
        elif path == "/" or path == "/index.html":
            self._serve_landing()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        
        if path == "/api/generate":
            self._handle_generate()
        elif path == "/api/export":
            self._handle_export()
        else:
            self.send_error(404, "Not Found")

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- Core: Generate ----
    def _handle_generate(self):
        """
        POST /api/generate
        
        Request Body:
        {
            "prompt": "一个穿红色斗篷的精灵猎人",  // 必填
            "style": "cartoon",                    // 可选: pixel|cartoon|anime|western|dark
            "char_type": "archer",                 // 可选: warrior|mage|archer|rogue|healer|monster|npc
            "seed": 12345,                         // 可选: 固定种子可复现
            "render_mode": "ai",                   // 可选: procedural|ai|hybrid (默认procedural)
            "ai_backend": "pollinations",          // 可选: AI后端 (默认pollinations)
            "formats": ["spine","unity","godot"],  // 可选: 默认全部格式
            "include_png": true                    // 可选: 是否返回base64 PNG
        }
        """
        try:
            body = self._read_body()
            if not body:
                self._error(400, "Request body required")
                return
            
            data = json.loads(body) if isinstance(body, str) else body
            prompt = data.get("prompt", "").strip()
            
            if not prompt:
                self._error(400, "Field 'prompt' is required")
                return
            
            # v0.3: render_mode
            render_mode = data.get("render_mode", "procedural")
            if render_mode not in ("procedural", "ai", "hybrid"):
                self._error(400, f"Invalid render_mode: {render_mode}. Use: procedural|ai|hybrid")
                return
            
            # Generate character
            result = self.engine.generate(
                prompt=prompt,
                style=data.get("style"),
                char_type=data.get("char_type"),
                seed=data.get("seed"),
                render_mode=render_mode,
                ai_backend=data.get("ai_backend", "pollinations"),
            )
            
            # Export formats
            formats = data.get("formats", ["spine", "unity", "godot", "spritesheet"])
            exporter = AssetExporter(result)
            all_exports = exporter.export_all()
            
            exports = {}
            for fmt in formats:
                if fmt in all_exports:
                    exports[fmt] = all_exports[fmt]
            
            result["exports"] = exports
            result["preview_url"] = f"/preview/{result['id']}"
            
            # Optionally strip PNG
            if not data.get("include_png", True):
                del result["spritesheet"]["png_base64"]
            
            # Store for preview
            asset_store[result["id"]] = result
            
            self._json(result, status=201)
            
            ai_info = f" | ai_image={result.get('ai_image', {}).get('backend', 'none')}" if result.get("ai_image") else ""
            print(f"[ArtPipe] Generated: {result['id']} | mode={result.get('render_mode','procedural')} | style={result['style']} | type={result['char_type']} | {len(exports)} exports{ai_info}")
            
        except json.JSONDecodeError:
            self._error(400, "Invalid JSON in request body")
        except Exception as e:
            traceback.print_exc()
            self._error(500, f"Generation failed: {str(e)}")

    def _handle_export(self):
        """POST /api/export - 对已生成的角色重新导出指定格式"""
        try:
            data = json.loads(self._read_body())
            char_id = data.get("id")
            formats = data.get("formats", ["spine", "unity", "godot", "spritesheet"])
            
            if char_id not in asset_store:
                self._error(404, f"Character {char_id} not found. Generate first via POST /api/generate")
                return
            
            char = asset_store[char_id]
            exporter = AssetExporter(char)
            all_exports = exporter.export_all()
            
            exports = {fmt: all_exports[fmt] for fmt in formats if fmt in all_exports}
            self._json({"id": char_id, "exports": exports})
            
        except Exception as e:
            self._error(500, str(e))

    # ---- Preview ----
    def _serve_preview(self, char_id):
        if char_id not in asset_store:
            self.send_error(404, "Character not found")
            return
        
        char = asset_store[char_id]
        png_b64 = char.get("spritesheet", {}).get("png_base64", "")
        ai_img = char.get("ai_image", {})
        ai_section = ""
        if ai_img:
            ai_section = f"""
<div style="margin-top:24px;padding-top:16px;border-top:1px solid #333;">
<h3>🎨 AI Generated Image</h3>
<p><b>Backend:</b> {html_module.escape(str(ai_img.get('backend','')))} | <b>Time:</b> {html_module.escape(str(ai_img.get('generation_time','')))}s | <b>Size:</b> {ai_img.get('size',0)//1024}KB</p>
<img src="data:image/{html_module.escape(ai_img.get('format','jpeg').lower())};base64,{ai_img.get('image_base64','')}" 
     style="image-rendering:auto;border:2px solid #333;border-radius:8px;max-width:512px;" alt="ai-generated">
</div>"""
        
        # v0.3.17: XSS修复 — 所有用户可控字段用html.escape转义
        safe_id = html_module.escape(char_id)
        safe_prompt = html_module.escape(char.get("prompt", ""))
        safe_style = html_module.escape(char.get("style_name", ""))
        safe_type = html_module.escape(char.get("char_type_name", ""))
        safe_seed = html_module.escape(str(char.get("seed", "")))
        safe_mode = html_module.escape(char.get('render_mode', 'procedural').upper())
        safe_anims = ", ".join(html_module.escape(a) for a in char.get("animations", {}).keys())
        safe_exports = ", ".join(html_module.escape(e) for e in char.get("exports", {}).keys())
        
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ArtPipe Preview - {safe_id}</title>
<style>
body {{ background:#1a1a2e; color:#eee; font-family:system-ui; display:flex; justify-content:center; padding:40px; }}
.card {{ background:#16213e; border-radius:12px; padding:24px; max-width:700px; }}
img {{ image-rendering:pixelated; border:2px solid #333; border-radius:8px; max-width:100%; }}
.info {{ margin-top:16px; font-size:14px; color:#aaa; }}
.info b {{ color:#eee; }}
.badge {{ display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold; }}
.badge-ai {{ background:#e94560;color:white; }}
.badge-proc {{ background:#0f3460;color:#53a8b6; }}
</style></head><body>
<div class="card">
<h2>ArtPipe Preview <span class="badge {'badge-ai' if ai_img else 'badge-proc'}">{safe_mode}</span></h2>
<p><b>Prompt:</b> {safe_prompt}</p>
<p><b>Style:</b> {safe_style} | <b>Type:</b> {safe_type} | <b>Seed:</b> {safe_seed}</p>
<h3>SpriteSheet (Procedural)</h3>
<img src="data:image/png;base64,{png_b64}" alt="spritesheet">
{ai_section}
<div class="info">
<p>Animations: {safe_anims}</p>
<p>Palette: {char.get("palette",[])}</p>
<p>Exports: {safe_exports}</p>
</div></div></body></html>"""
        
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._set_cors()
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_landing(self):
        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ArtPipe API</title>
<style>
body { background:#1a1a2e; color:#eee; font-family:monospace; display:flex; justify-content:center; padding:80px 20px; }
pre { background:#0f3460; padding:24px; border-radius:8px; max-width:700px; overflow-x:auto; line-height:1.6; }
h1 { color:#e94560; }
a { color:#53a8b6; }
</style></head><body><pre>
<h1>ArtPipe API v0.3.0</h1>

AI-Powered 2D Game Character Asset Generation

<b>Quick Start:</b>

  curl -X POST http://localhost:8080/api/generate \\
    -H "Content-Type: application/json" \\
    -d '{"prompt": "一个穿红袍的法师", "render_mode": "ai"}'

<b>Render Modes (v0.3):</b>

  procedural  Zero-latency procedural rendering (default)
  ai          AI image generation (Pollinations/Stability)
  hybrid      AI reference + procedural spritesheet

<b>Endpoints:</b>

  POST /api/generate   Generate character from text prompt
  GET  /api/info       API information
  GET  /api/styles     Available art styles
  GET  /api/types      Available character types
  GET  /api/backends   AI image generation backends
  GET  /preview/{id}   Preview generated character

<b>GitHub:</b> <a href="https://github.com/kongshan001/art-pipe">kongshan001/art-pipe</a>
</pre></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    # ---- Helpers ----
    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        return self.rfile.read(length).decode("utf-8")

    def _json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        self._json({"error": True, "status": status, "message": message}, status)

    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, fmt, *args):
        pass  # Suppress default logging


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    # v0.3.17: ThreadingHTTPServer 支持并发请求
    server = ThreadingHTTPServer(("0.0.0.0", port), ArtPipeAPI)
    print(f"ArtPipe API v0.3.0 | http://localhost:{port}")
    print(f"POST /api/generate  |  prompt -> assets (procedural + AI)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArtPipe stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
