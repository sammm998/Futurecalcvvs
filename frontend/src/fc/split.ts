/* Att dela en text i rader utan att gissa var raderna går.
 *
 * En radmask kräver att man vet var webbläsaren bröt texten, och det vet bara webbläsaren. Ordet läggs därför
 * ut som egna spann först, deras översta kant läses av, och de som står på samma kant hör till samma rad.
 * Resultatet är rätt vid varje bredd, varje typsnittsstorlek och varje språk - också när ett ord är så långt
 * att det får en rad för sig själv.
 *
 * Texten som läsaren hör ligger kvar: elementet får `aria-label` med originalet och bitarna göms för
 * uppläsning. En uppläsare ska höra en mening, inte sjutton ord.
 */

export type Split = { lines: HTMLElement[]; inners: HTMLElement[]; restore: () => void };

function wrapWords(el: HTMLElement): HTMLElement[] {
  const text = el.textContent || "";
  el.textContent = "";
  const out: HTMLElement[] = [];
  for (const word of text.split(/(\s+)/)) {
    if (!word) continue;
    if (/^\s+$/.test(word)) { el.appendChild(document.createTextNode(word)); continue; }
    const s = document.createElement("span");
    s.textContent = word;
    s.style.display = "inline-block";
    el.appendChild(s);
    out.push(s);
  }
  return out;
}

/** Dela i rader. Varje rad blir `.fc-line > .fc-line-in`, där den yttre klipper och den inre rör sig. */
export function splitLines(el: HTMLElement): Split {
  const original = el.textContent || "";
  const html = el.innerHTML;
  const words = wrapWords(el);
  if (!words.length) return { lines: [], inners: [], restore: () => { el.innerHTML = html; } };

  const rows: HTMLElement[][] = [];
  let top = Number.NaN;
  for (const w of words) {
    const t = Math.round(w.offsetTop);
    if (Number.isNaN(top) || Math.abs(t - top) > 2) { rows.push([]); top = t; }
    rows[rows.length - 1].push(w);
  }

  el.textContent = "";
  const lines: HTMLElement[] = [];
  const inners: HTMLElement[] = [];
  for (const row of rows) {
    const outer = document.createElement("span");
    outer.className = "fc-line";
    const inner = document.createElement("span");
    inner.className = "fc-line-in";
    inner.textContent = row.map((w) => w.textContent).join(" ");
    outer.appendChild(inner);
    el.appendChild(outer);
    lines.push(outer);
    inners.push(inner);
  }
  el.setAttribute("aria-label", original);
  for (const l of lines) l.setAttribute("aria-hidden", "true");
  return { lines, inners, restore: () => { el.innerHTML = html; el.removeAttribute("aria-label"); } };
}

/** Dela i ord. Varje ord blir `.fc-word > .fc-word-in`. */
export function splitWords(el: HTMLElement): Split {
  const original = el.textContent || "";
  const html = el.innerHTML;
  const text = original;
  el.textContent = "";
  const lines: HTMLElement[] = [];
  const inners: HTMLElement[] = [];
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const outer = document.createElement("span");
    outer.className = "fc-word";
    const inner = document.createElement("span");
    inner.className = "fc-word-in";
    inner.textContent = word;
    outer.appendChild(inner);
    el.appendChild(outer);
    el.appendChild(document.createTextNode(" "));
    lines.push(outer);
    inners.push(inner);
  }
  el.setAttribute("aria-label", original);
  for (const l of lines) l.setAttribute("aria-hidden", "true");
  return { lines, inners, restore: () => { el.innerHTML = html; el.removeAttribute("aria-label"); } };
}

/** Dela i tecken. Bara för korta ord - ett stycke i tecken är hundratals element och lönar sig aldrig. */
export function splitChars(el: HTMLElement): Split {
  const original = el.textContent || "";
  const html = el.innerHTML;
  el.textContent = "";
  const lines: HTMLElement[] = [];
  const inners: HTMLElement[] = [];
  for (const ch of Array.from(original)) {
    if (ch === " ") { el.appendChild(document.createTextNode(" ")); continue; }
    const outer = document.createElement("span");
    outer.className = "fc-char";
    const inner = document.createElement("span");
    inner.className = "fc-char-in";
    inner.textContent = ch;
    outer.appendChild(inner);
    el.appendChild(outer);
    lines.push(outer);
    inners.push(inner);
  }
  el.setAttribute("aria-label", original);
  for (const l of lines) l.setAttribute("aria-hidden", "true");
  return { lines, inners, restore: () => { el.innerHTML = html; el.removeAttribute("aria-label"); } };
}
