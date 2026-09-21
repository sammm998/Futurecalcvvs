// Right-hand inspector: context-sensitive details and actions.

import { classColor, el, fmt } from './util.js';
import { ClassCombo } from './combo.js';

export class Inspector {
  constructor(app, root) {
    this.app = app;
    this.root = root;
    this.store = app.store;
    this.store.on('selection', () => this.render());
    this.store.on('change', () => this.render());
    this.render();
  }

  render() {
    const sel = this.store.selectionList();
    this.root.replaceChildren();
    if (!sel.length) return this.root.append(this._overview());
    if (sel.length > 1) return this.root.append(this._multi(sel));
    const { kind, obj } = sel[0];
    this.root.append(
      kind === 'pipe' ? this._pipe(obj)
      : kind === 'label' ? this._label(obj)
      : this._join(obj));
  }

  /* ── no selection: drawing overview + legend ─────────────────────────── */
  _overview() {
    const st = this.store;
    const counts = st.classCounts();
    const wrap = el('div');
    wrap.append(
      el('div', { class: 'empty-state' },
        el('span', { class: 'big' }, '◈'),
        'Select an object to inspect it.',
        el('br'), 'Drag to marquee-select.'));

    const s = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Drawing'));
    const totalPipes = st.activePipes().length;
    const unknown = st.activePipes().filter(p => p.type === 'Unknown').length;
    const manual = st.activePipes().filter(p => p.source === 'manual').length;
    for (const [k, v] of [
      ['Pipes', totalPipes],
      ['Classified', `${totalPipes - unknown} (${totalPipes ? Math.round((totalPipes - unknown) / totalPipes * 100) : 0}%)`],
      ['Unknown', unknown],
      ['Manual overrides', manual],
      ['Labels', st.activeLabels().length],
      ['Joining points', st.activeJoins().length],
    ]) {
      s.append(el('div', { class: 'kv' },
        el('span', { class: 'k' }, k), el('span', { class: 'v' }, String(v))));
    }
    wrap.append(s);

    const lg = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, `Classes (${counts.length})`));
    for (const [code, n] of counts) {
      lg.append(el('div', {
        class: 'legend-item',
        onclick: () => this.app.selectByClass(code),
        title: `Select all ${code} pipes`,
      },
        el('span', { class: 'layer-swatch',
                     style: `background:${classColor(code)}` }),
        el('span', { class: 'lg-name' }, code),
        el('span', { class: 'lg-n' }, String(n))));
    }
    wrap.append(lg);
    return wrap;
  }

  /* ── multi-selection ─────────────────────────────────────────────────── */
  _multi(sel) {
    const wrap = el('div');
    const byKind = sel.reduce((m, s) => (m[s.kind] = (m[s.kind] || 0) + 1, m), {});
    wrap.append(el('div', { class: 'section' },
      el('div', { class: 'section-title' }, `${sel.length} objects selected`),
      el('div', { class: 'card' },
        ...Object.entries(byKind).map(([k, n]) =>
          el('div', { class: 'kv' },
            el('span', { class: 'k' }, k + 's'),
            el('span', { class: 'v' }, String(n)))))));

    const pipes = sel.filter(s => s.kind === 'pipe');
    if (pipes.length) {
      const sec = el('div', { class: 'section' },
        el('div', { class: 'section-title' }, 'Set class for all selected pipes'));
      const combo = new ClassCombo(this.app, '', (code) => {
        this.app.history.run(`Set class of ${pipes.length} pipes`, () => {
          for (const p of pipes) this.store.setPipeClass(p.id, code);
        });
        this.app.renderer.invalidate();
      });
      sec.append(combo.element);
      wrap.append(sec);
    }

    const row = el('div', { class: 'btn-row' });
    if (pipes.length >= 2) {
      row.append(el('button', {
        class: 'btn', onclick: () => this.app.mergeSelectedPipes(),
      }, 'Merge'));
    }
    row.append(el('button', {
      class: 'btn danger', onclick: () => this.app.deleteSelection(),
    }, 'Delete all'));
    wrap.append(row);
    return wrap;
  }

  /* ── pipe ────────────────────────────────────────────────────────────── */
  _pipe(p) {
    const wrap = el('div');
    const nJoins = this.store.activeJoins().filter(j => j.pipeId === p.id).length;

    wrap.append(el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Pipe'),
      el('div', { class: 'card accent' },
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'ID'),
          el('span', { class: 'v' }, p.id)),
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Class'),
          el('span', {
            class: 'v',
            style: `color:${classColor(p.type)}`,
          }, p.type)),
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Assignment'),
          el('span', { class: `pill ${p.source === 'manual' ? 'manual' : 'auto'}` },
            el('span', { class: 'dot' }),
            p.source === 'manual' ? 'Manual override' : 'Automatic')),
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Geometry'),
          el('span', { class: 'v' },
            p.origin === 'manual' ? 'user drawn' : 'detected')))));

    // class editor
    const sec = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Assigned class'));
    const combo = new ClassCombo(this.app, p.type, (code) => {
      this.app.history.run(`Set ${p.id} class`, () =>
        this.store.setPipeClass(p.id, code));
      this.app.renderer.invalidate();
      this.app.toast(`${p.id} → ${code} (manual override)`);
    });
    sec.append(combo.element);
    if (p.source === 'manual') {
      sec.append(el('button', {
        class: 'btn block ghost',
        style: 'margin-top:8px',
        onclick: () => {
          this.app.history.run(`Reset ${p.id} to automatic`, () =>
            this.store.resetPipeClassToAuto(p.id));
          this.app.toast('Reset to automatic — re-run assignment to recompute');
        },
      }, 'Reset to Automatic'));
    }
    wrap.append(sec);

    // statistics
    const stats = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Statistics'));
    for (const [k, v] of [
      ['Vertices', String(p.polygon.length - 1)],
      ['Area', `${fmt(p.area, 1)} pt²`],
      ['Joining points', String(nJoins)],
    ]) {
      stats.append(el('div', { class: 'kv' },
        el('span', { class: 'k' }, k), el('span', { class: 'v' }, v)));
    }
    wrap.append(stats);

    // connected joins
    const joins = this.store.activeJoins().filter(j => j.pipeId === p.id);
    if (joins.length) {
      const js = el('div', { class: 'section' },
        el('div', { class: 'section-title' }, 'Connected joining points'));
      for (const j of joins) {
        js.append(el('div', {
          class: 'legend-item',
          onclick: () => this.app.focusObject('join', j.id),
        },
          el('span', { class: 'layer-swatch',
                       style: `background:${classColor(j.code)}` }),
          el('span', { class: 'lg-name' }, `${j.id} · ${j.code}`)));
      }
      wrap.append(js);
    }

    wrap.append(el('div', { class: 'btn-row' },
      el('button', { class: 'btn', onclick: () => this.app.tools.activate('vertex') }, 'Edit'),
      el('button', { class: 'btn', onclick: () => this.app.tools.activate('split') }, 'Split'),
      el('button', { class: 'btn', onclick: () => this.app.simplifySelected() }, 'Simplify'),
      el('button', { class: 'btn', onclick: () => this.app.smoothSelected() }, 'Smooth')));

    wrap.append(el('div', { class: 'btn-row' },
      p.deleted
        ? el('button', { class: 'btn', onclick: () => this.app.restoreSelection() }, 'Restore')
        : el('button', { class: 'btn danger', onclick: () => this.app.deleteSelection() }, 'Delete pipe')));
    return wrap;
  }

  /* ── label ───────────────────────────────────────────────────────────── */
  _label(l) {
    const wrap = el('div');
    const join = this.store.activeJoins().find(j => j.labelId === l.id);
    const [x0, y0, x1, y1] = l.rect;

    wrap.append(el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Label'),
      el('div', { class: 'card accent' },
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'ID'), el('span', { class: 'v' }, l.id)),
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'OCR confidence'),
          el('span', { class: 'v' },
            l.conf < 0 ? 'n/a' : `${fmt(l.conf, 0)}%`)),
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Source'),
          el('span', { class: `pill ${l.source === 'manual' ? 'manual' : 'auto'}` },
            el('span', { class: 'dot' }),
            l.source === 'manual' ? 'Manual' : 'Detected')))));

    const sec = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Label text'));
    if (l.score >= 0) {
      sec.append(el('div', { class: 'kv' },
        el('span', { class: 'k' }, 'Detector score'),
        el('span', { class: 'v' }, `${Math.round(l.score * 100)}%`)));
    }
    if (l.text) {
      // Everything read inside the box, not just the part that parsed as a
      // code: label boxes carry extra rows (installation elevation, room,
      // fall, notes) and the user needs to see them. Multi-row text is shown
      // as its own block so the rows stay on separate lines.
      const rows = l.text.split('\n').filter((t) => t.trim());
      const same = rows.length === 1 && rows[0].trim() === (l.code || '').trim();
      if (!same) {
        const box = el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Read'));
        const v = el('span', { class: 'v', style: 'white-space:pre-wrap' },
          rows.join('\n'));
        box.append(v);
        sec.append(box);
      }
    }
    if (l.inherited) {
      // the note came from the LAST label on the same connection line: one
      // ladder line serves the stack and the note is written once, at the end
      sec.append(el('div', { class: 'kv' },
        el('span', { class: 'k' }, 'Shared note'),
        el('span', { class: 'v' }, l.inherited)));
    }
    const combo = new ClassCombo(this.app, l.code, (code) => {
      this.app.history.run(`Edit ${l.id} text`, () => {
        l.code = code;
        l.source = 'manual';
        this.store.touch('label:text', l.id);
      });
      this.app.renderer.invalidateObject('label', l.id);
      this.app.renderer.invalidate();
    }, { free: true });
    sec.append(combo.element);
    wrap.append(sec);

    // Sewer (S) runs are gravity-driven: the installation elevation written
    // next to the code decides which stretch the label describes, before
    // diameter or position do.  Not read by OCR yet, so it is entered here.
    const ev = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Installation elevation (m)'));
    const evIn = el('input', {
      type: 'number', step: '0.01', class: 'num',
      value: l.elevation == null ? '' : String(l.elevation),
      placeholder: 'e.g. 12.30 — sewer labels only',
    });
    evIn.addEventListener('change', () => {
      const v = evIn.value.trim() === '' ? null : parseFloat(evIn.value);
      if (v !== null && !Number.isFinite(v)) return;
      this.app.history.run(`Set ${l.id} elevation`, () => {
        l.elevation = v;
        this.store.touch('label:text', l.id);
      });
    });
    ev.append(evIn);
    wrap.append(ev);

    const bb = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Bounding box'));
    for (const [k, v] of [
      ['x', `${fmt(x0)} → ${fmt(x1)}`],
      ['y', `${fmt(y0)} → ${fmt(y1)}`],
      ['size', `${fmt(x1 - x0)} × ${fmt(y1 - y0)} pt`],
    ]) {
      bb.append(el('div', { class: 'kv' },
        el('span', { class: 'k' }, k), el('span', { class: 'v' }, v)));
    }
    wrap.append(bb);

    wrap.append(el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Connected joining point'),
      join
        ? el('div', {
            class: 'legend-item',
            onclick: () => this.app.focusObject('join', join.id),
          },
            el('span', { class: 'layer-swatch',
                         style: `background:${classColor(join.code)}` }),
            el('span', { class: 'lg-name' },
              `${join.id}${join.pipeId ? ' → ' + join.pipeId : ' (orphan)'}`))
        : el('div', { class: 'kv' },
            el('span', { class: 'k' }, 'none'),
            el('span', { class: 'v' }, '—'))));

    wrap.append(el('div', { class: 'btn-row' },
      el('button', { class: 'btn', onclick: () => this.app.duplicateSelection() }, 'Duplicate'),
      el('button', { class: 'btn', onclick: () => this.app.tools.activate('join') }, 'Add join'),
      el('button', { class: 'btn danger', onclick: () => this.app.deleteSelection() }, 'Delete')));
    return wrap;
  }

  /* ── joining point ───────────────────────────────────────────────────── */
  _join(j) {
    const wrap = el('div');
    wrap.append(el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Joining point'),
      el('div', { class: 'card accent' },
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'ID'), el('span', { class: 'v' }, j.id)),
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Class'),
          el('span', { class: 'v', style: `color:${classColor(j.code)}` }, j.code || '—')),
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Coordinates'),
          el('span', { class: 'v' }, `${fmt(j.point[0])}, ${fmt(j.point[1])}`)),
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Capture radius'),
          el('span', { class: 'v' }, `${fmt(j.radius ?? 6, 1)} pt`)),
        j.conf >= 0 ? el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Detector score'),
          el('span', { class: 'v' }, `${fmt(j.conf, 0)}%`)) : null,
        el('div', { class: 'kv' },
          el('span', { class: 'k' }, 'Source'),
          el('span', { class: `pill ${j.source === 'manual' ? 'manual' : 'auto'}` },
            el('span', { class: 'dot' }),
            j.source === 'manual' ? 'Manual' : 'Detected')))));

    // resizable capture radius
    const rad = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Capture radius'));
    const cur = j.radius ?? 6;
    const num = el('input', {
      class: 'input', type: 'number', step: '0.5', min: '1.5', max: '60',
      value: String(cur),
    });
    const slider = el('input', {
      type: 'range', min: '1.5', max: '40', step: '0.5', value: String(cur),
    });
    const apply = (v, commit) => {
      const r = parseFloat(v);
      if (!isFinite(r)) return;
      if (commit) this.app.history.begin(`Resize ${j.id}`);
      this.store.setJoinRadius(j.id, r);
      if (commit) this.app.history.commit();
      num.value = String(j.radius);
      slider.value = String(j.radius);
      this.app.renderer.invalidateObject('join', j.id);
      this.app.renderer.invalidate();
    };
    slider.addEventListener('input', () => apply(slider.value, false));
    slider.addEventListener('change', () => apply(slider.value, true));
    num.addEventListener('change', () => apply(num.value, true));
    rad.append(el('div', { class: 'row' }, num));
    rad.append(slider);
    rad.append(el('div', { class: 'hint', style: 'margin-top:6px' },
      'Every pipe within this radius, on the side this joining point claims, ' +
      'takes its class. Drag the square handle on the circle, or use ' +
      '[ and ].'));
    wrap.append(rad);

    const links = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Connections'));
    const reached = (j.pipeIds && j.pipeIds.length) ? j.pipeIds
                  : (j.pipeId ? [j.pipeId] : []);
    links.append(el('div', { class: 'kv' },
      el('span', { class: 'k' }, `Pipes (${reached.length})`),
      reached.length
        ? el('span', { class: 'v' },
            ...reached.slice(0, 6).map((pid, i) =>
              el('a', { style: 'cursor:pointer;color:var(--accent)',
                        onclick: () => this.app.focusObject('pipe', pid) },
                 (i ? ', ' : '') + pid)),
            reached.length > 6 ? ` +${reached.length - 6}` : null)
        : el('span', { class: 'v', style: 'color:var(--amber)' }, 'not connected')));
    links.append(el('div', { class: 'kv' },
      el('span', { class: 'k' }, 'Label'),
      j.labelId
        ? el('a', { class: 'v', style: 'cursor:pointer;color:var(--accent)',
                    onclick: () => this.app.focusObject('label', j.labelId) }, j.labelId)
        : el('span', { class: 'v' }, '—')));
    wrap.append(links);

    const sec = el('div', { class: 'section' },
      el('div', { class: 'section-title' }, 'Class'));
    sec.append(new ClassCombo(this.app, j.code, (code) => {
      this.app.history.run(`Set ${j.id} class`, () => {
        j.code = code;
        j.labelId = null;              // detached from its label on purpose
        this.store.touch('join:move', j.id);
      });
      this.app.renderer.invalidate();
    }).element);
    wrap.append(sec);

    wrap.append(el('div', { class: 'btn-row' },
      el('button', { class: 'btn', onclick: () => this.app.snapJoinToPipe(j.id) }, 'Snap to pipe'),
      el('button', { class: 'btn danger', onclick: () => this.app.deleteSelection() }, 'Delete')));
    return wrap;
  }
}
