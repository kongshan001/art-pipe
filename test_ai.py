#!/usr/bin/env python3
"""ArtPipe v0.3 AI Generation Test"""
import sys, os, base64, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from artpipe.engine import CharacterEngine

engine = CharacterEngine()

tests = [
    ("pixel", "像素风蓝色法师，手持法杖，穿着蓝色长袍", 420),
    ("anime", "日式RPG绿色盗贼，穿皮甲，双持匕首", 421),
    ("dark",  "暗黑红色恶魔boss，巨大双角，黑红铠甲", 422),
]

for style, prompt, seed in tests:
    print(f"\n=== Testing: {style} mode=ai seed={seed} ===")
    print(f"Prompt: {prompt}")
    
    r = engine.generate(prompt, render_mode="ai", seed=seed)
    
    print(f"  ID: {r['id']}")
    print(f"  Mode: {r.get('render_mode')}")
    print(f"  Style: {r['style_name']} | Type: {r['char_type_name']}")
    
    ai = r.get("ai_image", {})
    if ai:
        print(f"  AI Backend: {ai.get('backend')}")
        print(f"  AI Time: {ai.get('generation_time')}s")
        print(f"  AI Size: {ai.get('size', 0) // 1024}KB")
        print(f"  AI Format: {ai.get('format')}")
        
        # Save AI image
        ai_path = f"/tmp/artpipe_ai_{style}.jpg"
        with open(ai_path, "wb") as f:
            f.write(base64.b64decode(ai["image_base64"]))
        print(f"  AI Image saved: {ai_path} ({os.path.getsize(ai_path)//1024}KB)")
    else:
        print("  AI: FAILED - no image returned")
    
    # Save spritesheet
    ss_path = f"/tmp/artpipe_ss_{style}.png"
    with open(ss_path, "wb") as f:
        f.write(base64.b64decode(r["spritesheet"]["png_base64"]))
    print(f"  SpriteSheet saved: {ss_path}")
    
    print(f"  Animations: {list(r['animations'].keys())}")

print("\n=== All tests complete ===")
