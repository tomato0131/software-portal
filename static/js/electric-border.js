/**
 * ElectricBorder - 纯 JS 移植版
 * 灵感来源: https://reactbits.dev/animations/electric-border
 * 适用于非 React 环境（Flask Jinja2 模板）
 */

class ElectricBorder {
  constructor(element, options = {}) {
    this.element = element;
    this.color = options.color || '#0071e3';
    this.speed = options.speed || 0.8;
    this.chaos = options.chaos || 0.08;
    this.borderRadius = options.borderRadius || 18;
    this.thickness = options.thickness || 1.5;

    this.time = 0;
    this.lastFrameTime = 0;
    this.animId = null;

    this._createCanvas();
    this._startAnimation();
  }

  _createCanvas() {
    const canvas = document.createElement('canvas');
    canvas.className = 'electric-border-canvas';
    Object.assign(canvas.style, {
      position: 'absolute',
      top: '0',
      left: '0',
      pointerEvents: 'none',
      zIndex: '1'
    });
    this.element.style.position = 'relative';
    this.element.style.overflow = 'visible';
    this.element.insertBefore(canvas, this.element.firstChild);
    this.canvas = canvas;
  }

  // Noise
  _random(x) {
    return (Math.sin(x * 12.9898) * 43758.5453) % 1;
  }

  _noise2D(x, y) {
    const i = Math.floor(x);
    const j = Math.floor(y);
    const fx = x - i;
    const fy = y - j;
    const a = this._random(i + j * 57);
    const b = this._random(i + 1 + j * 57);
    const c = this._random(i + (j + 1) * 57);
    const d = this._random(i + 1 + (j + 1) * 57);
    const ux = fx * fx * (3.0 - 2.0 * fx);
    const uy = fy * fy * (3.0 - 2.0 * fy);
    return a * (1 - ux) * (1 - uy) + b * ux * (1 - uy) + c * (1 - ux) * uy + d * ux * uy;
  }

  _octavedNoise(x, octaves, lacunarity, gain, baseAmplitude, frequency, time, seed, baseFlatness) {
    let y = 0;
    let amplitude = baseAmplitude;
    let freq = frequency;
    for (let i = 0; i < octaves; i++) {
      let amp = amplitude;
      if (i === 0) amp *= baseFlatness;
      y += amp * this._noise2D(freq * x + seed * 100, time * freq * 0.3);
      freq *= lacunarity;
      amplitude *= gain;
    }
    return y;
  }

  _getCornerPoint(cx, cy, radius, startAngle, arcLength, progress) {
    const angle = startAngle + progress * arcLength;
    return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  }

  _getRoundedRectPoint(t, left, top, width, height, radius) {
    const sw = width - 2 * radius;
    const sh = height - 2 * radius;
    const ca = (Math.PI * radius) / 2;
    const total = 2 * sw + 2 * sh + 4 * ca;
    const dist = t * total;
    let acc = 0;

    if (dist <= acc + sw) {
      const p = (dist - acc) / sw;
      return { x: left + radius + p * sw, y: top };
    }
    acc += sw;

    if (dist <= acc + ca) {
      const p = (dist - acc) / ca;
      return this._getCornerPoint(left + width - radius, top + radius, radius, -Math.PI / 2, Math.PI / 2, p);
    }
    acc += ca;

    if (dist <= acc + sh) {
      const p = (dist - acc) / sh;
      return { x: left + width, y: top + radius + p * sh };
    }
    acc += sh;

    if (dist <= acc + ca) {
      const p = (dist - acc) / ca;
      return this._getCornerPoint(left + width - radius, top + height - radius, radius, 0, Math.PI / 2, p);
    }
    acc += ca;

    if (dist <= acc + sw) {
      const p = (dist - acc) / sw;
      return { x: left + width - radius - p * sw, y: top + height };
    }
    acc += sw;

    if (dist <= acc + ca) {
      const p = (dist - acc) / ca;
      return this._getCornerPoint(left + radius, top + height - radius, radius, Math.PI / 2, Math.PI / 2, p);
    }
    acc += ca;

    if (dist <= acc + sh) {
      const p = (dist - acc) / sh;
      return { x: left, y: top + height - radius - p * sh };
    }
    acc += sh;

    const p = (dist - acc) / ca;
    return this._getCornerPoint(left + radius, top + radius, radius, Math.PI, Math.PI / 2, p);
  }

  _updateSize() {
    const canvas = this.canvas;
    const container = this.element;
    const rect = container.getBoundingClientRect();
    const borderOffset = 6;
    const width = rect.width + borderOffset * 2;
    const height = rect.height + borderOffset * 2;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    canvas.style.top = -borderOffset + 'px';
    canvas.style.left = -borderOffset + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    return { width, height, borderOffset, ctx };
  }

  _startAnimation() {
    const draw = (currentTime) => {
      const { width, height, borderOffset, ctx } = this._updateSize();
      if (!ctx) { this.animId = requestAnimationFrame(draw); return; }

      const deltaTime = (currentTime - this.lastFrameTime) / 1000;
      this.time += deltaTime * this.speed;
      this.lastFrameTime = currentTime;

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      ctx.scale(dpr, dpr);

      // Glow layers
      const layers = [
        { blur: 12, alpha: 0.15, lw: 4 },
        { blur: 6, alpha: 0.3, lw: 2.5 },
        { blur: 2, alpha: 0.8, lw: this.thickness },
        { blur: 0, alpha: 1, lw: this.thickness },
      ];

      for (const layer of layers) {
        ctx.save();
        ctx.strokeStyle = this.color;
        ctx.lineWidth = layer.lw;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.globalAlpha = layer.alpha;
        if (layer.blur > 0) { ctx.filter = `blur(${layer.blur}px)`; }

        const left = borderOffset;
        const top = borderOffset;
        const bw = width - 2 * borderOffset;
        const bh = height - 2 * borderOffset;
        const maxR = Math.min(bw, bh) / 2;
        const radius = Math.min(this.borderRadius, maxR);
        const approxP = 2 * (bw + bh) + 2 * Math.PI * radius;
        const samples = Math.floor(approxP / 2);

        ctx.beginPath();
        for (let i = 0; i <= samples; i++) {
          const progress = i / samples;
          const pt = this._getRoundedRectPoint(progress, left, top, bw, bh, radius);

          const xn = this._octavedNoise(progress * 8, 4, 1.6, 0.7, this.chaos, 10, this.time, 0, 0);
          const yn = this._octavedNoise(progress * 8, 4, 1.6, 0.7, this.chaos, 10, this.time, 1, 0);

          const displace = 3;
          const x = pt.x + xn * displace;
          const y = pt.y + yn * displace;

          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.stroke();
        ctx.restore();
      }

      this.animId = requestAnimationFrame(draw);
    };
    this.animId = requestAnimationFrame(draw);
  }

  destroy() {
    if (this.animId) cancelAnimationFrame(this.animId);
    if (this.canvas && this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }
  }
}

// 初始化所有 .software-card 的 Electric Border
function initElectricBorders() {
  const cards = document.querySelectorAll('.software-card');
  const colorMap = {
    'briefcase': '#0071e3',
    'chat': '#00b894',
    'shield': '#636e72',
    'lock': '#0984e3',
    'cpu': '#6c5ce7',
    'default': '#636e72'
  };
  cards.forEach(card => {
    const iconClass = [...card.classList].find(c => c !== 'software-card' && c !== 'fade-in-up') || 'default';
    const color = colorMap[iconClass] || '#0071e3';
    new ElectricBorder(card, { color, speed: 0.6, chaos: 0.06, borderRadius: 18, thickness: 1.5 });
  });
}
