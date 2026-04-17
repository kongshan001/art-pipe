/**
 * ArtPipe - 多格式导出引擎
 * 支持 Unity / Spine / SpriteSheet / Godot 导出
 */

class AssetExporter {
    constructor(character, renderer) {
        this.character = character;
        this.renderer = renderer;
    }

    async export(format) {
        const c = this.character;
        const timestamp = new Date().toISOString().slice(0,10).replace(/-/g,'');
        const baseName = `artpipe_${c.config.type}_${c.style.pixelSize > 1 ? 'pixel' : 'smooth'}_${timestamp}`;

        switch (format) {
            case 'unity': return this.exportUnity(baseName);
            case 'spine': return this.exportSpine(baseName);
            case 'spritesheet': return this.exportSpriteSheet(baseName);
            case 'godot': return this.exportGodot(baseName);
        }
    }

    exportUnity(name) {
        const c = this.character;
        const animNames = Object.keys(c.animations);
        
        const meta = {
            name,
            format: 'Unity Package',
            version: '0.1.0',
            unityVersion: '2022.3',
            generatedAt: new Date().toISOString(),
            contents: {
                prefabs: [`${name}.prefab`],
                animatorController: `${name}.controller`,
                animations: animNames.map(a => `Animations/${name}_${a}.anim`),
                sprites: `Textures/${name}_Atlas.png`,
                materials: `Materials/${name}_Mat.mat`,
                script: `Scripts/${name}Controller.cs`
            }
        };

        const csCode = `// ArtPipe Auto-Generated Character Controller
using UnityEngine;

public class ${this.className(name)}Controller : MonoBehaviour
{
    private Animator animator;
    
    void Start()
    {
        animator = GetComponent<Animator>();
    }
    
    public void PlayIdle() => animator.Play("idle");
    public void PlayWalk() => animator.Play("walk");
    public void PlayRun() => animator.Play("run");
    public void PlayAttack() => animator.Play("attack");
    public void PlayHurt() => animator.Play("hurt");
    public void PlayDie() => animator.Play("die");
    
    public void SetSpeed(float speed)
    {
        animator.speed = speed;
    }
}`;

        const animatorYaml = `%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!91 &9100000
AnimatorController:
  m_Name: ${name}
  m_AnimatorParameters:
${animNames.map((a, i) => `  - m_Name: ${a}
    m_Type: 9
    m_DefaultFloat: 0`).join('
')}
  m_AnimatorLayers:
  - m_Name: Base Layer
    m_StateMachine: {fileID: 110700000}
    m_Mask: {fileID: 0}`;

        return {
            meta,
            files: {
                'controller.cs': csCode,
                'animator.controller.yaml': animatorYaml,
                'README.md': this.generateReadme(name, 'Unity')
            }
        };
    }

    exportSpine(name) {
        const c = this.character;
        const bones = c.bones;
        const anims = c.animations;

        const skeletonJson = {
            skeleton: { hash: c.seed, spine: '4.1', width: 200, height: 400 },
            bones: bones.map(b => ({
                name: b.name,
                parent: b.parent,
                x: b.x, y: -b.y,
                rotation: 0, scaleX: 1, scaleY: 1
            })),
            slots: c.parts.filter(p => p.layer > 0).map(p => ({
                name: p.name,
                bone: p.name === 'head' ? 'Head' : 
                      p.name === '左臂' ? 'L Arm' :
                      p.name === '右臂' ? 'R Arm' :
                      p.name.includes('腿') ? (p.name.includes('左') ? 'L Leg' : 'R Leg') : 'Spine',
                attachment: p.name
            })),
            skins: [{ name: 'default', attachments: {} }],
            animations: {}
        };

        // Convert animation frames to Spine timeline format
        for (const [animName, anim] of Object.entries(anims)) {
            const spineAnim = { bones: {} };
            for (const bone of bones) {
                spineAnim.bones[bone.name] = { 
                    translation: anim.frames.map((f, i) => ({
                        time: i / anim.fps,
                        x: (f.body_x || 0) * 0.5,
                        y: (f.body_y || 0) * 0.5
                    }))
                };
            }
            skeletonJson.animations[animName] = spineAnim;
        }

        const atlasStr = `${name}.png
size: 512,512
format: RGBA8888
filter: Linear,Linear
repeat: none
${c.parts.map(p => p.name).join('\n')}`;

        return {
            meta: {
                name,
                format: 'Spine Project',
                version: '4.1',
                generatedAt: new Date().toISOString(),
                contents: {
                    skeleton: `${name}.skel`,
                    atlas: `${name}.atlas`,
                    texture: `${name}.png`
                }
            },
            files: {
                'skeleton.json': JSON.stringify(skeletonJson, null, 2),
                'atlas.txt': atlasStr,
                'README.md': this.generateReadme(name, 'Spine')
            }
        };
    }

    async exportSpriteSheet(name) {
        const c = this.character;
        const anims = c.animations;
        
        const animList = [];
        for (const [animName, anim] of Object.entries(anims)) {
            // Sample keyframes (every 5th frame)
            const keyframes = [];
            for (let i = 0; i < anim.frames.length; i += 3) {
                keyframes.push({
                    frame: i,
                    time: (i / anim.fps).toFixed(3)
                });
            }
            animList.push({
                name: animName,
                fps: anim.fps,
                loop: anim.loop,
                totalFrames: anim.frames.length,
                keyframes
            });
        }

        const spriteData = {
            meta: {
                app: 'ArtPipe',
                version: '0.1.0',
                image: `${name}_spritesheet.png`,
                size: { w: 2048, h: 2048 },
                scale: 1,
                format: 'RGBA8888'
            },
            frames: animList,
            frameSize: { w: 128, h: 128 },
            animations: animList.map(a => ({
                name: a.name,
                frames: a.keyframes.map(k => k.frame),
                loop: a.loop
            }))
        };

        return {
            meta: {
                name,
                format: 'Sprite Sheet',
                generatedAt: new Date().toISOString(),
                contents: {
                    spritesheet: `${name}_spritesheet.png`,
                    data: `${name}_data.json`
                }
            },
            files: {
                'spritesheet.json': JSON.stringify(spriteData, null, 2),
                'README.md': this.generateReadme(name, 'SpriteSheet')
            }
        };
    }

    exportGodot(name) {
        const c = this.character;
        const anims = Object.keys(c.animations);

        const sceneTscn = `[gd_scene load_steps=3 format=3]

[ext_resource type="Texture2D" path="res://textures/${name}.png" id="1"]
[ext_resource type="Script" path="res://scripts/${name}_controller.gd" id="2"]

[node name="${this.className(name)}" type="CharacterBody2D"]
script = ExtResource("2")

[node name="Sprite2D" type="Sprite2D" parent="."]
texture = ExtResource("1")
hframes = ${anims.length * 4}

[node name="AnimationPlayer" type="AnimationPlayer" parent="."]
${anims.map((a, i) => `"libraries/${i}/${a}" = ExtResource("${i + 3}")`).join('\n')}`;

        const gdScript = `# ArtPipe Auto-Generated Character Controller (Godot 4)
extends CharacterBody2D

@export var speed: float = 200.0
@export var jump_velocity: float = -400.0

@onready var sprite = $Sprite2D
@onready var anim_player = $AnimationPlayer

var current_anim: String = "idle"

func _physics_process(delta: float) -> void:
    # Handle animation
    if velocity.length() > 10:
        if Input.is_action_pressed("run"):
            play_anim("run")
        else:
            play_anim("walk")
    else:
        play_anim("idle")

func play_anim(anim_name: String) -> void:
    if current_anim != anim_name:
        current_anim = anim_name
        anim_player.play(anim_name)

func attack() -> void:
    anim_player.play("attack")
    await anim_player.animation_finished
    
func take_damage() -> void:
    anim_player.play("hurt")
    await anim_player.animation_finished

func die() -> void:
    anim_player.play("die")`;

        return {
            meta: {
                name,
                format: 'Godot Scene',
                version: '4.2',
                generatedAt: new Date().toISOString(),
                contents: {
                    scene: `${name}.tscn`,
                    script: `${name}_controller.gd`,
                    texture: `textures/${name}.png`
                }
            },
            files: {
                'scene.tscn': sceneTscn,
                'controller.gd': gdScript,
                'README.md': this.generateReadme(name, 'Godot')
            }
        };
    }

    generateReadme(name, format) {
        const c = this.character;
        return `# ${name} - ArtPipe Generated Asset

Generated by [ArtPipe](https://github.com/kongshan001/art-pipe) on ${new Date().toLocaleDateString()}

## Character Info
- **Style**: ${c.style.name}
- **Type**: ${c.type.name}
- **Parts**: ${c.parts.length}
- **Bones**: ${c.bones.length}
- **Animations**: ${Object.keys(c.animations).join(', ')}
- **Export Format**: ${format}

## Usage
Import the generated files into your ${format} project.
See the included controller script for animation playback.

## License
Generated by ArtPipe MVP. Free for personal and commercial use.
`;
    }

    className(name) {
        return name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join('');
    }

    downloadFile(content, filename) {
        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }
}

window.AssetExporter = AssetExporter;
