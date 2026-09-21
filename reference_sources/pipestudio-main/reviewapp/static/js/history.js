// Undo/redo. Snapshot based: every committed operation stores the previous
// state of the editable collections, so *every* operation is reversible
// without each tool having to write an inverse.

import { Emitter } from './util.js';

export class History extends Emitter {
  constructor(store, limit = 500) {
    super();
    this.store = store;
    this.limit = limit;
    this.past = [];      // {label, snapshot}
    this.future = [];
    this._pending = null;
  }

  reset() {
    this.past = []; this.future = []; this._pending = null;
    this.emit('change');
  }

  /**
   * Capture the state *before* an operation. Call begin() then mutate the
   * store then commit(). If the operation turns out to be a no-op, call
   * cancel().
   */
  begin(label) {
    this._pending = { label, snapshot: this.store.snapshot() };
  }

  commit(label) {
    if (!this._pending) return;
    const entry = this._pending;
    if (label) entry.label = label;
    this._pending = null;
    if (entry.snapshot === this.store.snapshot()) return;   // nothing changed
    this.past.push(entry);
    if (this.past.length > this.limit) this.past.shift();
    this.future.length = 0;
    this.emit('change');
  }

  cancel() { this._pending = null; }

  /** Convenience for single-shot mutations. */
  run(label, fn) {
    this.begin(label);
    try { fn(); this.commit(); }
    catch (e) { this.cancel(); throw e; }
  }

  get canUndo() { return this.past.length > 0; }
  get canRedo() { return this.future.length > 0; }

  undo() {
    if (!this.past.length) return null;
    const entry = this.past.pop();
    this.future.push({ label: entry.label, snapshot: this.store.snapshot() });
    this.store.restoreSnapshot(entry.snapshot);
    this.emit('change');
    return entry.label;
  }

  redo() {
    if (!this.future.length) return null;
    const entry = this.future.pop();
    this.past.push({ label: entry.label, snapshot: this.store.snapshot() });
    this.store.restoreSnapshot(entry.snapshot);
    this.emit('change');
    return entry.label;
  }

  /** Most recent operations, newest first. */
  recent(n = 24) {
    return this.past.slice(-n).reverse().map((e, i) => ({
      label: e.label, index: this.past.length - i,
    }));
  }
}
