// Tool framework: a Tool owns pointer/keyboard behaviour while it is active.
// Adding a new tool means writing a class and registering it here — no other
// module needs to change.

export class Tool {
  static id = 'tool';
  static title = 'Tool';
  static key = '';
  static icon = '';
  static cursor = 'default';

  constructor(app) { this.app = app; }

  get store() { return this.app.store; }
  get renderer() { return this.app.renderer; }
  get vp() { return this.app.viewport; }
  get history() { return this.app.history; }

  activate() {}
  deactivate() {}
  onPointerDown(_e, _w) {}
  onPointerMove(_e, _w) {}
  onPointerUp(_e, _w) {}
  onDoubleClick(_e, _w) {}
  onKeyDown(_e) { return false; }
  status() { return ''; }
}

export class ToolManager {
  constructor(app) {
    this.app = app;
    this.tools = new Map();
    this.current = null;
    this.previous = null;
  }

  register(ToolClass) {
    this.tools.set(ToolClass.id, new ToolClass(this.app));
    return this;
  }

  list() { return [...this.tools.values()]; }

  activate(id) {
    const next = this.tools.get(id);
    if (!next || next === this.current) return;
    // a wizard step only exposes the tools that belong to it
    if (this.app.allowedTools && !this.app.allowedTools.has(id)) {
      this.app.toast(`${next.constructor.title} is not part of this step`);
      return;
    }
    if (this.current) {
      this.previous = this.current.constructor.id;
      this.current.deactivate();
    }
    this.current = next;
    next.activate();
    this.app.emit('tool', next);
  }

  /** Temporarily switch (e.g. space-to-pan) and back. */
  activatePrevious() {
    if (this.previous) this.activate(this.previous);
  }
}
