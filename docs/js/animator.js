/**
 * ArtPipe - 角色渲染与动画引擎
 * Canvas 2D实时渲染，支持多风格、多动画
 */

class CharacterRenderer {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.character = null;
        this.currentAnim = 'idle';
        this.frameIndex = 0;
        this.speed = 1.0;
        this.scale = 1.0;
        this.lastTime = 0;
        this.animFrame = null;
        this.playing = true;
    }

    setCharacter(char) {
        this.character = char;
        this.frameIndex = 0;
    }

    play(animName) {
        if (!this.character || !this.character.animations[animName]) return;
        this.currentAnim = animName;
        this.frameIndex = 0;
        this.playing = true;
        document.querySelectorAll('.anim-controls .btn-sm').forEach(b => b.classList.remove('active'));
        const btn = document.getElementById('anim-' + animName);
        if (btn) btn.classList.add('active');
    }

    setSpeed(s) { this.speed = s; }
    setScale(s) { this.scale = s; }

    startLoop() {
        const loop = (time) => {
            if (this.character) {
                const anim = this.character.animations[this.currentAnim];
                if (anim) {
                    const frameTime = 1000 / (anim.fps * this.speed);
                    if (time - this.lastTime > frameTime) {
                        this.frameIndex++;
                        if (this.frameIndex >= anim.frames.length) {
                            this.frameIndex = anim.loop ? 0 : anim.frames.length - 1;
                        }
                        this.lastTime = time;
                    }
                }
                this.render();
            }
            this.animFrame = requestAnimationFrame(loop);
        };
        this.animFrame = requestAnimationFrame(loop);
    }

    stop() {
        if (this.animFrame) cancelAnimationFrame(this.animFrame);
    }

    render() {
        const ctx = this.ctx;
        const c = this.character;
        if (!c) return;

        const w = this.canvas.width;
        const h = this.canvas.height;
        
        ctx.clearRect(0, 0, w, h);
        ctx.save();

        const cx = w / 2;
        const cy = h * 0.65;
        const s = this.scale * (c.style.pixelSize > 1 ? 1 : 2.5);

        ctx.translate(cx, cy);
        ctx.scale(s, s);

        const anim = c.animations[this.currentAnim];
        const frame = anim ? anim.frames[this.frameIndex] : {};
        
        if (frame.opacity !== undefined) {
            ctx.globalAlpha = frame.opacity;
        }
        if (frame.rotation) {
            ctx.rotate(frame.rotation * Math.PI / 180);
        }

        const bx = (frame.body_x || 0);
        const by = (frame.body_y || 0);

        // Draw shadow
        ctx.save();
        ctx.translate(bx, 50);
        ctx.scale(1, 0.3);
        ctx.fillStyle = 'rgba(0,0,0,0.2)';
        ctx.beginPath();
        ctx.ellipse(0, 0, 25, 25, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        // Draw based on style
        if (c.style.pixelSize > 1) {
            this.drawPixelCharacter(ctx, c, frame, bx, by);
        } else {
            this.drawSmoothCharacter(ctx, c, frame, bx, by);
        }

        ctx.restore();
    }

    drawPixelCharacter(ctx, c, frame, bx, by) {
        const px = c.style.pixelSize;
        const colors = c.colors;
        
        const drawPixelRect = (x, y, w, h, color, angle = 0) => {
            ctx.save();
            ctx.fillStyle = color;
            if (angle) {
                ctx.translate(x + w/2, y + h/2);
                ctx.rotate(angle * Math.PI / 180);
                ctx.fillRect(-w/2, -h/2, w, h);
            } else {
                ctx.fillRect(x, y, w, h);
            }
            ctx.restore();
        };

        const drawPixelCircle = (cx, cy, r, color) => {
            ctx.fillStyle = color;
            for (let y = -r; y <= r; y += px) {
                for (let x = -r; x <= r; x += px) {
                    if (x*x + y*y <= r*r) {
                        ctx.fillRect(cx + x, cy + y, px, px);
                    }
                }
            }
        };

        const la = (frame.leg_l_angle || 0);
        const ra = (frame.leg_r_angle || 0);
        const ala = (frame.arm_l_angle || 0);
        const ara = (frame.arm_r_angle || 0);

        // Legs
        drawPixelRect(-14 + bx, 20 + by, 8, 28, colors.primary, la);
        drawPixelRect(6 + bx, 20 + by, 8, 28, colors.primary, ra);
        
        // Boots
        drawPixelRect(-16 + bx, 44 + by, 12, 6, colors.shadow, la);
        drawPixelRect(4 + bx, 44 + by, 12, 6, colors.shadow, ra);

        // Body
        drawPixelRect(-16 + bx, -20 + by, 32, 42, colors.primary);
        drawPixelRect(-12 + bx, -16 + by, 24, 34, colors.secondary);
        
        // Belt
        drawPixelRect(-16 + bx, 12 + by, 32, 4, colors.shadow);

        // Arms
        drawPixelRect(-24 + bx, -16 + by, 8, 28, colors.primary, ala);
        drawPixelRect(16 + bx, -16 + by, 8, 28, colors.primary, ara);
        
        // Hands
        drawPixelCircle(-20 + bx + Math.sin(ala*Math.PI/180)*12, 14 + by + Math.cos(ala*Math.PI/180)*12, 4, colors.skin);
        drawPixelCircle(20 + bx + Math.sin(ara*Math.PI/180)*12, 14 + by + Math.cos(ara*Math.PI/180)*12, 4, colors.skin);

        // Head
        const hy = frame.head_y || 0;
        drawPixelCircle(bx, -38 + by + hy, 16, colors.skin);
        
        // Hair
        drawPixelRect(-16 + bx, -54 + by + hy, 32, 12, colors.hair);
        drawPixelRect(-18 + bx, -46 + by + hy, 4, 16, colors.hair);
        drawPixelRect(14 + bx, -46 + by + hy, 4, 16, colors.hair);
        
        // Eyes
        drawPixelRect(-6 + bx, -40 + by + hy, 4, 4, '#ffffff');
        drawPixelRect(2 + bx, -40 + by + hy, 4, 4, '#ffffff');
        drawPixelRect(-5 + bx, -39 + by + hy, 2, 2, colors.eye);
        drawPixelRect(3 + bx, -39 + by + hy, 2, 2, colors.eye);
        
        // Mouth
        drawPixelRect(-3 + bx, -32 + by + hy, 6, 2, '#c0392b');

        // Weapon
        const wa = frame.weapon_angle || 0;
        this.drawWeaponPixel(ctx, c, bx, by, ara, wa, px);
    }

    drawWeaponPixel(ctx, c, bx, by, armAngle, weaponAngle, px) {
        const type = c.config.type;
        ctx.save();
        ctx.translate(20 + bx, 0);
        ctx.rotate((armAngle + weaponAngle) * Math.PI / 180);
        
        const colors = c.colors;
        
        if (type === 'warrior' || type === 'rogue') {
            // Sword / Dagger
            ctx.fillStyle = '#bdc3c7';
            for (let i = 0; i < 30; i += px) {
                ctx.fillRect(-1, 12 + i, 3, px);
            }
            ctx.fillStyle = '#f1c40f';
            ctx.fillRect(-4, 10, 9, 4);
        } else if (type === 'mage') {
            // Staff
            ctx.fillStyle = '#8B4513';
            for (let i = 0; i < 35; i += px) {
                ctx.fillRect(-1, 12 + i, 3, px);
            }
            // Orb
            ctx.fillStyle = colors.highlight;
            for (let y = -6; y <= 6; y += px) {
                for (let x = -6; x <= 6; x += px) {
                    if (x*x + y*y <= 36) ctx.fillRect(x-1, y-1, px, px);
                }
            }
        } else if (type === 'archer') {
            // Bow
            ctx.strokeStyle = '#8B4513';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(8, 25, 15, -Math.PI/2, Math.PI/2);
            ctx.stroke();
            ctx.strokeStyle = '#ecf0f1';
            ctx.beginPath();
            ctx.moveTo(8, 10);
            ctx.lineTo(8, 40);
            ctx.stroke();
        } else if (type === 'monster') {
            // Claws
            ctx.fillStyle = colors.shadow;
            ctx.fillRect(18, 20, 3, 15);
            ctx.fillRect(22, 18, 3, 15);
            ctx.fillRect(26, 20, 3, 15);
        }
        ctx.restore();
    }

    drawSmoothCharacter(ctx, c, frame, bx, by) {
        const colors = c.colors;
        const style = c.style;
        const sw = style.strokeWeight;

        const la = (frame.leg_l_angle || 0) * Math.PI / 180;
        const ra = (frame.leg_r_angle || 0) * Math.PI / 180;
        const ala = (frame.arm_l_angle || 0) * Math.PI / 180;
        const ara = (frame.arm_r_angle || 0) * Math.PI / 180;
        const hy = frame.head_y || 0;

        // Legs
        this.drawLimb(ctx, -10 + bx, 18 + by, la, 30, 10, colors.primary, colors.shadow, sw);
        this.drawLimb(ctx, 10 + bx, 18 + by, ra, 30, 10, colors.primary, colors.shadow, sw);
        
        // Boots
        this.drawBoot(ctx, -10 + bx + Math.sin(la)*28, 18 + by + Math.cos(la)*28, la, colors.shadow, sw);
        this.drawBoot(ctx, 10 + bx + Math.sin(ra)*28, 18 + by + Math.cos(ra)*28, ra, colors.shadow, sw);

        // Torso
        ctx.save();
        ctx.fillStyle = colors.primary;
        if (sw) ctx.strokeStyle = '#1a1a2e';
        ctx.lineWidth = sw;
        
        ctx.beginPath();
        ctx.moveTo(-18 + bx, -18 + by);
        ctx.lineTo(18 + bx, -18 + by);
        ctx.lineTo(16 + bx, 20 + by);
        ctx.lineTo(-16 + bx, 20 + by);
        ctx.closePath();
        ctx.fill();
        if (sw) ctx.stroke();

        // Armor/clothing detail
        ctx.fillStyle = colors.secondary;
        ctx.beginPath();
        ctx.moveTo(-12 + bx, -12 + by);
        ctx.lineTo(12 + bx, -12 + by);
        ctx.lineTo(10 + bx, 14 + by);
        ctx.lineTo(-10 + bx, 14 + by);
        ctx.closePath();
        ctx.fill();

        // Belt
        ctx.fillStyle = colors.shadow;
        ctx.fillRect(-18 + bx, 14 + by, 36, 5);
        if (sw) ctx.strokeRect(-18 + bx, 14 + by, 36, 5);
        
        ctx.restore();

        // Arms
        this.drawLimb(ctx, -20 + bx, -14 + by, ala, 28, 9, colors.primary, colors.secondary, sw);
        this.drawLimb(ctx, 20 + bx, -14 + by, ara, 28, 9, colors.primary, colors.secondary, sw);

        // Hands
        const handLX = -20 + bx + Math.sin(ala) * 26;
        const handLY = -14 + by + Math.cos(ala) * 26;
        const handRX = 20 + bx + Math.sin(ara) * 26;
        const handRY = -14 + by + Math.cos(ara) * 26;
        
        ctx.fillStyle = colors.skin;
        ctx.beginPath(); ctx.arc(handLX, handLY, 5, 0, Math.PI * 2); ctx.fill();
        if (sw) { ctx.strokeStyle = '#1a1a2e'; ctx.stroke(); }
        ctx.beginPath(); ctx.arc(handRX, handRY, 5, 0, Math.PI * 2); ctx.fill();
        if (sw) ctx.stroke();

        // Head
        const headY = -40 + by + hy;
        ctx.fillStyle = colors.skin;
        ctx.beginPath(); ctx.ellipse(bx, headY, 16, 18, 0, 0, Math.PI * 2); ctx.fill();
        if (sw) { ctx.strokeStyle = '#1a1a2e'; ctx.lineWidth = sw; ctx.stroke(); }

        // Hair
        ctx.fillStyle = colors.hair;
        ctx.beginPath();
        ctx.ellipse(bx, headY - 12, 18, 12, 0, Math.PI, 0);
        ctx.fill();
        // Side hair
        ctx.fillRect(-18 + bx, headY - 10, 5, 18);
        ctx.fillRect(13 + bx, headY - 10, 5, 18);
        if (sw) { ctx.strokeStyle = '#1a1a2e'; ctx.stroke(); }

        // Eyes
        ctx.fillStyle = '#fff';
        ctx.beginPath(); ctx.ellipse(-6 + bx, headY - 2, 4, 5, 0, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.ellipse(6 + bx, headY - 2, 4, 5, 0, 0, Math.PI * 2); ctx.fill();
        
        ctx.fillStyle = colors.eye;
        ctx.beginPath(); ctx.arc(-5 + bx, headY - 1, 2.5, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(7 + bx, headY - 1, 2.5, 0, Math.PI * 2); ctx.fill();
        
        // Eye shine
        ctx.fillStyle = '#fff';
        ctx.beginPath(); ctx.arc(-4 + bx, headY - 3, 1, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(8 + bx, headY - 3, 1, 0, Math.PI * 2); ctx.fill();

        // Mouth
        ctx.strokeStyle = '#c0392b';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(bx, headY + 8, 4, 0.2, Math.PI - 0.2);
        ctx.stroke();

        // Class-specific headgear
        this.drawHeadgear(ctx, c, bx, headY, sw);

        // Weapon
        const wa = (frame.weapon_angle || 0) * Math.PI / 180;
        this.drawWeaponSmooth(ctx, c, handRX, handRY, ara + wa, sw);
    }

    drawLimb(ctx, x, y, angle, length, width, color, detailColor, sw) {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(angle);
        
        ctx.fillStyle = color;
        if (sw) { ctx.strokeStyle = '#1a1a2e'; ctx.lineWidth = sw; }
        
        // Rounded limb
        ctx.beginPath();
        ctx.roundRect(-width/2, 0, width, length, width/2);
        ctx.fill();
        if (sw) ctx.stroke();
        
        ctx.restore();
    }

    drawBoot(ctx, x, y, angle, color, sw) {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(angle * 0.3);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.roundRect(-7, -3, 16, 8, 3);
        ctx.fill();
        if (sw) { ctx.strokeStyle = '#1a1a2e'; ctx.stroke(); }
        ctx.restore();
    }

    drawHeadgear(ctx, c, x, y, sw) {
        const type = c.config.type;
        const colors = c.colors;
        
        if (sw) { ctx.strokeStyle = '#1a1a2e'; ctx.lineWidth = sw; }

        if (type === 'warrior') {
            // Helmet
            ctx.fillStyle = '#7f8c8d';
            ctx.beginPath();
            ctx.ellipse(x, y - 16, 18, 14, 0, Math.PI, 0);
            ctx.fill();
            if (sw) ctx.stroke();
            // Visor
            ctx.fillStyle = '#95a5a6';
            ctx.fillRect(-14 + x, y - 16, 28, 4);
        } else if (type === 'mage') {
            // Pointy hat
            ctx.fillStyle = colors.shadow;
            ctx.beginPath();
            ctx.moveTo(x, y - 50);
            ctx.lineTo(-22 + x, y - 14);
            ctx.lineTo(22 + x, y - 14);
            ctx.closePath();
            ctx.fill();
            if (sw) ctx.stroke();
            // Star
            ctx.fillStyle = '#f1c40f';
            ctx.beginPath(); ctx.arc(x + 3, y - 30, 3, 0, Math.PI * 2); ctx.fill();
        } else if (type === 'archer') {
            // Hood
            ctx.fillStyle = '#27ae60';
            ctx.beginPath();
            ctx.ellipse(x, y - 10, 19, 15, 0, Math.PI + 0.3, -0.3);
            ctx.fill();
        } else if (type === 'rogue') {
            // Mask
            ctx.fillStyle = '#2c3e50';
            ctx.fillRect(-14 + x, y - 6, 28, 8);
            // Eyes through mask
            ctx.fillStyle = '#fff';
            ctx.beginPath(); ctx.arc(-5 + x, y - 2, 3, 0, Math.PI*2); ctx.fill();
            ctx.beginPath(); ctx.arc(5 + x, y - 2, 3, 0, Math.PI*2); ctx.fill();
        } else if (type === 'healer') {
            // Halo
            ctx.strokeStyle = '#f1c40f';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.ellipse(x, y - 38, 14, 4, 0, 0, Math.PI * 2);
            ctx.stroke();
        } else if (type === 'monster') {
            // Horns
            ctx.fillStyle = '#7f8c8d';
            ctx.beginPath();
            ctx.moveTo(-14 + x, y - 14);
            ctx.lineTo(-20 + x, y - 35);
            ctx.lineTo(-8 + x, y - 18);
            ctx.fill();
            ctx.beginPath();
            ctx.moveTo(14 + x, y - 14);
            ctx.lineTo(20 + x, y - 35);
            ctx.lineTo(8 + x, y - 18);
            ctx.fill();
        }
    }

    drawWeaponSmooth(ctx, c, hx, hy, angle, sw) {
        const type = c.config.type;
        const colors = c.colors;
        
        ctx.save();
        ctx.translate(hx, hy);
        ctx.rotate(angle);
        
        if (sw) { ctx.strokeStyle = '#1a1a2e'; ctx.lineWidth = sw; }

        if (type === 'warrior') {
            // Sword
            ctx.fillStyle = '#bdc3c7';
            ctx.beginPath();
            ctx.roundRect(-2, 5, 4, 35, 1);
            ctx.fill();
            if (sw) ctx.stroke();
            ctx.fillStyle = '#f1c40f';
            ctx.fillRect(-6, 2, 12, 4);
        } else if (type === 'mage') {
            // Staff
            ctx.fillStyle = '#8B4513';
            ctx.fillRect(-2, 5, 4, 40);
            // Orb
            ctx.fillStyle = colors.highlight;
            ctx.beginPath(); ctx.arc(0, 2, 6, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = 'rgba(255,255,255,0.4)';
            ctx.beginPath(); ctx.arc(-2, 0, 2, 0, Math.PI * 2); ctx.fill();
        } else if (type === 'archer') {
            ctx.strokeStyle = '#8B4513';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(10, 18, 16, -1.2, 1.2);
            ctx.stroke();
            ctx.strokeStyle = '#ddd';
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(10, 2); ctx.lineTo(10, 34); ctx.stroke();
        } else if (type === 'rogue') {
            ctx.fillStyle = '#bdc3c7';
            ctx.beginPath(); ctx.roundRect(-1, 5, 3, 20, 1); ctx.fill();
            ctx.fillRect(-4, 3, 9, 3);
        } else if (type === 'monster') {
            ctx.fillStyle = colors.shadow;
            ctx.beginPath();
            ctx.moveTo(-3, 5); ctx.lineTo(0, 22); ctx.lineTo(3, 5);
            ctx.fill();
            ctx.beginPath();
            ctx.moveTo(5, 5); ctx.lineTo(8, 20); ctx.lineTo(11, 5);
            ctx.fill();
        }
        ctx.restore();
    }

    renderToCanvas(targetCanvas, variant = null) {
        const tc = targetCanvas.getContext('2d');
        const tmpCanvas = document.createElement('canvas');
        tmpCanvas.width = this.canvas.width;
        tmpCanvas.height = this.canvas.height;
        const tmpCtx = tmpCanvas.getContext('2d');
        tmpCtx.drawImage(this.canvas, 0, 0);
        
        tc.clearRect(0, 0, targetCanvas.width, targetCanvas.height);
        tc.drawImage(tmpCanvas, 0, 0, targetCanvas.width, targetCanvas.height);
    }
}

window.CharacterRenderer = CharacterRenderer;
