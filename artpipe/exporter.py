"""
ArtPipe 多格式导出器
支持 Spine JSON / SpriteSheet元数据 / Unity Package / Godot .tres
"""
import json
import time


class AssetExporter:
    
    def __init__(self, character_data):
        """
        character_data: generate() 返回的完整数据
        """
        self.char = character_data

    def export_all(self):
        """导出所有格式"""
        return {
            "spine": self.export_spine(),
            "unity": self.export_unity(),
            "godot": self.export_godot(),
            "spritesheet": self.export_spritesheet_meta(),
        }

    def export_spine(self):
        """生成 Spine 兼容的骨骼 JSON 项目文件"""
        c = self.char
        sk = c["skeleton"]
        ts = c["generated_at"][:10].replace("-", "")
        name = f"artpipe_{c['char_type']}_{ts}"

        # Spine JSON format (simplified but compatible)
        spine = {
            "skeleton": {
                "hash": str(c["seed"]),
                "spine": "4.1",
                "x": -c["canvas_size"]["width"] // 2,
                "y": -c["canvas_size"]["height"],
                "width": c["canvas_size"]["width"],
                "height": c["canvas_size"]["height"],
                "images": "./images/",
                "audio": "",
            },
            "bones": [],
            "slots": [],
            "skins": {"default": {"attachments": {}}},
            "animations": {},
        }

        # Bones
        for b in sk["bones"]:
            bone = {
                "name": b["name"],
                "x": b["x"],
                "y": b["y"],
            }
            if b["parent"]:
                bone["parent"] = b["parent"]
            if b["name"] == "root":
                bone["length"] = 10
            spine["bones"].append(bone)

        # Slots
        for i, s in enumerate(sk["slots"]):
            spine["slots"].append({
                "name": s["name"],
                "bone": s["bone"],
                "order": i,
                "color": "FFFFFFFF",
            })

        # Animations (rotation-based, simplified)
        anim_names = list(c["animations"].keys())
        for anim_name in anim_names:
            anim_data = c["animations"][anim_name]
            spine_anim = {"bones": {}}

            if anim_name == "idle":
                spine_anim["bones"]["head"] = {
                    "rotation": [
                        {"time": 0, "value": 0, "curve": "linear"},
                        {"time": anim_data["frame_count"] / anim_data["fps"] / 2, "value": 3},
                        {"time": anim_data["frame_count"] / anim_data["fps"], "value": 0},
                    ]
                }
            elif anim_name == "walk":
                cycle = anim_data["frame_count"] / anim_data["fps"]
                spine_anim["bones"]["left_upper_leg"] = {
                    "rotation": [
                        {"time": 0, "value": -20},
                        {"time": cycle / 2, "value": 20},
                        {"time": cycle, "value": -20},
                    ]
                }
                spine_anim["bones"]["right_upper_leg"] = {
                    "rotation": [
                        {"time": 0, "value": 20},
                        {"time": cycle / 2, "value": -20},
                        {"time": cycle, "value": 20},
                    ]
                }
            elif anim_name == "attack":
                cycle = anim_data["frame_count"] / anim_data["fps"]
                spine_anim["bones"]["right_upper_arm"] = {
                    "rotation": [
                        {"time": 0, "value": 0},
                        {"time": cycle * 0.3, "value": -60},
                        {"time": cycle * 0.5, "value": 30},
                        {"time": cycle, "value": 0},
                    ]
                }
            elif anim_name == "die":
                cycle = anim_data["frame_count"] / anim_data["fps"]
                spine_anim["bones"]["root"] = {
                    "rotation": [
                        {"time": 0, "value": 0},
                        {"time": cycle, "value": 90},
                    ]
                }

            spine["animations"][anim_name] = spine_anim

        return {
            "filename": f"{name}_spine.json",
            "content": json.dumps(spine, indent=2, ensure_ascii=False),
            "format": "spine",
        }

    def export_unity(self):
        """生成 Unity Package 元数据 + C# 控制器脚本"""
        c = self.char
        ts = c["generated_at"][:10].replace("-", "")
        name = f"ArtPipe{c['char_type_name'].title()}{ts}"
        anim_names = list(c["animations"].keys())
        
        # Unity meta JSON
        meta = {
            "name": name,
            "version": "0.2.0",
            "unityVersion": "2022.3",
            "generatedAt": c["generated_at"],
            "prefab": f"{name}.prefab",
            "animatorController": {
                "name": f"{name}.controller",
                "parameters": [{"name": "Speed", "type": "Float"}, {"name": "Attack", "type": "Trigger"}],
                "layers": [{
                    "name": "Base",
                    "states": [{"name": a, "motion": f"{name}_{a}.clip"} for a in anim_names],
                    "transitions": [
                        {"from": "idle", "to": "walk", "condition": "Speed > 0.1"},
                        {"from": "walk", "to": "run", "condition": "Speed > 2"},
                        {"from": "run", "to": "walk", "condition": "Speed < 2"},
                        {"from": "*", "to": "attack", "condition": "Attack"},
                        {"from": "*", "to": "hurt", "condition": "Hurt"},
                    ],
                }],
            },
            "spritesheet": {
                "texture": f"{name}_Atlas.png",
                "size": f"{c['spritesheet']['cols'] * c['canvas_size']['width']}x{c['spritesheet']['rows'] * c['canvas_size']['height']}",
                "frames": c["spritesheet"]["total_frames"],
            },
        }
        
        # C# controller script
        cs = f"""// ArtPipe Auto-Generated Character Controller
// Generated at: {c["generated_at"]}
// Prompt: {c["prompt"]}

using UnityEngine;

public class {name}Controller : MonoBehaviour
{{
    private Animator animator;
    private SpriteRenderer spriteRenderer;
    
    public Sprite[] sprites;
    public float speed;
    
    void Start()
    {{
        animator = GetComponent<Animator>();
        spriteRenderer = GetComponent<SpriteRenderer>();
    }}
    
    void Update()
    {{
        float h = Input.GetAxisRaw("Horizontal");
        float v = Input.GetAxisRaw("Vertical");
        speed = new Vector2(h, v).magnitude;
        
        animator.SetFloat("Speed", speed);
        
        if (h != 0)
            spriteRenderer.flipX = h < 0;
        
        if (Input.GetMouseButtonDown(0))
            animator.SetTrigger("Attack");
    }}
    
    // Public API
    public void PlayAnimation(string animName)
    {{
        animator.Play(animName);
    }}
    
    public void SetDirection(bool facingLeft)
    {{
        spriteRenderer.flipX = facingLeft;
    }}
}}
"""
        
        return {
            "filename": f"{name}_unity.json",
            "content": json.dumps(meta, indent=2, ensure_ascii=False),
            "script": cs,
            "script_filename": f"{name}Controller.cs",
            "format": "unity",
        }

    def export_godot(self):
        """生成 Godot .tres 场景文件"""
        c = self.char
        ts = c["generated_at"][:10].replace("-", "")
        name = f"artpipe_{c['char_type']}_{ts}"
        anim_names = list(c["animations"].keys())
        
        # .tres resource file
        tres = f"""[gd_scene load_steps=3 format=3 uid="uid://artpipe/{name}"]

[ext_resource type="Texture2D" uid="uid://artpipe/{name}_atlas" path="res://assets/{name}_atlas.png" id="1"]
[ext_resource type="Script" path="res://scripts/{name}_controller.gd" id="2"]

[node name="{name}" type="CharacterBody2D"]
script = ExtResource("2")

[node name="Sprite2D" type="Sprite2D" parent="."]
texture = ExtResource("1")
hframes = {c["spritesheet"]["total_frames"]}

[node name="AnimationPlayer" type="AnimationPlayer" parent="."]
"""
        # Add animations
        for i, anim_name in enumerate(anim_names):
            anim = c["animations"][anim_name]
            frame_start = c["spritesheet"]["frame_map"][anim_name]["start"]
            frame_count = anim["frame_count"]
            duration = frame_count / anim["fps"]
            fps_val = anim["fps"]
            times_str = ", ".join(f"{t/fps_val:.2f}" for t in range(frame_count))
            values_str = ", ".join(str(frame_start + t) for t in range(frame_count))
            loop_str = str(anim["loop"]).lower()
            tres += f"""
[animation id="{i}" name="{anim_name}" length={duration:.2f} loop={loop_str}]
tracks/0/type = "value"
tracks/0/path = "Sprite2D:frame"
tracks/0/keys = {{
"times": [{times_str}],
"values": [{values_str}]
}}
"""
        
        # GDScript controller
        gd = f"""# ArtPipe Auto-Generated Character Controller
# Generated at: {c["generated_at"]}

extends CharacterBody2D

@export var speed: float = 200.0
@export var jump_velocity: float = -400.0

@onready var sprite = $Sprite2D
@onready var anim_player = $AnimationPlayer

var facing_left: bool = false

func _physics_process(delta: float) -> void:
    var direction = Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
    velocity = direction * speed
    
    if direction.x != 0:
        facing_left = direction.x < 0
        sprite.flip_h = facing_left
    
    # Animation state machine
    if Input.is_action_just_pressed("ui_accept"):
        anim_player.play("attack")
    elif direction.length() > 0.5:
        anim_player.play("run")
    elif direction.length() > 0:
        anim_player.play("walk")
    else:
        anim_player.play("idle")
    
    move_and_slide()

func play_animation(name: String) -> void:
    anim_player.play(name)
"""
        
        return {
            "filename": f"{name}.tscn",
            "content": tres,
            "script": gd,
            "script_filename": f"{name}_controller.gd",
            "format": "godot",
        }

    def export_spritesheet_meta(self):
        """导出 SpriteSheet 元数据（配合 PNG 使用）"""
        c = self.char
        
        frames = []
        for anim_name, anim_info in c["animations"].items():
            start = c["spritesheet"]["frame_map"][anim_name]["start"]
            count = anim_info["frame_count"]
            for i in range(count):
                col = (start + i) % c["spritesheet"]["cols"]
                row = (start + i) // c["spritesheet"]["cols"]
                fw = c["canvas_size"]["width"]
                fh = c["canvas_size"]["height"]
                frames.append({
                    "filename": f"{anim_name}_{i:03d}.png",
                    "frame": {"x": col * fw, "y": row * fh, "w": fw, "h": fh},
                    "rotated": False,
                    "trimmed": False,
                    "spriteSourceSize": {"x": 0, "y": 0, "w": fw, "h": fh},
                    "sourceSize": {"w": fw, "h": fh},
                    "duration": int(1000 / anim_info["fps"]),
                    "animation": anim_name,
                })
        
        meta = {
            "meta": {
                "app": "ArtPipe",
                "version": "0.2.0",
                "image": f"artpipe_spritesheet.png",
                "size": {
                    "w": c["spritesheet"]["cols"] * c["canvas_size"]["width"],
                    "h": c["spritesheet"]["rows"] * c["canvas_size"]["height"],
                },
                "scale": 1,
                "frameTags": [
                    {"name": anim, "from": c["spritesheet"]["frame_map"][anim]["start"],
                     "to": c["spritesheet"]["frame_map"][anim]["start"] + c["animations"][anim]["frame_count"] - 1,
                     "direction": "forward"}
                    for anim in c["animations"]
                ],
            },
            "frames": frames,
        }
        
        return {
            "filename": "spritesheet_meta.json",
            "content": json.dumps(meta, indent=2, ensure_ascii=False),
            "format": "spritesheet",
        }
