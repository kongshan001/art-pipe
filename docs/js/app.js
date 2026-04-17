/**
 * ArtPipe MVP - 主应用逻辑
 */

let generator = null;
let renderer = null;
let currentCharacter = null;
let gallery = [];

// Step navigation
function showStep(step) {
    document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
    const el = document.getElementById('step-' + step);
    if (el) el.classList.add('active');
    
    document.querySelectorAll('.nav-links a').forEach(a => a.classList.remove('active'));
    if (step === 0) document.getElementById('nav-create').classList.add('active');
    else if (step === 5) document.getElementById('nav-gallery').classList.add('active');
    else if (step === 6) document.getElementById('nav-api').classList.add('active');
}

// Generate character
function generateCharacter() {
    const desc = document.getElementById('char-desc').value || '一个勇敢的冒险者';
    const style = document.getElementById('art-style').value;
    const type = document.getElementById('char-type').value;
    const color = document.getElementById('primary-color').value;

    showStep(1);
    runPipeline({ description: desc, style, type, primaryColor: color });
}

async function runPipeline(config) {
    const steps = ['ps-gen', 'ps-split', 'ps-rig', 'ps-anim', 'ps-pack'];
    const labels = ['概念图生成', '图层拆分', '骨骼绑定', '动画制作', '打包就绪'];
    const progress = document.getElementById('progress-fill');
    const loadingText = document.getElementById('loading-text');

    // Reset
    steps.forEach(s => {
        const el = document.getElementById(s);
        el.className = 'pipe-step';
        el.textContent = '⏳ ' + el.textContent.replace(/^[✅⏳🔄] /, '');
    });

    for (let i = 0; i < steps.length; i++) {
        const el = document.getElementById(steps[i]);
        el.className = 'pipe-step active';
        el.textContent = '🔄 ' + labels[i];
        loadingText.textContent = '🎨 ' + labels[i] + '中...';
        
        progress.style.width = ((i + 0.5) / steps.length * 100) + '%';
        
        await sleep(400 + Math.random() * 600);
        
        el.className = 'pipe-step done';
        el.textContent = '✅ ' + labels[i];
        progress.style.width = ((i + 1) / steps.length * 100) + '%';
    }

    // Actually generate
    generator = new CharacterGenerator();
    currentCharacter = generator.generate(config);

    // Setup renderer
    const canvas = document.getElementById('character-canvas');
    if (!renderer) {
        renderer = new CharacterRenderer(canvas);
        renderer.startLoop();
    }
    renderer.setCharacter(currentCharacter);
    renderer.play('idle');

    // Update UI
    updateCharInfo();
    updateColorSwatches();
    updateVariantGrid();
    
    // Add to gallery
    gallery.push({ character: currentCharacter, time: new Date() });

    await sleep(300);
    showStep(2);
}

function updateCharInfo() {
    const c = currentCharacter;
    document.getElementById('info-style').textContent = c.style.name;
    document.getElementById('info-type').textContent = c.type.name;
    document.getElementById('info-parts').textContent = c.parts.length;
    document.getElementById('info-bones').textContent = c.bones.length;
}

function updateColorSwatches() {
    const container = document.getElementById('color-swatches');
    container.innerHTML = '';
    const schemes = currentCharacter.colors.schemes;
    schemes.forEach((color, i) => {
        const swatch = document.createElement('div');
        swatch.className = 'swatch' + (i === 0 ? ' active' : '');
        swatch.style.background = color;
        swatch.onclick = () => applyColorScheme(color, i);
        container.appendChild(swatch);
    });
}

function updateVariantGrid() {
    const container = document.getElementById('variant-grid');
    container.innerHTML = '';
    currentCharacter.variants.forEach((v, i) => {
        const item = document.createElement('div');
        item.className = 'variant-item';
        item.textContent = ['🔄', '🎭', '👤', '⚔️'][i];
        item.title = v.label;
        item.onclick = () => applyVariant(v);
        container.appendChild(item);
    });
}

function applyColorScheme(color, index) {
    document.querySelectorAll('.swatch').forEach((s, i) => {
        s.classList.toggle('active', i === index);
    });
    
    // Regenerate with new color
    const config = { ...currentCharacter.config, primaryColor: color };
    generator = new CharacterGenerator();
    currentCharacter = generator.generate(config);
    renderer.setCharacter(currentCharacter);
    renderer.play('idle');
    updateCharInfo();
}

function applyVariant(variant) {
    const r = generator.rng;
    generator.seedRandom(variant.seed);
    
    const config = { ...currentCharacter.config };
    // Shift description slightly
    config.description = currentCharacter.config.description + ' variant ' + variant.seed;
    
    generator.seedRandom(variant.seed);
    currentCharacter = generator.generate(config);
    renderer.setCharacter(currentCharacter);
    renderer.play('idle');
    updateCharInfo();
    updateColorSwatches();
}

// Animation controls
function playAnim(name) {
    if (renderer) renderer.play(name);
}

function setAnimSpeed(val) {
    if (renderer) renderer.setSpeed(parseFloat(val));
    document.getElementById('speed-val').textContent = parseFloat(val).toFixed(1) + 'x';
}

function setScale(val) {
    if (renderer) renderer.setScale(parseFloat(val));
    document.getElementById('scale-val').textContent = parseFloat(val).toFixed(1) + 'x';
}

// Export
function doExport(format) {
    if (!currentCharacter) {
        alert('请先生成角色');
        showStep(0);
        return;
    }

    const exporter = new AssetExporter(currentCharacter, renderer);
    const names = { unity: 'Unity Package', spine: 'Spine Project', spritesheet: 'Sprite Sheet', godot: 'Godot Scene' };
    
    const statusEl = document.getElementById('export-status');
    statusEl.style.display = 'block';
    statusEl.className = 'export-status success';
    statusEl.textContent = `✅ ${names[format]} 导出成功！`;

    // Generate export data
    exporter.export(format).then(result => {
        const previewEl = document.getElementById('export-preview');
        previewEl.style.display = 'block';
        
        let content = `📦 ${result.meta.name} - ${result.meta.format}\n`;
        content += `📅 ${result.meta.generatedAt}\n\n`;
        content += `=== 文件列表 ===\n`;
        for (const [key, value] of Object.entries(result.meta.contents || {})) {
            content += `  📄 ${value}\n`;
        }
        content += `\n=== 文件内容 ===\n`;
        for (const [filename, fileContent] of Object.entries(result.files)) {
            content += `\n--- ${filename} ---\n`;
            content += fileContent.substring(0, 2000);
            if (fileContent.length > 2000) content += '\n... (truncated)';
        }

        document.getElementById('export-content').textContent = content;
        
        // Auto-download first file
        const firstFile = Object.entries(result.files)[0];
        if (firstFile) {
            exporter.downloadFile(firstFile[1], `${result.meta.name}_${firstFile[0].replace('.', '_')}.txt`);
        }
    });
}

function downloadExport() {
    // Re-trigger download of all files
    const exporter = new AssetExporter(currentCharacter, renderer);
    ['unity', 'spine', 'spritesheet', 'godot'].forEach(format => {
        exporter.export(format).then(result => {
            for (const [filename, content] of Object.entries(result.files)) {
                const ext = filename.includes('.json') ? 'json' : filename.includes('.cs') ? 'cs' : filename.includes('.gd') ? 'gd' : 'txt';
                exporter.downloadFile(content, `${result.meta.name}_${filename.replace('.', '_')}.${ext}`);
            }
        });
    });
}

// Gallery
function updateGallery() {
    const grid = document.getElementById('gallery-grid');
    if (gallery.length === 0) {
        grid.innerHTML = '<div class="gallery-empty">还没有生成角色，去<a href="#" onclick="showStep(0)">创建一个</a>吧！</div>';
        return;
    }
    grid.innerHTML = '';
    gallery.forEach((item, i) => {
        const card = document.createElement('div');
        card.className = 'gallery-card';
        
        const miniCanvas = document.createElement('canvas');
        miniCanvas.width = 200;
        miniCanvas.height = 250;
        
        const info = document.createElement('div');
        info.className = 'card-info';
        info.innerHTML = `<h4>${item.character.type.name}</h4><span>${item.character.style.name} · ${item.time.toLocaleTimeString()}</span>`;
        
        card.appendChild(miniCanvas);
        card.appendChild(info);
        card.onclick = () => loadFromGallery(i);
        grid.appendChild(card);

        // Render thumbnail
        const thumbRenderer = new CharacterRenderer(miniCanvas);
        thumbRenderer.setCharacter(item.character);
        thumbRenderer.play('idle');
        thumbRenderer.startLoop();
    });
}

function loadFromGallery(index) {
    const item = gallery[index];
    currentCharacter = item.character;
    renderer.setCharacter(currentCharacter);
    renderer.play('idle');
    updateCharInfo();
    updateColorSwatches();
    updateVariantGrid();
    showStep(2);
}

// Utility
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// Watch gallery nav
const origShowStep = showStep;
showStep = function(step) {
    origShowStep(step);
    if (step === 5) updateGallery();
};

// Demo grid: pre-generate all 5 styles × 7 types
function initDemoGrid() {
    const grid = document.getElementById('demo-grid');
    if (!grid) return;
    grid.innerHTML = '';

    const styles = ['pixel', 'cartoon', 'anime', 'western', 'dark'];
    const types = ['warrior', 'mage', 'archer', 'rogue', 'healer', 'monster', 'npc'];
    const styleLabels = { pixel: '像素风', cartoon: '卡通', anime: '日式RPG', western: '欧美', dark: '暗黑风' };
    const typeLabels = { warrior: '战士', mage: '法师', archer: '弓箭手', rogue: '盗贼', healer: '治疗', monster: '怪物', npc: 'NPC' };

    styles.forEach(style => {
        types.forEach(type => {
            const card = document.createElement('div');
            card.className = 'gallery-card demo-card';
            card.title = `${styleLabels[style]} · ${typeLabels[type]} — 点击体验`;

            const miniCanvas = document.createElement('canvas');
            miniCanvas.width = 120;
            miniCanvas.height = 150;
            miniCanvas.style.width = '120px';
            miniCanvas.style.height = '150px';
            miniCanvas.style.imageRendering = style === 'pixel' ? 'pixelated' : 'auto';

            const info = document.createElement('div');
            info.className = 'card-info';
            info.innerHTML = `<h4 style="font-size:12px;">${typeLabels[type]}</h4><span style="font-size:10px;">${styleLabels[style]}</span>`;

            card.appendChild(miniCanvas);
            card.appendChild(info);

            // Click to load into main preview
            card.onclick = () => {
                const config = {
                    description: `${typeLabels[type]}`,
                    style: style,
                    type: type,
                    primaryColor: '#e74c3c'
                };
                showStep(1);
                runPipeline(config);
            };

            grid.appendChild(card);

            // Generate and render thumbnail
            try {
                const gen = new CharacterGenerator();
                const char = gen.generate({
                    description: `${typeLabels[type]}`,
                    style: style,
                    type: type,
                    primaryColor: '#e74c3c'
                });
                const thumbRenderer = new CharacterRenderer(miniCanvas);
                thumbRenderer.setCharacter(char);
                thumbRenderer.play('idle');
                thumbRenderer.startLoop();
            } catch (e) {
                // Silently skip failed renders
                console.warn('Demo render failed:', style, type, e);
            }
        });
    });
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    showStep(0);
    // Init demo grid after a short delay to let scripts settle
    setTimeout(initDemoGrid, 100);
});
