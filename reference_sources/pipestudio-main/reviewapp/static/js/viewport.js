// Viewport: world (page points) <-> screen transform, pan/zoom with inertia-free
// precision, fit helpers.

import { Emitter, clamp } from './util.js';

export class Viewport extends Emitter {
  constructor(canvas) {
    super();
    this.canvas = canvas;
    this.x = 0;          // world coords at the top-left of the canvas
    this.y = 0;
    this.z = 1;          // screen px per world unit (page point)
    this.minZ = 0.02;
    this.maxZ = 60;
    this.width = 1;
    this.height = 1;
  }

  resize(w, h) { this.width = w; this.height = h; this.emit('change'); }

  toScreen(wx, wy) {
    return [(wx - this.x) * this.z, (wy - this.y) * this.z];
  }

  toWorld(sx, sy) {
    return [sx / this.z + this.x, sy / this.z + this.y];
  }

  panBy(dxScreen, dyScreen) {
    this.x -= dxScreen / this.z;
    this.y -= dyScreen / this.z;
    this.emit('change');
  }

  /** Zoom keeping the world point under (sx, sy) fixed. */
  zoomAt(sx, sy, factor) {
    const [wx, wy] = this.toWorld(sx, sy);
    const nz = clamp(this.z * factor, this.minZ, this.maxZ);
    if (nz === this.z) return;
    this.z = nz;
    this.x = wx - sx / this.z;
    this.y = wy - sy / this.z;
    this.emit('change');
  }

  setZoom(z, sx = this.width / 2, sy = this.height / 2) {
    this.zoomAt(sx, sy, clamp(z, this.minZ, this.maxZ) / this.z);
  }

  /** Fit a world-space bbox [x0,y0,x1,y1] into the viewport. */
  fitBounds(b, pad = 0.06) {
    if (!b || !isFinite(b[0])) return;
    const bw = Math.max(b[2] - b[0], 1e-6), bh = Math.max(b[3] - b[1], 1e-6);
    const z = Math.min(this.width / bw, this.height / bh) * (1 - pad * 2);
    this.z = clamp(z, this.minZ, this.maxZ);
    this.x = (b[0] + b[2]) / 2 - this.width / (2 * this.z);
    this.y = (b[1] + b[3]) / 2 - this.height / (2 * this.z);
    this.emit('change');
  }

  centerOn(wx, wy) {
    this.x = wx - this.width / (2 * this.z);
    this.y = wy - this.height / (2 * this.z);
    this.emit('change');
  }

  /** Visible world rectangle. */
  visibleBounds() {
    return [this.x, this.y,
            this.x + this.width / this.z, this.y + this.height / this.z];
  }

  /** Smoothly animate to a target view. */
  animateTo({ bounds, wx, wy, z }, ms = 260) {
    const start = { x: this.x, y: this.y, z: this.z };
    let target;
    if (bounds) {
      const bw = Math.max(bounds[2] - bounds[0], 1e-6);
      const bh = Math.max(bounds[3] - bounds[1], 1e-6);
      const tz = clamp(Math.min(this.width / bw, this.height / bh) * 0.7,
                       this.minZ, this.maxZ);
      target = {
        z: tz,
        x: (bounds[0] + bounds[2]) / 2 - this.width / (2 * tz),
        y: (bounds[1] + bounds[3]) / 2 - this.height / (2 * tz),
      };
    } else {
      const tz = clamp(z ?? this.z, this.minZ, this.maxZ);
      target = { z: tz, x: wx - this.width / (2 * tz),
                 y: wy - this.height / (2 * tz) };
    }
    const t0 = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - t0) / ms);
      const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      this.z = start.z + (target.z - start.z) * e;
      this.x = start.x + (target.x - start.x) * e;
      this.y = start.y + (target.y - start.y) * e;
      this.emit('change');
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}
