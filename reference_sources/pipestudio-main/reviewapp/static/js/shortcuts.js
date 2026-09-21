// Keyboard shortcuts and the help dialog.

import { el, isMac, modKey } from './util.js';

export const SHORTCUTS = [
  ['Tools', [
    ['V', 'Select'], ['H', 'Pan'], ['P', 'Draw pipe'], ['E', 'Edit polygon'],
    ['X', 'Split pipe'], ['M', 'Merge selected pipes'],
    ['L', 'Add label'], ['J', 'Add joining point'],
    ['C', 'Draw connection line'], ['K', 'Link pipe/joining point → label'],
    ['Space (hold)', 'Temporary pan'],
  ]],
  ['Selection', [
    ['Click', 'Select'], ['Shift + click', 'Add / remove from selection'],
    ['Drag', 'Rectangle selection'], ['⌘A / Ctrl+A', 'Select all'],
    ['Esc', 'Clear selection'], ['Delete / Backspace', 'Delete selected'],
  ]],
  ['Edit', [
    ['⌘Z / Ctrl+Z', 'Undo'], ['⇧⌘Z / Ctrl+Shift+Z', 'Redo'],
    ['⌘D / Ctrl+D', 'Duplicate'], ['⌘S / Ctrl+S', 'Save review'],
    ['[ / ]', 'Shrink / grow joining-point capture radius'],
  ]],
  ['View', [
    ['F', 'Fit to screen'], ['⇧F', 'Zoom to selection'],
    ['Scroll', 'Zoom'], ['Middle-drag / Space-drag', 'Pan'],
    ['1 / 2 / 3', 'Toggle pipes / labels / joins'],
    ['?', 'This help'],
  ]],
];

export function installShortcuts(app) {
  window.addEventListener('keydown', (e) => {
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;

    // let the active tool consume the key first
    if (app.tools.current?.onKeyDown(e)) { e.preventDefault(); return; }

    const k = e.key.toLowerCase();

    if (modKey(e) && k === 'z') {
      e.preventDefault();
      e.shiftKey ? app.redo() : app.undo();
      return;
    }
    if (modKey(e) && k === 'y') { e.preventDefault(); app.redo(); return; }
    if (modKey(e) && k === 'a') { e.preventDefault(); app.store.selectAll(); app.renderer.invalidate(); return; }
    if (modKey(e) && k === 's') { e.preventDefault(); app.save(); return; }
    if (modKey(e) && k === 'd') { e.preventDefault(); app.duplicateSelection(); return; }
    if (modKey(e)) return;

    switch (k) {
      case 'v': app.tools.activate('select'); break;
      case 'h': app.tools.activate('pan'); break;
      case 'p': app.tools.activate('draw'); break;
      case 'e': app.tools.activate('vertex'); break;
      case 'x': app.tools.activate('split'); break;
      case 'm': app.mergeSelectedPipes(); break;
      case 'l': app.tools.activate('label'); break;
      case 'j': app.tools.activate('join'); break;
      case 'c': app.tools.activate('connect'); break;
      case 'k': app.tools.activate('link'); break;
      case 'f': e.shiftKey ? app.zoomToSelection() : app.fit(); break;
      case 'escape': app.store.clearSelection(); app.renderer.invalidate(); break;
      case 'delete': case 'backspace':
        e.preventDefault(); app.deleteSelection(); break;
      case '[': app.resizeSelectedJoins(-1); break;
      case ']': app.resizeSelectedJoins(+1); break;
      case '1': app.toggleLayer('pipes'); break;
      case '2': app.toggleLayer('labels'); break;
      case '3': app.toggleLayer('joins'); break;
      case '?': app.showShortcuts(); break;
      case ' ':
        if (!app._spacePan) {
          app._spacePan = app.tools.current?.constructor.id;
          app.tools.activate('pan');
        }
        e.preventDefault();
        break;
    }
  });

  window.addEventListener('keyup', (e) => {
    if (e.key === ' ' && app._spacePan) {
      app.tools.activate(app._spacePan);
      app._spacePan = null;
    }
  });
}

export function shortcutDialog() {
  const wrap = el('div');
  wrap.append(el('h2', {}, 'Keyboard shortcuts'));
  for (const [group, rows] of SHORTCUTS) {
    wrap.append(el('h3', {}, group));
    const grid = el('div', { class: 'shortcut-grid' });
    for (const [key, desc] of rows) {
      grid.append(el('span', { class: 'sk' }, desc));
      grid.append(el('span', {},
        ...key.split(' + ').map((k, i) => i
          ? [document.createTextNode(' + '), el('kbd', {}, k)]
          : el('kbd', {}, k)).flat()));
    }
    wrap.append(grid);
  }
  return wrap;
}
