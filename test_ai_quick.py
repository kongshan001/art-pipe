#!/usr/bin/env python3
"""ArtPipe v0.3 AI Generation Quick Test"""
import sys, os, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from artpipe.engine import CharacterEngine

engine = CharacterEngine()

# === Test 1: AI mode ===
print("=== Test 1: AI mode (pixel mage) ===")
try:
    r = engine.generate(
        "像素风蓝色法师，手持法杖",
        render_mode="ai",
        seed=42
    )
    print(f"  ID: {r['id']}")
    print(f"  Mode: {r.get('render_mode')}")
    
    ai = r.get("ai_image", {})
    if ai and ai.get("image_base64"):
        print(f"  AI Backend: {ai.get('backend')}")
        print(f"  AI Time: {ai.get('generation_time')}s")
        print(f"  AI Size: {ai.get('size', 0) // 1024}KB")
        print(f"  AI Format: {ai.get('format')}")
        
        ai_path = "/tmp/artpipe_ai_pixel.jpg"
        with open(ai_path, "wb") as f:
            f.write(base64.b64decode(ai["image_base64"]))
        print(f"  Saved: {ai_path} ({os.path.getsize(ai_path)//1024}KB)")
    else:
        print("  AI: NO IMAGE")
    
    ss_path = "/tmp/artpipe_ss_pixel.png"
    with open(ss_path, "wb") as f:
        f.write(base64.b64decode(r["spritesheet"]["png_base64"]))
    print(f"  SpriteSheet: {ss_path}")
    print("  RESULT: SUCCESS ✓")
    
except Exception as ex:
    import traceback
    print(f"  ERROR: {ex}")
    traceback.print_exc()

# === Test 2: Hybrid mode ===
print("\n=== Test 2: Hybrid mode (anime rogue) ===")
try:
    r2 = engine.generate(
        "日式RPG绿色盗贼，穿皮甲",
        render_mode="hybrid",
        seed=99
    )
    print(f"  ID: {r2['id']}")
    print(f"  Mode: {r2.get('render_mode')}")
    
    ai2 = r2.get("ai_image", {})
    if ai2 and ai2.get("image_base64"):
        print(f"  AI Time: {ai2.get('generation_time')}s | Size: {ai2.get('size', 0)//1024}KB")
        ai2_path = "/tmp/artpipe_ai_hybrid.jpg"
        with open(ai2_path, "wb") as f:
            f.write(base64.b64decode(ai2["image_base64"]))
        print(f"  Saved: {ai2_path}")
    
    ss2_path = "/tmp/artpipe_ss_hybrid.png"
    with open(ss2_path, "wb") as f:
        f.write(base64.b64decode(r2["spritesheet"]["png_base64"]))
    print(f"  SpriteSheet: {ss2_path}")
    print("  RESULT: SUCCESS ✓")
    
except Exception as ex:
    import traceback
    print(f"  ERROR: {ex}")
    traceback.print_exc()

print("\n=== All tests complete ===")
