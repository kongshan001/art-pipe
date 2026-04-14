/**
 * ArtPipe - 程序化角色生成引擎
 * 基于Canvas 2D的程序化角色生成，无需GPU
 */

class CharacterGenerator {
    constructor() {
        this.rng = null;
        this.character = null;
    }

    seedRandom(seed) {
        let s = seed;
        this.rng = () => {
            s = (s * 16807 + 0) % 2147483647;
            return (s - 1) / 2147483646;
        };
    }

    generate(config) {
        const seed = this.hashString(config.description + config.style + config.type + Date.now());
        this.seedRandom(seed);

        const style = this.getStyleConfig(config.style);
        const type = this.getTypeConfig(config.type);
        const colors = this.extractColors(config);

        this.character = {
            id: 'char_' + Date.now(),
            config: { ...config },
            style,
            type,
            colors,
            parts: [],
            bones: [],
            animations: {},
            seed
        };

        this.generateParts();
        this.generateBones();
        this.generateAnimations();
        this.generateVariants();

        return this.character;
    }

    hashString(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash |= 0;
        }
        return Math.abs(hash) || 1;
    }

    getStyleConfig(style) {
        const styles = {
            pixel: {
                name: '像素风',
                pixelSize: 4,
                strokeWeight: 0,
                saturation: 0.8,
                outline: true,
                dither: true,
                palette: 'retro'
            },
            cartoon: {
                name: '卡通手绘',
                pixelSize: 1,
                strokeWeight: 3,
                saturation: 1.2,
                outline: true,
                dither: false,
                palette: 'vibrant'
            },
            anime: {
                name: '日式RPG',
                pixelSize: 1,
                strokeWeight: 2,
                saturation: 1.0,
                outline: true,
                dither: false,
                palette: 'anime'
            },
            western: {
                name: '欧美卡通',
                pixelSize: 1,
                strokeWeight: 4,
                saturation: 1.3,
                outline: true,
                dither: false,
                palette: 'bold'
            },
            dark: {
                name: '暗黑风',
                pixelSize: 1,
                strokeWeight: 2,
                saturation: 0.6,
                outline: true,
                dither: false,
                palette: 'dark'
            }
        };
        return styles[style] || styles.pixel;
    }

    getTypeConfig(type) {
        const types = {
            warrior: { name: '战士', bodyType: 'stocky', weapon: 'sword', armor: true, helmet: true },
            mage: { name: '法师', bodyType: 'slim', weapon: 'staff', armor: false, robe: true, hat: true },
            archer: { name: '弓箭手', bodyType: 'athletic', weapon: 'bow', armor: 'light', hood: true },
            rogue: { name: '盗贼', bodyType: 'slim', weapon: 'dagger', armor: 'light', mask: true },
            healer: { name: '治疗者', bodyType: 'slim', weapon: 'none', armor: false, robe: true, halo: true },
            monster: { name: '怪物', bodyType: 'large', weapon: 'claw', armor: false, horns: true },
            npc: { name: 'NPC', bodyType: 'normal', weapon: 'none', armor: false }
        };
        return types[type] || types.warrior;
    }

    extractColors(config) {
        const primary = config.primaryColor || '#e74c3c';
        const r = parseInt(primary.slice(1,3),16), g = parseInt(primary.slice(3,5),16), b = parseInt(primary.slice(5,7),16);
        
        const shift = (c, amount) => Math.max(0, Math.min(255, c + amount));
        
        return {
            primary,
            secondary: `rgb(${shift(r,-40)},${shift(g,-40)},${shift(b,-40)})`,
            highlight: `rgb(${shift(r,60)},${shift(g,60)},${shift(b,60)})`,
            shadow: `rgb(${shift(r,-80)},${shift(g,-80)},${shift(b,-80)})`,
            skin: ['#f4c898','#d4a574','#c49a6c','#8d6e4c'][Math.floor(this.rng()*4)],
            hair: ['#2c1810','#5c3317','#c49a6c','#f4d03f','#a93226'][Math.floor(this.rng()*5)],
            eye: ['#2c3e50','#27ae60','#2980b9','#c0392b'][Math.floor(this.rng()*4)],
            schemes: this.generateColorSchemes(primary)
        };
    }

    generateColorSchemes(primary) {
        const schemes = [primary];
        const variations = ['#e74c3c','#3498db','#2ecc71','#9b59b6','#f39c12','#1abc9c','#e67e22','#2c3e50'];
        const r = this.rng;
        for (let i = 0; i < 5; i++) {
            schemes.push(variations[Math.floor(r() * variations.length)]);
        }
        return schemes;
    }

    generateParts() {
        const c = this.character;
        const s = c.style;
        const p = s.pixelSize;

        c.parts = [
            { id: 'shadow', name: '阴影', layer: 0 },
            { id: 'body_back', name: '身体后层', layer: 1 },
            { id: 'legs', name: '腿部', layer: 2 },
            { id: 'torso', name: '躯干', layer: 3 },
            { id: 'arm_l', name: '左臂', layer: 4 },
            { id: 'head', name: '头部', layer: 5 },
            { id: 'hair', name: '头发', layer: 6 },
            { id: 'face', name: '面部', layer: 7 },
            { id: 'arm_r', name: '右臂', layer: 8 },
            { id: 'weapon', name: '武器', layer: 9 },
            { id: 'effect', name: '特效', layer: 10 }
        ];
    }

    generateBones() {
        const c = this.character;
        c.bones = [
            { id: 'root', name: 'Root', parent: null, x: 0, y: 0 },
            { id: 'hip', name: 'Hip', parent: 'root', x: 0, y: 40 },
            { id: 'spine', name: 'Spine', parent: 'hip', x: 0, y: -30 },
            { id: 'chest', name: 'Chest', parent: 'spine', x: 0, y: -25 },
            { id: 'neck', name: 'Neck', parent: 'chest', x: 0, y: -15 },
            { id: 'head', name: 'Head', parent: 'neck', x: 0, y: -30 },
            { id: 'arm_l', name: 'L Arm', parent: 'chest', x: -25, y: -10 },
            { id: 'arm_r', name: 'R Arm', parent: 'chest', x: 25, y: -10 },
            { id: 'hand_l', name: 'L Hand', parent: 'arm_l', x: 0, y: 30 },
            { id: 'hand_r', name: 'R Hand', parent: 'arm_r', x: 0, y: 30 },
            { id: 'leg_l', name: 'L Leg', parent: 'hip', x: -12, y: 0 },
            { id: 'leg_r', name: 'R Leg', parent: 'hip', x: 12, y: 0 },
            { id: 'foot_l', name: 'L Foot', parent: 'leg_l', x: 0, y: 40 },
            { id: 'foot_r', name: 'R Foot', parent: 'leg_r', x: 0, y: 40 },
            { id: 'weapon', name: 'Weapon', parent: 'hand_r', x: 5, y: 20 }
        ];
    }

    generateAnimations() {
        const c = this.character;
        c.animations = {
            idle: this.createIdleAnim(),
            walk: this.createWalkAnim(),
            run: this.createRunAnim(),
            attack: this.createAttackAnim(),
            hurt: this.createHurtAnim(),
            die: this.createDieAnim()
        };
    }

    createIdleAnim() {
        const frames = [];
        for (let i = 0; i < 60; i++) {
            const breath = Math.sin(i / 60 * Math.PI * 2) * 3;
            frames.push({
                body_y: breath,
                head_y: breath * 0.8,
                arm_l_angle: Math.sin(i / 60 * Math.PI * 2) * 2,
                arm_r_angle: -Math.sin(i / 60 * Math.PI * 2) * 2,
                leg_l_angle: 0,
                leg_r_angle: 0,
                weapon_angle: Math.sin(i / 60 * Math.PI * 2) * 2
            });
        }
        return { name: 'Idle', frames, fps: 30, loop: true };
    }

    createWalkAnim() {
        const frames = [];
        for (let i = 0; i < 30; i++) {
            const t = i / 30 * Math.PI * 2;
            frames.push({
                body_y: Math.abs(Math.sin(t)) * -5,
                head_y: Math.abs(Math.sin(t)) * -4,
                arm_l_angle: Math.sin(t) * 15,
                arm_r_angle: -Math.sin(t) * 15,
                leg_l_angle: Math.sin(t) * 20,
                leg_r_angle: -Math.sin(t) * 20,
                weapon_angle: Math.sin(t) * 5
            });
        }
        return { name: 'Walk', frames, fps: 30, loop: true };
    }

    createRunAnim() {
        const frames = [];
        for (let i = 0; i < 20; i++) {
            const t = i / 20 * Math.PI * 2;
            frames.push({
                body_y: Math.abs(Math.sin(t)) * -8,
                body_x: Math.sin(t) * 3,
                head_y: Math.abs(Math.sin(t)) * -7,
                arm_l_angle: Math.sin(t) * 30,
                arm_r_angle: -Math.sin(t) * 30,
                leg_l_angle: Math.sin(t) * 35,
                leg_r_angle: -Math.sin(t) * 35,
                weapon_angle: Math.sin(t) * 10
            });
        }
        return { name: 'Run', frames, fps: 30, loop: true };
    }

    createAttackAnim() {
        const frames = [];
        // Wind up (frames 0-10)
        for (let i = 0; i < 10; i++) {
            frames.push({
                body_y: 0,
                arm_r_angle: -i * 6,
                weapon_angle: -i * 4,
                arm_l_angle: i * 2,
                leg_l_angle: 0, leg_r_angle: 0,
                body_x: -i * 0.5
            });
        }
        // Swing (frames 10-18)
        for (let i = 0; i < 8; i++) {
            const p = i / 7;
            frames.push({
                body_y: 0,
                arm_r_angle: -60 + p * 150,
                weapon_angle: -40 + p * 120,
                arm_l_angle: 20 - p * 10,
                leg_l_angle: p * 10, leg_r_angle: -p * 10,
                body_x: -5 + p * 15
            });
        }
        // Recovery (frames 18-30)
        for (let i = 0; i < 12; i++) {
            const p = i / 11;
            frames.push({
                body_y: 0,
                arm_r_angle: 90 * (1 - p),
                weapon_angle: 80 * (1 - p),
                arm_l_angle: 10 * (1 - p),
                leg_l_angle: 10 * (1 - p), leg_r_angle: -10 * (1 - p),
                body_x: 10 * (1 - p)
            });
        }
        return { name: 'Attack', frames, fps: 30, loop: false };
    }

    createHurtAnim() {
        const frames = [];
        for (let i = 0; i < 20; i++) {
            const p = i / 19;
            frames.push({
                body_y: -Math.sin(p * Math.PI) * 10,
                body_x: Math.sin(p * Math.PI) * -15,
                head_y: -Math.sin(p * Math.PI) * 8,
                arm_l_angle: Math.sin(p * Math.PI) * -20,
                arm_r_angle: Math.sin(p * Math.PI) * -20,
                leg_l_angle: Math.sin(p * Math.PI) * 5,
                leg_r_angle: Math.sin(p * Math.PI) * -5,
                weapon_angle: Math.sin(p * Math.PI) * -15
            });
        }
        return { name: 'Hurt', frames, fps: 30, loop: false };
    }

    createDieAnim() {
        const frames = [];
        for (let i = 0; i < 40; i++) {
            const p = i / 39;
            frames.push({
                body_y: p * 30,
                body_x: p * -5,
                head_y: p * 20,
                rotation: p * 90,
                arm_l_angle: p * -45,
                arm_r_angle: p * 45,
                leg_l_angle: p * 20,
                leg_r_angle: p * -20,
                weapon_angle: p * -60,
                opacity: 1 - p * 0.3
            });
        }
        return { name: 'Die', frames, fps: 30, loop: false };
    }

    generateVariants() {
        const c = this.character;
        c.variants = [];
        for (let i = 0; i < 4; i++) {
            const seed = c.seed + (i + 1) * 1000;
            c.variants.push({
                id: 'variant_' + i,
                seed,
                label: ['变体A', '变体B', '变体C', '变体D'][i],
                colorShift: (i + 1) * 30
            });
        }
    }
}

window.CharacterGenerator = CharacterGenerator;
