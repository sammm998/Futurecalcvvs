// Searchable class combobox — used by the inspector and the class prompt.

import { classColor, el } from './util.js';

export class ClassCombo {
  /**
   * @param {object}  app
   * @param {string}  value    initial code
   * @param {func}    onPick   called with the chosen code
   * @param {object}  opts     {free:true} allows codes not in the list
   */
  constructor(app, value, onPick, opts = {}) {
    this.app = app;
    this.onPick = onPick;
    this.free = !!opts.free;
    this.value = value || '';

    this.input = el('input', {
      class: 'input', type: 'text', value: this.value,
      placeholder: 'Search classes…', autocomplete: 'off', spellcheck: 'false',
    });
    this.list = el('div', { class: 'combo-list hidden' });
    this.element = el('div', { class: 'combo' }, this.input, this.list);

    this.input.addEventListener('focus', () => { this.input.select(); this.open(); });
    this.input.addEventListener('input', () => this.open());
    this.input.addEventListener('blur', () => setTimeout(() => this.close(), 140));
    this.input.addEventListener('keydown', (e) => this._key(e));
    this.active = 0;
  }

  options() {
    const q = this.input.value.trim().toLowerCase();
    const all = ['Unknown', ...this.app.store.classes().filter(c => c !== 'Unknown')];
    const hits = q ? all.filter(c => c.toLowerCase().includes(q)) : all;
    if (this.free && q && !all.some(c => c.toLowerCase() === q)) {
      hits.unshift(this.input.value.trim());
    }
    return hits.slice(0, 120);
  }

  open() {
    const opts = this.options();
    this.list.replaceChildren();
    this.active = Math.min(this.active, Math.max(0, opts.length - 1));
    opts.forEach((code, i) => {
      this.list.append(el('div', {
        class: 'combo-item' + (i === this.active ? ' active' : ''),
        onmousedown: (e) => { e.preventDefault(); this.pick(code); },
        onmouseenter: () => { this.active = i; this._paint(); },
      },
        el('span', { class: 'combo-swatch',
                     style: `background:${classColor(code)}` }),
        el('span', {}, code)));
    });
    this.list.classList.toggle('hidden', !opts.length);
  }

  _paint() {
    [...this.list.children].forEach((n, i) =>
      n.classList.toggle('active', i === this.active));
  }

  close() { this.list.classList.add('hidden'); }

  pick(code) {
    this.value = code;
    this.input.value = code;
    this.close();
    this.onPick(code);
  }

  _key(e) {
    const opts = this.options();
    if (e.key === 'ArrowDown') {
      this.active = Math.min(this.active + 1, opts.length - 1); this._paint();
      e.preventDefault();
    } else if (e.key === 'ArrowUp') {
      this.active = Math.max(this.active - 1, 0); this._paint();
      e.preventDefault();
    } else if (e.key === 'Enter') {
      const code = opts[this.active] ?? (this.free ? this.input.value.trim() : null);
      if (code) this.pick(code);
      e.preventDefault();
    } else if (e.key === 'Escape') {
      this.input.value = this.value; this.close(); this.input.blur();
    }
    e.stopPropagation();     // never let shortcuts fire while typing
  }
}
