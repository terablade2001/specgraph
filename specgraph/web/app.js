/* Editor UI. Plain JavaScript, no libraries, no build step.
   Rule: all text from the model goes through textContent/setAttribute, never innerHTML. */
'use strict';

const S = { token: null, model: null, head: null, me: {}, locks: {}, problems: [], integrity: [], treeDrag: null,
            open: [], active: null, sel: null, multi: [], expanded: new Set(), views: {}, drag: null, panel: null,
            linkType: null, undo: { steps: 0, next: null }, version: '' };
const $ = (id) => document.getElementById(id);
const SVGNS = 'http://www.w3.org/2000/svg';

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const k in (attrs || {})) {
    const v = attrs[k];
    if (v == null || v === false) continue;
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'class') e.className = v;
    else if (k === 'style') e.style.cssText = v;
    else if (k === 'value' || k === 'checked' || k === 'disabled' || k === 'selected' || k === 'draggable' || k === 'hidden') e[k] = v;
    else e.setAttribute(k, v);
  }
  kids.flat(Infinity).forEach((c) => { if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c))); });
  return e;
}
function sv(tag, attrs, ...kids) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in (attrs || {})) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
  kids.flat(Infinity).forEach((c) => { if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c))); });
  return e;
}
/* append that accepts nested arrays and skips null/false */
function put(parent, ...kids) {
  kids.flat(Infinity).forEach((c) => { if (c != null && c !== false) parent.append(c.nodeType ? c : document.createTextNode(String(c))); });
  return parent;
}
function clear(e) { while (e.firstChild) e.removeChild(e.firstChild); return e; }

// ---- server ---------------------------------------------------------------
async function call(method, path, body) {
  const r = await fetch(path, { method, headers: Object.assign({ 'X-specgraph-Token': S.token },
    body ? { 'Content-Type': 'application/json' } : {}), body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({ error: 'bad answer from the tool' }));
  if (!r.ok) { const e = new Error(data.error || ('error ' + r.status)); e.code = data.code; throw e; }
  return data;
}
function get(path, params) {
  const q = new URLSearchParams();
  for (const k in (params || {})) if (params[k] != null && params[k] !== '') q.set(k, params[k]);
  return call('GET', path + (q.toString() ? '?' + q : ''));
}
function setState(st) {
  ['model', 'head', 'me', 'locks', 'problems', 'integrity', 'undo', 'version'].forEach((k) => { S[k] = st[k]; });
  const m = S.model;
  S.open = S.open.filter((d) => m.diagrams[d]);
  if (!m.diagrams[S.active]) S.active = S.open[0] || null;
  if (S.sel && !(m[S.sel.kind + 's'] || {})[S.sel.id]) S.sel = null;
  if (!S.linkType || !m.config.linkTypes[S.linkType] || m.config.linkTypes[S.linkType].retired) {
    S.linkType = Object.keys(m.config.linkTypes).find((k) => !m.config.linkTypes[k].retired) || null;
  }
}
async function load() {
  try { setState(await get('/api/state')); S.loadError = null; }
  catch (e) { S.loadError = e.message; }
  render();
}
/* Apply operations. Returns the results array, or null when refused.
   `confirmed` is set only after the person said yes in a dialog; the server
   refuses to delete an element without it. */
async function post(ops, confirmed) {
  try {
    const st = await call('POST', '/api/ops', confirmed ? { base: S.head, ops, confirmed: true } : { base: S.head, ops });
    setState(st); render();
    return st.results;
  } catch (e) {
    toast(e.message, true);
    await load();
    return null;
  }
}
const op = (name, args) => post([{ op: name, args }]);
/* Take back the last change made in this editor session (the server keeps the steps). */
async function undo() {
  if (!S.undo.steps || readOnly()) return toast('Nothing to undo');
  const what = S.undo.next;
  try { setState(await call('POST', '/api/undo', { base: S.head })); render(); toast('Undone: ' + what); }
  catch (e) { toast(e.message, true); await load(); }
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); }
  catch (e) {  // clipboard API refused: fall back to a hidden text box
    const t = h('textarea', { value: text, style: 'position:fixed;opacity:0' });
    document.body.appendChild(t); t.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch (x) { ok = false; }
    t.remove();
    if (!ok) return toast('Could not copy; select the id and press Ctrl+C', true);
  }
  toast('Id copied');
}
function idLine(id) {
  return h('div', { class: 'idline', title: 'Unique id' }, h('span', { class: 'idtext' }, id),
    h('button', { class: 'copy', title: 'Copy id', 'aria-label': 'Copy id', onclick: () => copyText(id) }, '⧉'));
}

function toast(msg, err) {
  const t = $('toast'); t.textContent = msg; t.className = err ? 'err' : ''; t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { t.hidden = true; }, err ? 7000 : 2500);
}

// ---- model helpers --------------------------------------------------------
const cfg = () => S.model.config;
/* Colours go into styles and drawings: only #rrggbb is used, whatever a hand-edited file holds (security review 0.3.0) */
const hex = (c, dflt) => (/^#[0-9a-fA-F]{6}$/.test(c) ? c : dflt);
const stOf = (key) => { const st = cfg().stereotypes[key] || { label: key, icon: '?', shape: 'rect', fields: {} };
  return Object.assign({}, st, { fill: hex(st.fill, '#eeeeee'), border: hex(st.border, '#666666') }); };
const statusOf = (key) => { const s = cfg().statuses[key] || { label: key, symbol: '?' }; return Object.assign({}, s, { color: hex(s.color, '#666666') }); };
const ltOf = (key) => { const lt = cfg().linkTypes[key] || { label: key, lineStyle: 'solid', sourceArrow: 'none', targetArrow: 'open', showLabel: true, routing: 'straight' };
  return Object.assign({}, lt, { color: hex(lt.color, '#666666') }); };
const elName = (el) => (el.label ? el.label + ' ' : '') + el.topic;
const byName = (f) => (a, b) => f(a[1]).localeCompare(f(b[1]));
function allowedStatuses(stKey, current) {
  const st = stOf(stKey), all = cfg().statuses;
  return Object.keys(all).filter((k) => (st.statuses == null || st.statuses.includes(k)) && (!all[k].retired || k === current))
    .sort((a, b) => (all[a].order || 0) - (all[b].order || 0));
}
function folderPath(fid) {
  const parts = [];
  for (let i = 0; fid && S.model.folders[fid] && i < 50; i++) { parts.unshift(S.model.folders[fid].name); fid = S.model.folders[fid].parent; }
  return parts.join('/');
}
const lockOf = (fid) => S.locks[fid] || null;
const lockedOut = (fid) => { const l = lockOf(fid); return !!l && l.owner !== S.me.user; };
const readOnly = () => !S.me.user || S.integrity.length > 0;
function select(kind, id) { S.sel = id ? { kind, id } : null; S.multi = id && kind === 'element' ? [id] : []; renderTree(); renderDiagram(); renderProps(); }
/* The selected nodes of the open diagram, in the order they were selected; the last one is S.sel (ADR-027). */
function selNodes() {
  const d = S.active && S.model.diagrams[S.active];
  return d ? selElements().filter((id) => d.nodes[id]) : [];
}
/* The selected elements, in the order they were selected; the last one is S.sel. The explorer shows all of
   them; the diagram works on those that are on it (selNodes), whose last one is its reference. */
function selElements() {
  if (!S.sel || S.sel.kind !== 'element' || !S.model.elements[S.sel.id]) return [];
  if (!S.multi.includes(S.sel.id)) return [S.sel.id];
  return S.multi.filter((id) => S.model.elements[id] && id !== S.sel.id).concat([S.sel.id]);
}
/* Ctrl+click or Shift+click, on the diagram or in the explorer: add or remove one element. */
function toggleNode(id) {
  const cur = selElements();
  selectNodes(cur.includes(id) ? cur.filter((x) => x !== id) : cur.concat([id]));
}
function selectNodes(ids) {
  S.multi = ids.slice(); S.sel = ids.length ? { kind: 'element', id: ids[ids.length - 1] } : null;
  renderTree(); renderDiagram(); renderProps();
}
/* Align the selected nodes to the last selected one (ADR-027, ADR-028). axis 'x' is horizontal
   alignment (left, centre, right edges), 'y' vertical (top, centre, bottom); where is
   'start', 'center' or 'end'. One change, one undo step; not snapped to the grid. */
const ALIGN = [['x', 'Horizontal', [['start', 'Left', 'Ctrl+Shift+1'], ['center', 'Center', 'Ctrl+Shift+2'], ['end', 'Right', 'Ctrl+Shift+3']]],
               ['y', 'Vertical', [['start', 'Top', 'Alt+Shift+1'], ['center', 'Center', 'Alt+Shift+2'], ['end', 'Bottom', 'Alt+Shift+3']]]];
function align(axis, where) {
  const ids = selNodes(), d = S.active && S.model.diagrams[S.active];
  if (ids.length < 2) return toast('Select two or more elements on the diagram first');
  const ref = d.nodes[ids[ids.length - 1]], size = axis === 'x' ? 'w' : 'h', f = { start: 0, center: 0.5, end: 1 }[where];
  const line = ref[axis] + ref[size] * f;
  const ops = ids.slice(0, -1).map((id) => ({ op: 'diagram.layout', args: { diagram: S.active, element: id, [axis]: Math.round(line - d.nodes[id][size] * f) } }))
    .filter((o) => o.args[axis] !== d.nodes[o.args.element][axis]);
  if (ops.length) post(ops);
}
const alignMenu = () => ['Align', ALIGN.map(([axis, label, wheres]) => [label, wheres.map(([w, l, key]) => [l + ' (' + key + ')', () => align(axis, w)])])];
function chip(stKey) {
  const st = stOf(stKey);
  const attrs = { class: 'chip', style: 'background:' + st.fill + ';border-color:' + st.border + ';color:' + st.border };
  if (st.description) attrs.title = st.description;   // ADR-033: the type's meaning in this project
  return h('span', attrs,
    (st.icon ? st.icon + ' ' : '') + st.label);
}

// ---- render: bar and banners ---------------------------------------------
function render() {
  if (!S.model) {
    put(clear($('banner')), h('div', { class: 'err' }, S.loadError || 'Loading…'));
    return;
  }
  renderBar(); renderTree(); renderTabs(); renderDiagram(); renderProps(); renderPanel();
}
function renderBar() {
  const errs = S.problems.filter((p) => p.level === 'error').length + S.integrity.length;
  const warns = S.problems.length - S.problems.filter((p) => p.level === 'error').length;
  const sts = cfg().stereotypes, stats = cfg().statuses;
  const old = { q: ($('q') || {}).value || '', st: ($('qst') || {}).value || '', ss: ($('qss') || {}).value || '', un: ($('qun') || {}).checked };
  const go = () => doSearch({ q: $('q').value, stereotype: $('qst').value, status: $('qss').value, unused: $('qun').checked ? '1' : '' });
  put(clear($('bar')), 
    h('span', { class: 'name', title: 'Version of this tool' }, 'specgraph', h('span', { class: 'ver' }, ' ' + (S.version || ''))),
    h('input', { id: 'q', type: 'search', placeholder: 'Search id, label or text…', value: old.q, onkeydown: (e) => { if (e.key === 'Enter') go(); } }),
    h('select', { id: 'qst', title: 'Stereotype filter' }, h('option', { value: '' }, 'any type'),
      Object.keys(sts).map((k) => h('option', { value: k, selected: k === old.st }, sts[k].label))),
    h('select', { id: 'qss', title: 'Status filter' }, h('option', { value: '' }, 'any status'),
      Object.keys(stats).map((k) => h('option', { value: k, selected: k === old.ss }, stats[k].label))),
    h('label', { title: 'Only elements that appear on no diagram' }, h('input', { id: 'qun', type: 'checkbox', checked: old.un }), 'unused'),
    h('button', { onclick: go }, 'Search'),
    h('span', { class: 'sp' }),
    h('button', { id: 'btnUndo', disabled: !S.undo.steps || readOnly(), onclick: undo,
      title: S.undo.steps ? 'Undo ' + S.undo.next + ' (Ctrl+Z). ' + S.undo.steps + ' step(s) kept.' : 'Nothing to undo' }, '↶ Undo'),
    h('button', { onclick: matrixDialog }, 'Matrix'),
    h('button', { id: 'btnCheck', onclick: () => showPanel({ kind: 'check' }) }, 'Check',
      errs ? h('span', { class: 'badge' }, errs) : warns ? h('span', { class: 'badge', style: 'background:#b45309' }, warns) : h('span', { class: 'badge ok' }, '✓')),
    h('button', { onclick: () => configDialog('stereotypes') }, 'Configure'),
    h('button', { onclick: usersDialog }, 'Users'),
    h('span', { class: 'who' }, S.me.user ? '👤 ' + S.me.user + (S.me.role === 'admin' ? ' (admin)' : '') : '👤 not identified'));
  const b = clear($('banner'));
  if (S.loadError) put(b, h('div', { class: 'err' }, S.loadError));
  if (S.me.error) put(b, h('div', { class: 'err' }, 'Read-only: ', h('code', {}, S.me.error)));
  if (S.integrity.length) put(b, h('div', { class: 'err' }, 'Read-only: ' + S.integrity[0] + ' ',
    h('button', { onclick: () => showPanel({ kind: 'check' }) }, 'Details')));
  if ((S.model.conflicts || []).length) put(b, h('div', {}, S.model.conflicts.length + ' merge conflict(s) need your decision. ',
    h('button', { onclick: () => showPanel({ kind: 'check' }) }, 'Resolve')));
}

// ---- render: folder tree --------------------------------------------------
const parentOf = (kind, x) => (kind === 'folder' ? (x.parent == null ? null : x.parent) : x.folder);
/* Ids of the sub-folders, diagrams or elements directly in a folder (null = top level), in the
   order of the explorer (ADR-024): by `order` when set, the rest after them by name. */
function kids(kind, fid) {
  const coll = S.model[kind + 's'], name = kind === 'element' ? elName : (x) => x.name;
  const ord = (x) => (Number.isInteger(x.order) ? x.order : Infinity);
  return Object.keys(coll).filter((id) => parentOf(kind, coll[id]) === fid)
    .sort((p, q) => (ord(coll[p]) - ord(coll[q])) || name(coll[p]).localeCompare(name(coll[q])));
}
/* Open or close a folder together with all its sub-folders (null = the whole tree). */
function setExpanded(fid, open) {
  const todo = fid ? [fid] : kids('folder', null);
  while (todo.length) { const f = todo.pop(); if (open) S.expanded.add(f); else S.expanded.delete(f); todo.push(...kids('folder', f)); }
  renderTree();
}
/* Where a dragged tree item would land on a row: before or after it (same kind: reorder), or into a folder. */
function dropZone(e, r, kind, id) {
  const d = S.treeDrag;
  if (!d || (d.kind === kind && (d.ids || [d.id]).includes(id))) return null;
  if (d.kind !== kind) return kind === 'folder' ? 'into' : null;
  const b = r.getBoundingClientRect(), y = (e.clientY - b.top) / b.height;
  if (kind === 'folder') return y < 0.3 ? 'before' : y > 0.7 ? 'after' : 'into';
  return y < 0.5 ? 'before' : 'after';
}
function markDrop(r, zone) {
  r.classList.remove('drop', 'drop-before', 'drop-after');
  if (zone) r.classList.add(zone === 'into' ? 'drop' : 'drop-' + zone);
}
function renderTree() {
  const m = S.model, root = clear($('tree'));
  // the other selected nodes of the open diagram: grey; the last selected (S.sel) keeps the blue of 'sel'
  const also = new Set(selElements().slice(0, -1));
  const toggle = (e, fid) => {
    e.stopPropagation();
    if (e.shiftKey) return setExpanded(fid, !S.expanded.has(fid));
    if (S.expanded.has(fid)) S.expanded.delete(fid); else S.expanded.add(fid);
    renderTree();
  };
  const row = (kind, id, depth, parts, dbl) => {
    const r = h('div', Object.assign({
      class: 'row' + (S.sel && S.sel.kind === kind && S.sel.id === id ? ' sel' : kind === 'element' && also.has(id) ? ' sel2' : ''), style: 'padding-left:' + (6 + depth * 14) + 'px',
      'data-kind': kind, 'data-id': id, draggable: true,
      ondragstart: (e) => {
        // a selected element takes the whole selection along; anything else moves alone
        const all = selElements(), ids = kind === 'element' && all.length > 1 && all.includes(id) ? all : [id];
        S.treeDrag = { kind, id, ids };
        e.dataTransfer.setData('text/plain', JSON.stringify({ kind, id, ids })); e.dataTransfer.effectAllowed = 'move';
      },
      ondragend: () => { S.treeDrag = null; },
      ondragover: (e) => { const z = dropZone(e, r, kind, id); markDrop(r, z); if (z) e.preventDefault(); },
      ondragleave: () => markDrop(r, null),
      ondrop: (e) => { const z = dropZone(e, r, kind, id); markDrop(r, null); if (z) { e.preventDefault(); e.stopPropagation(); dropOnRow(z, kind, id); } },
      onclick: (e) => treeClick(e, kind, id, dbl), oncontextmenu: (e) => treeMenu(e, kind, id) }), parts);
    return r;
  };
  function folder(fid, depth) {
    const f = m.folders[fid], open = S.expanded.has(fid), lock = lockOf(fid);
    put(root, row('folder', fid, depth, [
      h('span', { class: 'tw', title: 'Shift+click: with all sub-folders', onclick: (e) => toggle(e, fid) }, open ? '▾' : '▸'),
      '📁', h('span', { class: 't' }, f.name),
      lock ? h('span', { class: 'lk', title: 'Locked by ' + lock.owner + (lock.reason ? ': ' + lock.reason : '') }, '🔒 ' + lock.owner) : null],
      (e) => { if (e.ctrlKey || e.metaKey) setExpanded(fid, true); else if (e.altKey) setExpanded(fid, false); else toggle(e, fid); }));
    if (!open) return;
    kids('folder', fid).forEach((id) => folder(id, depth + 1));
    kids('diagram', fid).forEach((id) =>
      put(root, row('diagram', id, depth + 1, [h('span', { class: 'tw' }), '▦', h('span', { class: 't' }, m.diagrams[id].name)], () => openDiagram(id))));
    kids('element', fid).forEach((id) => { const e = m.elements[id];
      put(root, row('element', id, depth + 1, [h('span', { class: 'tw' }), chip(e.stereotype), h('span', { class: 't', title: e.topic }, elName(e)),
        hasNotes(e) ? h('span', { class: 'nt', title: notesTip(e) }, '📜') : null],
        () => findInDiagrams(id))); });
  }
  kids('folder', null).forEach((id) => folder(id, 0));
  put(root, h('div', { class: 'row mute', style: 'margin-top:6px', onclick: () => newFolder(null),
    ondragover: (e) => { if (S.treeDrag && S.treeDrag.kind === 'folder') e.preventDefault(); },
    ondrop: (e) => { e.preventDefault(); moveInto(S.treeDrag, null); } }, '+ top-level folder'));
  root.oncontextmenu = (e) => { if (e.target === root) { e.preventDefault(); menu(e, [['New top-level folder…', () => newFolder(null)], null,
    ['Expand all folders', () => setExpanded(null, true)], ['Collapse all folders', () => setExpanded(null, false)]]); } };
}
/* A click on a tree row selects it; a second click on the same row soon after is a double-click.
   Own detection: the first click re-draws the tree, so the browser's dblclick does not fire. */
function treeClick(e, kind, id, dbl) {
  if (kind === 'element' && (e.ctrlKey || e.metaKey || e.shiftKey)) { treeClick.last = null; return toggleNode(id); }
  const last = treeClick.last, now = Date.now();
  treeClick.last = { kind, id, t: now };
  if (last && last.kind === kind && last.id === id && now - last.t < 450) { treeClick.last = null; return dbl && dbl(e); }
  select(kind, id);
}
/* Find in explorer: open the folders above an item, select it and scroll it into view. */
function findInExplorer(kind, id) {
  const m = S.model, item = m[kind + 's'][id];
  if (!item) return;
  for (let f = kind === 'folder' ? item.parent : parentOf(kind, item); f; f = m.folders[f] && m.folders[f].parent) S.expanded.add(f);
  select(kind, id);
  const r = $('tree').querySelector('.row[data-kind="' + kind + '"][data-id="' + id + '"]');
  if (r) r.scrollIntoView({ block: 'nearest' });
}
function moveInto(d, fid) {
  S.treeDrag = null;
  if (!d) return;
  if (d.kind === 'folder' && d.id !== fid) op('folder.move', { id: d.id, parent: fid });
  else if (fid && d.kind === 'element') {
    const ops = (d.ids || [d.id]).filter((x) => S.model.elements[x] && S.model.elements[x].folder !== fid)
      .map((x) => ({ op: 'element.move', args: { id: x, folder: fid } }));
    if (ops.length) post(ops);
  }
  else if (fid && d.kind === 'diagram') op('diagram.move', { id: d.id, folder: fid });
  if (fid) S.expanded.add(fid);
}
/* Drop on a row of the tree: into a folder, or before/after an item of the same kind (a move
   to that folder when it comes from another one, and the new order, as one change). */
function dropOnRow(zone, kind, id) {
  const d = S.treeDrag, coll = S.model[kind + 's'];
  if (zone === 'into') return moveInto(d, id);
  S.treeDrag = null;
  if (!d || d.kind !== kind || !coll[d.id]) return;
  // the dragged items (a selection of elements, or one item) go there as a block, in their tree order
  const moved = (d.ids || [d.id]).filter((x) => coll[x]), set = new Set(moved);
  const parent = parentOf(kind, coll[id]), ids = kids(kind, parent).filter((x) => !set.has(x));
  const block = kids(kind, parent).filter((x) => set.has(x)).concat(moved.filter((x) => parentOf(kind, coll[x]) !== parent));
  ids.splice(ids.indexOf(id) + (zone === 'after' ? 1 : 0), 0, ...block);
  const ops = moved.filter((x) => parentOf(kind, coll[x]) !== parent)
    .map((x) => ({ op: kind + '.move', args: kind === 'folder' ? { id: x, parent } : { id: x, folder: parent } }));
  ops.push({ op: 'folder.order', args: { id: parent, kind: kind + 's', ids } });
  post(ops);
}
function newFolder(parent) {
  formDialog('New folder', [{ key: 'name', label: 'Name' }], async (v) => {
    const r = await op('folder.create', { name: v.name, parent });
    if (r) { if (parent) S.expanded.add(parent); select('folder', r[0]); }
    return !!r;
  });
}
function newElement(stKey, fid, place) {
  formDialog('New ' + stOf(stKey).label, [{ key: 'topic', label: 'Topic' }], async (v) => {
    const ops = [{ op: 'element.create', args: { stereotype: stKey, topic: v.topic, folder: fid } }];
    if (place) { const x = snap(place.x), y = snap(place.y);
      ops.push({ op: 'diagram.place', args: Object.assign({ diagram: place.diagram, element: '$0', x, y },
        autoOn() ? fitSize({ stereotype: stKey, topic: v.topic, label: guessLabel(stKey), folder: fid }, x, y, 190) : {}) }); }
    const r = await post(ops);
    if (r) { S.expanded.add(fid); select('element', r[0]); }
    return !!r;
  });
}
function newDiagram(fid) {
  formDialog('New diagram', [{ key: 'name', label: 'Name' }], async (v) => {
    const r = await op('diagram.create', { name: v.name, folder: fid });
    if (r) { S.expanded.add(fid); openDiagram(r[0]); }
    return !!r;
  });
}
function lockFolder(fid) {
  formDialog('Lock folder "' + S.model.folders[fid].name + '"', [{ key: 'reason', label: 'Reason (shown to everyone)', optional: true }],
    async (v) => !!(await op('folder.lock', { id: fid, reason: v.reason })));
}
/* A lock only says "someone works here": anyone may clear it, after a confirmation when it is not theirs. */
function unlockFolder(id) {
  const f = S.model.folders[id], l = f.lock;
  if (!l || l.owner === S.me.user) return op('folder.unlock', { id });
  confirmDialog('"' + f.name + '" is locked by ' + l.owner + (l.reason ? ' (' + l.reason + ')' : '') + ' since ' + l.at +
    '. A lock means someone is working there in isolation. Unlock it anyway?', () => post([{ op: 'folder.unlock', args: { id } }], true));
}
function treeMenu(e, kind, id) {
  e.preventDefault(); e.stopPropagation(); select(kind, id);
  const m = S.model, items = [];
  if (kind === 'folder') {
    Object.keys(cfg().stereotypes).filter((k) => !cfg().stereotypes[k].retired).forEach((k) => items.push(['New ' + stOf(k).label + '…', () => newElement(k, id)]));
    items.push(null, ['New diagram…', () => newDiagram(id)], ['New sub-folder…', () => newFolder(id)], null,
      ['Expand with sub-folders', () => setExpanded(id, true)], ['Collapse with sub-folders', () => setExpanded(id, false)], null);
    const own = m.folders[id].lock;
    items.push(own ? ['Unlock', () => unlockFolder(id)] : ['Lock…', () => lockFolder(id)]);
    items.push(['Delete folder…', () => deleteFolder(id)]);
  } else if (kind === 'diagram') {
    items.push(['Open', () => openDiagram(id)], ['Delete diagram', () => confirmDialog('Delete diagram "' + m.diagrams[id].name + '"? Its elements stay in the model.', () => op('diagram.delete', { id }))]);
  } else {
    items.push(['Find in all diagrams', () => findInDiagrams(id)], ['Trace', () => showPanel({ kind: 'trace', id })], ['History', () => showPanel({ kind: 'history', id })]);
    if (S.active && !m.diagrams[S.active].nodes[id]) items.push(['Place on current diagram', () => placeAtCenter(id)]);
    items.push(null, ['Delete from model…', () => deleteElement(id)]);
  }
  menu(e, items);
}

// ---- render: properties ---------------------------------------------------
function field(label, input, inline) { return h('div', { class: 'f' + (inline ? ' inline' : '') }, inline ? [input, h('label', {}, label)] : [h('label', {}, label), input]); }
/* Text input that saves when you leave it or press Enter. */
function textIn(value, save, o) {
  o = o || {};
  const e = h(o.area ? 'textarea' : 'input', Object.assign({ value: value == null ? '' : value, disabled: o.disabled },
    o.area ? { rows: o.rows || 3 } : { type: o.type || 'text' }));
  const commit = () => { if (e.value !== String(value == null ? '' : value)) save(e.value); };
  e.addEventListener('blur', commit);
  if (!o.area) e.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') e.blur(); });
  return e;
}
function selectIn(options, value, save, disabled) {
  return h('select', { disabled, onchange: (e) => save(e.target.value) },
    options.map(([k, label]) => h('option', { value: k, selected: k === value }, label)));
}
function renderProps() {
  const p = clear($('props')), m = S.model, sel = S.sel;
  if (!sel) {
    put(p, h('h3', {}, 'Properties'), h('p', { class: 'mute' }, 'Select something in the tree or on a diagram.'),
      h('p', { class: 'mute' }, 'Right-click folders, elements and the diagram background for actions. Drag elements from the tree onto a diagram. ' +
        'Drag items in the tree to move or reorder them. Double-click a folder to open or close it (Ctrl: with all sub-folders, Alt: close all). Drag the lines between the panes to resize them. ' +
        'Drag from the blue dot of a selected element to another element to link them. ' +
        'Ctrl+click or Shift+click elements, Shift+drag a rectangle, or Ctrl+A for all, to select several; drag one of them to move them all; right-click one of them for Align (left, center, right; top, center, bottom).'));
    return;
  }
  if (sel.kind === 'element') propsElement(p, sel.id);
  else if (sel.kind === 'link') propsLink(p, sel.id);
  else if (sel.kind === 'folder') propsFolder(p, sel.id);
  else propsDiagram(p, sel.id);
}
function lockNote(p, fid) {
  const l = lockOf(fid);
  if (l) put(p, h('div', { class: 'note' }, '🔒 Locked by ' + l.owner + (l.reason ? ' — ' + l.reason : '') + (l.owner === S.me.user ? ' (you)' : '. You cannot change it.')));
  return readOnly() || lockedOut(fid);
}
function propsElement(p, id) {
  const m = S.model, el = m.elements[id], st = stOf(el.stereotype);
  const up = (args) => {
    const ops = [{ op: 'element.update', args: Object.assign({ id }, args) }];
    if (autoOn() && ('topic' in args || 'label' in args || 'stereotype' in args)) {
      const after = Object.assign({}, el, args);
      if ('stereotype' in args && !('label' in args)) after.label = guessLabel(args.stereotype, id);
      ops.push(...fitOps(id, after));                    // same change, one undo step
    }
    return post(ops);
  };
  put(p, h('h3', {}, chip(el.stereotype), 'Element'), idLine(id));
  const many = selNodes().length;
  if (many > 1) put(p, h('div', { class: 'note' }, many + ' elements are selected on the diagram; this one, the last selected, is the reference for alignment.',
    ALIGN.map(([axis, label, wheres]) => h('div', { class: 'btns' }, h('span', { class: 'mute' }, label + ':'),
      wheres.map(([w, l, key]) => h('button', { 'data-align': axis + ':' + w, title: key, onclick: () => align(axis, w) }, l))))));
  const dis = lockNote(p, el.folder);
  put(p, 
    field('Label', textIn(el.label, (v) => up({ label: v }), { disabled: dis })),
    field('Topic', textIn(el.topic, (v) => up({ topic: v }), { area: true, rows: 2, disabled: dis })),
    field('Status', selectIn(allowedStatuses(el.stereotype, el.status).map((k) => [k, statusOf(k).symbol + ' ' + statusOf(k).label]), el.status, (v) => up({ status: v }), dis)),
    field('Stereotype', selectIn(Object.keys(cfg().stereotypes).filter((k) => !cfg().stereotypes[k].retired || k === el.stereotype).map((k) => [k, stOf(k).label]), el.stereotype, (v) => up({ stereotype: v }), dis)),
    field('Notes', textIn(el.notes, (v) => up({ notes: v }), { area: true, rows: 7, disabled: dis })));
  Object.entries(st.fields || {}).forEach(([k, f]) => {
    const cur = (el.fields || {})[k], set = (v) => up({ fields: { [k]: v } });
    let input;
    if (f.type === 'enum') input = selectIn([['', '—']].concat((f.options || []).map((o) => [o, o])), cur == null ? '' : cur, set, dis);
    else if (f.type === 'boolean') input = selectIn([['', '—'], ['y', 'yes'], ['n', 'no']], cur == null ? '' : cur ? 'y' : 'n', (v) => set(v === '' ? null : v === 'y'), dis);
    else if (f.type === 'number') input = textIn(cur, (v) => set(v === '' ? null : Number(v)), { type: 'number', disabled: dis });
    else if (f.type === 'date') input = textIn(cur, set, { type: 'date', disabled: dis });
    else input = textIn(cur, set, { area: f.type === 'text', disabled: dis });
    put(p, field(f.label, input));
  });
  put(p, field('Folder', h('div', {}, folderPath(el.folder))),
    field('Last changed', h('div', { id: 'modified' }, el.modified ? el.modified.at.slice(0, 16).replace('T', ' ') + ' UTC by ' + el.modified.by
      : 'not recorded yet (added with the next change to the model)')));
  put(p, h('div', { class: 'btns' },
    h('button', { onclick: () => findInExplorer('element', id) }, 'Find in explorer'),
    h('button', { onclick: () => findInDiagrams(id) }, 'Find in diagrams'),
    h('button', { onclick: () => showPanel({ kind: 'trace', id }) }, 'Trace'),
    h('button', { onclick: () => showPanel({ kind: 'history', id }) }, 'History'),
    S.active && m.diagrams[S.active].nodes[id] ? h('button', { onclick: () => op('diagram.remove', { diagram: S.active, element: id }) }, 'Remove from diagram') : null,
    h('button', { class: 'danger', onclick: () => deleteElement(id) }, 'Delete from model…')));
  const links = Object.entries(m.links).filter(([, l]) => l.source === id || l.target === id);
  if (links.length) {
    put(p, h('h3', {}, 'Links'));
    links.forEach(([lid, l]) => {
      const out = l.source === id, other = m.elements[out ? l.target : l.source];
      put(p, h('div', { class: 'row' }, h('span', { class: 'mute' }, (out ? '→ ' : '← ') + ltOf(l.type).label), ' ',
        h('span', { class: 'link t', onclick: () => select('element', out ? l.target : l.source) }, other ? elName(other) : '?'),
        h('span', { class: 'lk link', title: 'Link properties', onclick: () => select('link', lid) }, '✎')));
    });
  }
}
function propsLink(p, id) {
  const m = S.model, l = m.links[id], a = m.elements[l.source], b = m.elements[l.target];
  put(p, h('h3', {}, 'Link'), idLine(id));
  const dis = lockNote(p, a.folder);
  put(p, 
    field('From', h('div', { class: 'link', onclick: () => select('element', l.source) }, elName(a))),
    field('To', h('div', { class: 'link', onclick: () => select('element', l.target) }, elName(b))),
    field('Type', selectIn(Object.keys(cfg().linkTypes).filter((k) => !cfg().linkTypes[k].retired || k === l.type).map((k) => [k, ltOf(k).label]), l.type, (v) => op('link.update', { id, type: v }), dis)),
    field('Text on the link', textIn(l.label, (v) => op('link.update', { id, label: v }), { disabled: dis })));
  const d = S.active && m.diagrams[S.active];
  if (d && d.nodes[l.source] && d.nodes[l.target]) {
    const o = d.links[id] || {}, ddis = readOnly() || lockedOut(d.folder);
    put(p, h('h3', {}, 'On diagram "' + d.name + '"'),
      field('Routing', selectIn([['', 'type default (' + ltOf(l.type).routing + ')'], ['straight', 'straight'], ['auto', 'automatic'], ['custom', 'user-defined']],
        o.routing || '', (v) => op('diagram.link', { diagram: S.active, link: id, routing: v || null }), ddis)),
      h('p', { class: 'mute' }, 'User-defined: double-click the line to add a bend, drag bends, double-click a bend to remove it.'),
      h('div', { class: 'btns' },
        h('button', { disabled: ddis, onclick: () => op('diagram.link', { diagram: S.active, link: id, hidden: !o.hidden }) }, o.hidden ? 'Show on this diagram' : 'Hide on this diagram'),
        h('button', { disabled: ddis, onclick: () => op('diagram.link', { diagram: S.active, link: id, reset: true }) }, 'Reset shape')));
  }
  put(p, h('div', { class: 'btns' }, h('button', { class: 'danger', disabled: dis, onclick: () => confirmDialog('Delete this link from the model?', () => op('link.delete', { id })) }, 'Delete link')));
}
function propsFolder(p, id) {
  const f = S.model.folders[id];
  put(p, h('h3', {}, '📁 Folder'), idLine(id));
  const dis = lockNote(p, id);
  put(p, field('Name', textIn(f.name, (v) => op('folder.update', { id, name: v }), { disabled: dis })),
    field('Path', h('div', {}, folderPath(id))),
    h('div', { class: 'btns' },
      h('button', { onclick: () => findInExplorer('folder', id) }, 'Find in explorer'),
      f.lock ? h('button', { onclick: () => unlockFolder(id) }, 'Unlock') : h('button', { onclick: () => lockFolder(id) }, 'Lock…'),
      h('button', { class: 'danger', onclick: () => deleteFolder(id) }, 'Delete folder…')),
    h('p', { class: 'mute' }, 'A lock tells others that someone works here: nobody else changes this folder, its sub-folders and everything in them, or links to it, until it is unlocked. Anyone can unlock it after a confirmation.'));
}
function propsDiagram(p, id) {
  const d = S.model.diagrams[id];
  put(p, h('h3', {}, '▦ Diagram'), idLine(id));
  const dis = lockNote(p, d.folder);
  put(p, field('Name', textIn(d.name, (v) => op('diagram.update', { id, name: v }), { disabled: dis })),
    field('Folder', h('div', {}, folderPath(d.folder))),
    h('div', { class: 'btns' }, h('button', { onclick: () => openDiagram(id) }, 'Open'),
      h('button', { onclick: () => findInExplorer('diagram', id) }, 'Find in explorer'),
      h('button', { class: 'danger', onclick: () => confirmDialog('Delete diagram "' + d.name + '"? Its elements stay in the model.', () => op('diagram.delete', { id })) }, 'Delete diagram')));
  const hidden = Object.entries(d.links).filter(([, o]) => o.hidden);
  if (hidden.length) {
    put(p, h('h3', {}, 'Hidden links'));
    hidden.forEach(([lid]) => { const l = S.model.links[lid]; put(p, h('div', { class: 'row' },
      h('span', { class: 't' }, elName(S.model.elements[l.source]) + ' → ' + elName(S.model.elements[l.target])),
      h('span', { class: 'lk link', onclick: () => op('diagram.link', { diagram: id, link: lid, hidden: false }) }, 'show'))); });
  }
}

// ---- diagrams: tabs and tools ---------------------------------------------
function view(did) { return S.views[did] || (S.views[did] = { x: 40, y: 40, k: 1 }); }
function openDiagram(did, focusEl) {
  if (!S.open.includes(did)) S.open.push(did);
  S.active = did;
  if (focusEl) {
    S.sel = { kind: 'element', id: focusEl };
    const n = S.model.diagrams[did].nodes[focusEl], r = $('canvas').getBoundingClientRect(), v = view(did);
    if (n) { v.x = r.width / 2 - (n.x + n.w / 2) * v.k; v.y = r.height / 2 - (n.y + n.h / 2) * v.k; }
  } else S.sel = { kind: 'diagram', id: did };
  render();
}
function renderTabs() {
  put(clear($('tabs')), S.open.map((did) => h('div', { class: 'tab' + (did === S.active ? ' on' : ''),
    onclick: () => { S.active = did; render(); } }, S.model.diagrams[did].name,
    h('span', { class: 'x', title: 'Close', onclick: (e) => { e.stopPropagation(); S.open = S.open.filter((x) => x !== did); if (S.active === did) S.active = S.open[0] || null; render(); } }, '×'))));
  const t = clear($('dtools'));
  if (!S.active) return;
  const lts = cfg().linkTypes;
  put(t, 'New links are:', selectIn(Object.keys(lts).filter((k) => !lts[k].retired).map((k) => [k, lts[k].label]), S.linkType, (v) => { S.linkType = v; }),
    h('button', { onclick: fit }, 'Fit'),
    h('button', { id: 'btnExport', onclick: (e) => { const r = e.currentTarget.getBoundingClientRect();
      menu({ preventDefault() {}, clientX: r.left, clientY: r.bottom + 2 }, [['SVG file', () => exportDiagram('svg')],
        ['PNG file', () => exportDiagram('png')], ['Copy image to clipboard', () => exportDiagram('clip')]]); } }, 'Export ▾'),
    h('label', { title: 'Grid size in diagram pixels (at 100% zoom)' }, 'Grid ',
      h('input', { id: 'gridSize', type: 'number', min: 2, max: 200, step: 1, value: String(gridNow().size), style: 'width:4.5em',
        onchange: (e) => { const v = parseInt(e.target.value, 10); if (v >= 2 && v <= 200) setGrid({ size: v }); else e.target.value = String(gridNow().size); } })),
    h('label', { title: 'Place, move and resize elements on the grid' },
      h('input', { id: 'gridSnap', type: 'checkbox', checked: gridNow().snap, onchange: (e) => setGrid({ snap: e.target.checked }) }), 'Snap'),
    h('label', { title: 'Size elements to show their whole text, always wider than tall (when created, edited or made narrower)' },
      h('input', { id: 'autoSize', type: 'checkbox', checked: autoOn(), onchange: (e) => {
        setAutoOn(e.target.checked);
        if (e.target.checked && selNodes().length) fitToText(selNodes(), true);    // switched on: fit what is selected
      } }), 'Auto size'),
    h('label', { title: 'Small overview of the whole diagram at the bottom right' },
      h('input', { id: 'miniOn', type: 'checkbox', checked: miniOn(), onchange: (e) => setMiniOn(e.target.checked) }), 'Overview'),
    lockOf(S.model.diagrams[S.active].folder) ? h('span', { class: 'lk', style: 'color:#b91c1c' }, '🔒 diagram locked by ' + lockOf(S.model.diagrams[S.active].folder).owner) : null);
}

// ---- diagrams: geometry ---------------------------------------------------
const FONT = 'system-ui, "Segoe UI", Roboto, sans-serif';
const mctx = document.createElement('canvas').getContext('2d');
function measure(text, size, bold) { mctx.font = (bold ? '600 ' : '') + size + 'px ' + FONT; return mctx.measureText(text).width; }
function wrap(text, maxW, maxLines) {
  const words = String(text).split(/\s+/), lines = [];
  let cur = '';
  for (const w of words) {
    const t = cur ? cur + ' ' + w : w;
    if (measure(t, 12) <= maxW || !cur) cur = t; else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) { lines.length = maxLines; lines[maxLines - 1] = lines[maxLines - 1].replace(/.{0,2}$/, '…'); }
  return lines.map((l) => { while (l.length > 2 && measure(l, 12) > maxW) l = l.slice(0, -2) + '…'; return l; });
}
const centerOf = (n) => [n.x + n.w / 2, n.y + n.h / 2];
/* Room the lock and notes badges take at the right end of the top line (badges: 0, 1 or 2). */
const badgeRoom = (badges) => (badges ? 16 + 22 * (badges - 1) : 0);
const badgesOf = (el) => (el.folder && lockOf(el.folder) ? 1 : 0) + (hasNotes(el) ? 1 : 0);
/* Room between the outline of a shape and its text: [left/right, top/bottom]. */
function insets(shape, w, h) {
  if (shape === 'ellipse') return [w * 0.15, h * 0.1];
  if (shape === 'hexagon') return [Math.min(16, w / 5) + 2, 0];
  return [8, 0];
}

// ---- auto size (ADR-030) -----------------------------------------------------
/* With Auto size on (per browser, on by default) a node gets the size that shows its whole topic, type, label
   and status without changing a font, and is always landscape: width / height > 1.2. The width of the node is
   a minimum; when the text would need a portrait box, the box gets wider instead. */
const RATIO = 1.2;
function autoOn() { try { return localStorage.getItem('sgauto') !== '0'; } catch (e) { return S.autoOff !== true; } }
function setAutoOn(on) { try { localStorage.setItem('sgauto', on ? '1' : '0'); } catch (e) { S.autoOff = !on; } }
/* The label the server will give an element of type stKey (ADR-023/026), to measure before it exists. */
const guessLabel = (stKey, eid) => { const p = stOf(stKey).labelPrefix; return p ? p + '-' + (eid || '00000000').replace(/-/g, '').slice(0, 8) : ''; };
/* The fitted {w, h} of element el (stereotype, topic, label, status) drawn at x, y, at least minW wide. */
function fitSize(el, x, y, minW) {
  const st = stOf(el.stereotype), g = gridNow(), step = g.snap ? g.size : 10;
  const up = (v, start) => Math.min(2000, g.snap ? Math.ceil((start + v) / g.size) * g.size - start : Math.ceil(v));
  const sta = statusOf(el.status || allowedStatuses(el.stereotype)[0]);
  const head = (st.icon ? 18 : 0) + measure('«' + st.label + '»', 10, true) + (el.label ? 12 + measure(el.label, 10, true) : 0);
  const pill = measure((sta.symbol ? sta.symbol + ' ' : '') + sta.label, 10, true) + 14;
  const word = Math.max(0, ...String(el.topic || '').split(/\s+/).map((t) => measure(t, 12)));
  let w = Math.max(60, minW || 0);
  for (let i = 0; i < 400; i++) {
    w = up(w, x);
    const ix = insets(st.shape, w, 0)[0], inner = w - 2 * ix, right = Math.max(ix, badgeRoom(badgesOf(el)));
    if (w - ix - right < head || inner < Math.max(pill, word)) { w += step; continue; }
    const lines = Math.max(1, wrap(el.topic || '', inner, 1000).length), base = 50 + 15 * lines;
    const h = up(Math.max(40, st.shape === 'ellipse' ? base / 0.8 : base), y);
    if (w / h > RATIO || w >= 2000) return { w, h };
    w += step;
  }
  return { w, h: up(40, y) };
}
/* diagram.layout operations that fit element eid (as `el` will be) on every diagram it is on, except where
   someone else's lock would refuse the whole change. */
function fitOps(eid, el, only) {
  const ops = [];
  Object.entries(S.model.diagrams).forEach(([did, d]) => {
    const n = d.nodes[eid];
    if (!n || (only && did !== only) || lockedOut(d.folder)) return;
    const f = fitSize(el, n.x, n.y, n.w);
    if (f.w !== n.w || f.h !== n.h) ops.push({ op: 'diagram.layout', args: { diagram: did, element: eid, w: f.w, h: f.h } });
  });
  return ops;
}
/* Fit to text: the selected nodes of the open diagram, whatever the switch says. */
function fitToText(ids, quiet) {
  const ops = [].concat(...ids.map((id) => fitOps(id, S.model.elements[id], S.active)));
  if (ops.length) post(ops); else if (!quiet) toast('Already fitted');
}
function clip(n, toward) {
  const [cx, cy] = centerOf(n), dx = toward[0] - cx, dy = toward[1] - cy;
  if (!dx && !dy) return [cx, cy];
  const t = Math.min(dx ? (n.w / 2) / Math.abs(dx) : Infinity, dy ? (n.h / 2) / Math.abs(dy) : Infinity);
  return [cx + dx * t, cy + dy * t];
}
function route(a, b, routing, pts) {
  if (routing === 'custom' && pts && pts.length) return [clip(a, pts[0])].concat(pts, [clip(b, pts[pts.length - 1])]);
  if (routing === 'auto') {
    const ay = a.y + a.h / 2, by = b.y + b.h / 2, ax = a.x + a.w / 2, bx = b.x + b.w / 2;
    const gx = b.x - (a.x + a.w), gx2 = a.x - (b.x + b.w), gy = b.y - (a.y + a.h), gy2 = a.y - (b.y + b.h);
    if (gx >= 24) { const mx = a.x + a.w + gx / 2; return [[a.x + a.w, ay], [mx, ay], [mx, by], [b.x, by]]; }
    if (gx2 >= 24) { const mx = b.x + b.w + gx2 / 2; return [[a.x, ay], [mx, ay], [mx, by], [b.x + b.w, by]]; }
    if (gy >= 24) { const my = a.y + a.h + gy / 2; return [[ax, a.y + a.h], [ax, my], [bx, my], [bx, b.y]]; }
    if (gy2 >= 24) { const my = b.y + b.h + gy2 / 2; return [[ax, a.y], [ax, my], [bx, my], [bx, b.y + b.h]]; }
  }
  return [clip(a, centerOf(b)), clip(b, centerOf(a))];
}
function linkPoints(d, lid) {
  const l = S.model.links[lid], o = d.links[lid] || {};
  return route(d.nodes[l.source], d.nodes[l.target], o.routing || ltOf(l.type).routing, o.points);
}
function visibleLinks(d) {
  return Object.keys(S.model.links).filter((lid) => { const l = S.model.links[lid]; return d.nodes[l.source] && d.nodes[l.target] && !(d.links[lid] || {}).hidden; });
}
/* Arrow head at `tip`, coming from `from`. Returns shapes and where the line should stop. */
function arrow(type, tip, from, color) {
  const dx = tip[0] - from[0], dy = tip[1] - from[1], len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
  const L = 12, W = 5, at = (f, s) => [tip[0] - ux * f + -uy * s, tip[1] - uy * f + ux * s];
  const pts = (a) => a.map((p) => p.join(',')).join(' ');
  if (type === 'open') return { els: [sv('polyline', { points: pts([at(L, W), tip, at(L, -W)]), fill: 'none', stroke: color, 'stroke-width': 1.5 })], trim: tip };
  if (type === 'triangle' || type === 'hollow-triangle')
    return { els: [sv('polygon', { points: pts([tip, at(L, W), at(L, -W)]), fill: type === 'triangle' ? color : '#ffffff', stroke: color, 'stroke-width': 1.5 })], trim: at(L, 0) };
  if (type === 'diamond' || type === 'hollow-diamond')
    return { els: [sv('polygon', { points: pts([tip, at(L * 0.75, W), at(L * 1.5, 0), at(L * 0.75, -W)]), fill: type === 'diamond' ? color : '#ffffff', stroke: color, 'stroke-width': 1.5 })], trim: at(L * 1.5, 0) };
  return { els: [], trim: tip };
}
function midpoint(pts) {
  let total = 0; const seg = [];
  for (let i = 1; i < pts.length; i++) { const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(l); total += l; }
  let half = total / 2;
  for (let i = 0; i < seg.length; i++) {
    if (half <= seg[i] || i === seg.length - 1) { const t = seg[i] ? half / seg[i] : 0; return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t]; }
    half -= seg[i];
  }
  return pts[0];
}

// ---- diagrams: drawing ----------------------------------------------------
const hasNotes = (el) => !!(el.notes && el.notes.trim());
const notesTip = (el) => 'Notes: ' + (el.notes.trim().length > 300 ? el.notes.trim().slice(0, 300) + '…' : el.notes.trim());
function drawNode(eid, n) {
  const el = S.model.elements[eid];
  if (!el) return null;
  const st = stOf(el.stereotype), sta = statusOf(el.status), w = n.w, hh = n.h;
  const chosen = renderDiagram.chosen || [], sel = chosen.includes(eid), lock = lockOf(el.folder);
  const g = sv('g', { transform: 'translate(' + n.x + ',' + n.y + ')', 'data-kind': 'node', 'data-id': eid, style: 'cursor:move' });
  const paint = { fill: st.fill, stroke: st.border, 'stroke-width': 1.5 };
  const [ix, iy] = insets(st.shape, w, hh);
  if (st.shape === 'ellipse') put(g, sv('ellipse', Object.assign({ cx: w / 2, cy: hh / 2, rx: w / 2, ry: hh / 2 }, paint)));
  else if (st.shape === 'hexagon') { const c = Math.min(16, w / 5);
    put(g, sv('polygon', Object.assign({ points: c + ',0 ' + (w - c) + ',0 ' + w + ',' + hh / 2 + ' ' + (w - c) + ',' + hh + ' ' + c + ',' + hh + ' 0,' + hh / 2 }, paint))); }
  else put(g, sv('rect', Object.assign({ width: w, height: hh, rx: st.shape === 'rounded' ? 12 : 0 }, paint)));
  put(g, sv('title', {}, elName(el) + ' — ' + sta.label + (lock ? ' — locked by ' + lock.owner + (lock.reason ? ': ' + lock.reason : '') : '')));
  if (st.icon) put(g, sv('text', { x: ix, y: iy + 16, 'font-size': 13, fill: st.border }, st.icon));
  put(g, sv('text', { x: ix + (st.icon ? 18 : 0), y: iy + 15, 'font-size': 10, 'font-weight': 600, fill: st.border }, '«' + st.label + '»'));
  if (el.label) put(g, sv('text', { x: w - Math.max(ix, badgeRoom(badgesOf(el))), y: iy + 15, 'font-size': 10, 'font-weight': 700, 'text-anchor': 'end', fill: '#111827' }, el.label));
  wrap(el.topic, w - 2 * ix, Math.max(1, Math.floor((hh - 2 * iy - 46) / 15))).forEach((t, i) =>
    put(g, sv('text', { x: w / 2, y: iy + 37 + i * 15, 'font-size': 12, 'text-anchor': 'middle', fill: '#111827' }, t)));
  const stText = (sta.symbol ? sta.symbol + ' ' : '') + sta.label, pw = measure(stText, 10, true) + 14;
  put(g, sv('rect', { x: (w - pw) / 2, y: hh - iy - 19, width: pw, height: 14, rx: 7, fill: sta.color }),
    sv('text', { x: w / 2, y: hh - iy - 8.5, 'font-size': 10, 'font-weight': 600, 'text-anchor': 'middle', fill: '#ffffff' }, stText));
  if (lock) put(g, sv('rect', { x: -3, y: -3, width: w + 6, height: hh + 6, fill: 'none', stroke: '#b91c1c', 'stroke-width': 1, 'stroke-dasharray': '5 3' }),
    sv('circle', { cx: w - 4, cy: 2, r: 9, fill: '#ffffff', stroke: '#b91c1c' }), sv('text', { x: w - 4, y: 6, 'font-size': 11, 'text-anchor': 'middle' }, '🔒'));
  if (hasNotes(el)) { const nx = lock ? w - 26 : w - 4;     // next to the lock when there is one
    put(g, sv('g', { 'data-badge': 'notes' }, sv('title', {}, notesTip(el)),
      sv('circle', { cx: nx, cy: 2, r: 9, fill: '#eff6ff', stroke: '#1d4ed8' }),
      sv('text', { x: nx, y: 6, 'font-size': 11, 'text-anchor': 'middle' }, '📜'))); }
  if (sel) put(g, sv('rect', { 'data-ui': 1, x: -5, y: -5, width: w + 10, height: hh + 10, fill: 'none', stroke: '#1d4ed8', 'stroke-width': 1.5,
    'stroke-dasharray': chosen.length > 1 && chosen[chosen.length - 1] !== eid ? '5 3' : null }));
  if (sel && chosen.length === 1) put(g,
    sv('rect', { 'data-ui': 1, 'data-kind': 'resize', 'data-id': eid, x: w - 1, y: hh - 1, width: 10, height: 10, fill: '#1d4ed8', style: 'cursor:nwse-resize' }),
    sv('circle', { 'data-ui': 1, 'data-kind': 'connect', 'data-id': eid, cx: w + 12, cy: hh / 2, r: 7, fill: '#1d4ed8', style: 'cursor:crosshair' },
      sv('title', {}, 'Drag to another element to create a link')));
  return g;
}
function drawLink(d, lid) {
  const l = S.model.links[lid], lt = ltOf(l.type), o = d.links[lid] || {}, pts = linkPoints(d, lid), n = pts.length;
  const sel = S.sel && S.sel.kind === 'link' && S.sel.id === lid;
  const g = sv('g', { 'data-kind': 'link', 'data-id': lid });
  const end = arrow(lt.targetArrow, pts[n - 1], pts[n - 2], lt.color), start = arrow(lt.sourceArrow, pts[0], pts[1], lt.color);
  const P = pts.slice(); P[0] = start.trim; P[n - 1] = end.trim;
  const path = 'M' + P.map((p) => p.map((v) => Math.round(v * 10) / 10).join(',')).join(' L');
  put(g, sv('path', { d: path, fill: 'none', stroke: lt.color, 'stroke-width': sel ? 3 : 1.5,
    'stroke-dasharray': lt.lineStyle === 'dashed' ? '7 4' : lt.lineStyle === 'dotted' ? '2 4' : null }),
    sv('path', { 'data-ui': 1, d: path, fill: 'none', stroke: 'transparent', 'stroke-width': 14, style: 'cursor:pointer' }), end.els, start.els);
  const text = l.label || (lt.showLabel ? lt.label : '');
  if (text) { const mp = midpoint(pts); put(g, sv('text', { x: mp[0], y: mp[1] - 4, 'font-size': 10, 'text-anchor': 'middle', fill: lt.color,
    stroke: '#ffffff', 'stroke-width': 3, 'paint-order': 'stroke' }, text)); }
  if (sel && (o.routing || lt.routing) === 'custom') (o.points || []).forEach((p, i) =>
    put(g, sv('circle', { 'data-ui': 1, 'data-kind': 'bend', 'data-id': lid, 'data-i': i, cx: p[0], cy: p[1], r: 6, fill: '#ffffff', stroke: '#1d4ed8', 'stroke-width': 2, style: 'cursor:move' })));
  return g;
}
function renderDiagram() {
  const svg = clear($('canvas')), d = S.active && S.model.diagrams[S.active];
  $('empty').textContent = !d ? 'Double-click a diagram in the tree to open it, or right-click a folder → New diagram.'
    : Object.keys(d.nodes).length ? '' : 'Empty diagram. Drag elements here from the tree, or right-click here to create one.';
  if (!d) return renderMini();
  const v = view(S.active);
  renderDiagram.chosen = selNodes();
  const gr = gridNow();
  svg.classList.toggle('snapping', gr.snap);           // the snap grid replaces the plain background dots
  if (gr.snap && gr.size * v.k >= 4) { const s = gr.size * v.k;   // not shown when the dots would be too dense
    put(svg, sv('defs', {}, sv('pattern', { id: 'grid', patternUnits: 'userSpaceOnUse', width: s, height: s, x: v.x, y: v.y },
      sv('circle', { cx: 0.75, cy: 0.75, r: 0.75, fill: '#9ca3af' }))),
      sv('rect', { width: '100%', height: '100%', fill: 'url(#grid)', 'pointer-events': 'none' })); }
  const vp = sv('g', { id: 'vp', transform: 'translate(' + v.x + ',' + v.y + ') scale(' + v.k + ')', 'font-family': FONT });
  visibleLinks(d).forEach((lid) => put(vp, drawLink(d, lid)));
  Object.keys(d.nodes).forEach((eid) => { const g = drawNode(eid, d.nodes[eid]); if (g) put(vp, g); });
  if (S.drag && S.drag.type === 'connect') { const c = centerOf(d.nodes[S.drag.from]);
    put(vp, sv('line', { x1: c[0], y1: c[1], x2: S.drag.to[0], y2: S.drag.to[1], stroke: '#1d4ed8', 'stroke-width': 2, 'stroke-dasharray': '4 3', 'pointer-events': 'none' })); }
  if (S.drag && S.drag.type === 'region' && S.drag.to) { const r = regionRect(S.drag);
    put(vp, sv('rect', { x: r[0], y: r[1], width: r[2] - r[0], height: r[3] - r[1], fill: 'rgba(29,78,216,.08)', stroke: '#1d4ed8', 'stroke-dasharray': '4 3', 'pointer-events': 'none' })); }
  put(svg, vp);
  renderMini();
}

// ---- diagrams: overview (ADR-028) ---------------------------------------------
const MINI = { w: 200, h: 140, pad: 6 };
function miniOn() { try { return localStorage.getItem('sgmini') !== '0'; } catch (e) { return S.miniOff !== true; } }
function setMiniOn(on) { try { localStorage.setItem('sgmini', on ? '1' : '0'); } catch (e) { S.miniOff = !on; } renderMini(); }
/* The part of the diagram in view, in diagram coordinates: [x, y, w, h]. */
function viewRect() {
  const r = $('canvas').getBoundingClientRect(), v = view(S.active);
  return [-v.x / v.k, -v.y / v.k, r.width / v.k, r.height / v.k];
}
/* Scale and offset from diagram coordinates to the overview: the whole diagram and the view fit in. */
function miniMap(d) {
  const vr = viewRect();
  let x1 = vr[0], y1 = vr[1], x2 = vr[0] + vr[2], y2 = vr[1] + vr[3];
  if (Object.keys(d.nodes).length) { const b = bounds(d); x1 = Math.min(x1, b.x); y1 = Math.min(y1, b.y); x2 = Math.max(x2, b.x + b.w); y2 = Math.max(y2, b.y + b.h); }
  const W = MINI.w - 2 * MINI.pad, Hh = MINI.h - 2 * MINI.pad, s = Math.min(W / ((x2 - x1) || 1), Hh / ((y2 - y1) || 1));
  return { s, ox: MINI.pad + (W - (x2 - x1) * s) / 2 - x1 * s, oy: MINI.pad + (Hh - (y2 - y1) * s) / 2 - y1 * s };
}
function renderMini() {
  const wrap = $('miniWrap'), d = S.active && S.model && S.model.diagrams[S.active];
  wrap.hidden = !d || !miniOn();
  if (wrap.hidden) return;
  const svg = clear($('mini')), mp = (S.miniDrag && S.miniDrag.map) || miniMap(d), vr = viewRect();
  const X = (x) => x * mp.s + mp.ox, Y = (y) => y * mp.s + mp.oy;
  visibleLinks(d).forEach((lid) => { const l = S.model.links[lid], a = centerOf(d.nodes[l.source]), b = centerOf(d.nodes[l.target]);
    put(svg, sv('line', { x1: X(a[0]), y1: Y(a[1]), x2: X(b[0]), y2: Y(b[1]), stroke: '#9ca3af', 'stroke-width': 1 })); });
  Object.keys(d.nodes).forEach((eid) => { const n = d.nodes[eid], el = S.model.elements[eid];
    if (!el) return;
    const st = stOf(el.stereotype);
    put(svg, sv('rect', { 'data-mini-node': eid, x: X(n.x), y: Y(n.y), width: Math.max(2, n.w * mp.s), height: Math.max(2, n.h * mp.s),
      fill: st.fill, stroke: st.border, 'stroke-width': 0.75 })); });
  put(svg, sv('rect', { id: 'miniView', x: X(vr[0]), y: Y(vr[1]), width: vr[2] * mp.s, height: vr[3] * mp.s,
    fill: 'rgba(29,78,216,.10)', stroke: '#1d4ed8', 'stroke-width': 1.5, style: 'cursor:move' }));
}
/* A click centres the view on that point; pressing on the box keeps the grip; then dragging moves the view.
   The scale is kept while dragging, so the box follows the pointer. */
function bindMini() {
  const svg = $('mini');
  const at = (e, mp) => { const r = svg.getBoundingClientRect(); return [(e.clientX - r.left - mp.ox) / mp.s, (e.clientY - r.top - mp.oy) / mp.s]; };
  const go = (pt) => { const v = view(S.active), g = S.miniDrag; v.x = -(pt[0] - g.off[0]) * v.k; v.y = -(pt[1] - g.off[1]) * v.k; renderDiagram(); };
  svg.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !S.active) return;
    e.preventDefault(); hideMenu();
    const mp = miniMap(S.model.diagrams[S.active]), pt = at(e, mp), vr = viewRect();
    const inside = pt[0] >= vr[0] && pt[0] <= vr[0] + vr[2] && pt[1] >= vr[1] && pt[1] <= vr[1] + vr[3];
    S.miniDrag = { map: mp, off: inside ? [pt[0] - vr[0], pt[1] - vr[1]] : [vr[2] / 2, vr[3] / 2] };
    svg.setPointerCapture(e.pointerId);
    go(pt);
  });
  svg.addEventListener('pointermove', (e) => { if (S.miniDrag && S.active) go(at(e, S.miniDrag.map)); });
  const end = () => { if (S.miniDrag) { S.miniDrag = null; renderMini(); } };
  svg.addEventListener('pointerup', end);
  svg.addEventListener('pointercancel', end);
  $('miniWrap').addEventListener('contextmenu', (e) => e.preventDefault());
  $('miniWrap').addEventListener('wheel', (e) => e.preventDefault(), { passive: false });
}

// ---- diagrams: interaction ------------------------------------------------
function toDiagram(e) {
  const r = $('canvas').getBoundingClientRect(), v = view(S.active);
  return [(e.clientX - r.left - v.x) / v.k, (e.clientY - r.top - v.y) / v.k];
}
function nodeAt(pt) {
  const nodes = S.model.diagrams[S.active].nodes;
  return Object.keys(nodes).reverse().find((id) => { const n = nodes[id]; return pt[0] >= n.x && pt[0] <= n.x + n.w && pt[1] >= n.y && pt[1] <= n.y + n.h; });
}
function hit(e) {
  // not e.target: a re-render between press and release replaces the element under the pointer
  const under = document.elementFromPoint(e.clientX, e.clientY);
  const t = under && $('canvas').contains(under) ? under.closest('[data-kind]') : null;
  return t ? { kind: t.getAttribute('data-kind'), id: t.getAttribute('data-id'), i: Number(t.getAttribute('data-i')) } : {};
}
function regionRect(g) {
  return [Math.min(g.start[0], g.to[0]), Math.min(g.start[1], g.to[1]), Math.max(g.start[0], g.to[0]), Math.max(g.start[1], g.to[1])];
}
/* Nodes touching or inside the rectangle, top to bottom then left to right (the last one is the reference). */
function nodesIn(r) {
  const nodes = S.model.diagrams[S.active].nodes;
  return Object.keys(nodes).filter((id) => { const n = nodes[id]; return n.x <= r[2] && n.x + n.w >= r[0] && n.y <= r[3] && n.y + n.h >= r[1]; })
    .sort((p, q) => (nodes[p].y - nodes[q].y) || (nodes[p].x - nodes[q].x));
}
/* Smallest zoom of Fit and the mouse wheel: 2%, so large diagrams fit; text is unreadable down there,
   which is fine for finding your way (use the overview or zoom in). */
const MIN_ZOOM = 0.02;
function fit() {
  const d = S.model.diagrams[S.active], ns = Object.values(d.nodes), r = $('canvas').getBoundingClientRect(), v = view(S.active);
  if (!ns.length) { v.x = 40; v.y = 40; v.k = 1; return renderDiagram(); }
  const b = bounds(d), zoom = (W, H) => Math.max(MIN_ZOOM, Math.min(1.5, (W - 60) / (b.w || 1), (H - 60) / (b.h || 1)));
  // with the overview shown, fit beside it or above it, whichever gives the larger picture
  let W = r.width, H = r.height;
  if (miniOn()) { const side = MINI.w + 20, below = MINI.h + 20;
    if (zoom(W - side, H) >= zoom(W, H - below)) W -= side; else H -= below; }
  v.k = zoom(W, H);
  v.x = (W - b.w * v.k) / 2 - b.x * v.k; v.y = (H - b.h * v.k) / 2 - b.y * v.k;
  renderDiagram();
}
function bounds(d) {
  let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
  const add = (x, y) => { x1 = Math.min(x1, x); y1 = Math.min(y1, y); x2 = Math.max(x2, x); y2 = Math.max(y2, y); };
  Object.values(d.nodes).forEach((n) => { add(n.x - 12, n.y - 12); add(n.x + n.w + 12, n.y + n.h + 12); });
  visibleLinks(d).forEach((lid) => linkPoints(d, lid).forEach((p) => { add(p[0] - 10, p[1] - 14); add(p[0] + 10, p[1] + 10); }));
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
}
function placeAtCenter(eid) {
  const r = $('canvas').getBoundingClientRect(), v = view(S.active);
  placeAt(eid, (r.width / 2 - v.x) / v.k - 95, (r.height / 2 - v.y) / v.k - 48);
}
function placeAt(eid, x, y) {
  x = snap(x); y = snap(y);
  op('diagram.place', Object.assign({ diagram: S.active, element: eid, x, y }, autoOn() ? fitSize(S.model.elements[eid], x, y, 190) : {}));
}
function bindCanvas() {
  const svg = $('canvas');
  svg.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !S.active) return;
    hideMenu();
    const t = hit(e), pt = toDiagram(e), d = S.model.diagrams[S.active];
    // own double-click detection: the browser's dblclick is unreliable here because
    // the first click re-draws the diagram
    const last = bindCanvas.last, now = Date.now();
    bindCanvas.last = { t: now, x: e.clientX, y: e.clientY };
    if (last && now - last.t < 400 && Math.abs(e.clientX - last.x) + Math.abs(e.clientY - last.y) < 6) { bindCanvas.last = null; return onDouble(e); }
    svg.setPointerCapture(e.pointerId);
    if (e.shiftKey) S.drag = { type: 'region', start: pt, to: null, node: t.kind === 'node' ? t.id : null, sx: e.clientX, sy: e.clientY };
    else if (t.kind === 'node' && (e.ctrlKey || e.metaKey)) toggleNode(t.id);
    else if (t.kind === 'connect') S.drag = { type: 'connect', from: t.id, to: pt };
    else if (t.kind === 'resize') S.drag = { type: 'resize', id: t.id, start: pt, orig: Object.assign({}, d.nodes[t.id]) };
    else if (t.kind === 'bend') S.drag = { type: 'bend', id: t.id, i: t.i };
    else if (t.kind === 'node') {
      // a selected node drags the whole selection; links whose both ends move take their bend points along
      const cur = selNodes(), ids = cur.includes(t.id) ? cur : [t.id], set = new Set(ids), orig = {}, bends = {};
      ids.forEach((id) => { orig[id] = Object.assign({}, d.nodes[id]); });
      Object.keys(d.links).forEach((lid) => { const l = S.model.links[lid], o = d.links[lid];
        if (l && o.points && o.points.length && set.has(l.source) && set.has(l.target)) bends[lid] = o.points.map((p) => p.slice()); });
      S.drag = { type: 'move', id: t.id, ids, start: pt, orig, bends };
      if (!cur.includes(t.id)) select('element', t.id);
    }
    else if (t.kind === 'link') select('link', t.id);
    else S.drag = { type: 'pan', sx: e.clientX, sy: e.clientY, orig: Object.assign({}, view(S.active)) };
  });
  svg.addEventListener('pointermove', (e) => {
    const g = S.drag;
    if (!g || !S.active) return;
    const pt = toDiagram(e), d = S.model.diagrams[S.active], v = view(S.active);
    if (g.type === 'pan') { const dx = e.clientX - g.sx, dy = e.clientY - g.sy; if (Math.abs(dx) + Math.abs(dy) > 3) g.moved = true; v.x = g.orig.x + dx; v.y = g.orig.y + dy; }
    else if (g.type === 'connect') g.to = pt;
    else if (g.type === 'bend') { d.links[g.id].points[g.i] = [Math.round(pt[0]), Math.round(pt[1])]; g.moved = true; }
    else if (g.type === 'region') g.to = pt;
    else {
      const dx = pt[0] - g.start[0], dy = pt[1] - g.start[1], n = d.nodes[g.id];
      if (Math.abs(dx) + Math.abs(dy) > 2) g.moved = true;
      if (g.type === 'move') {
        const o = g.orig[g.id], mx = snap(o.x + dx) - o.x, my = snap(o.y + dy) - o.y;
        g.ids.forEach((id) => { d.nodes[id].x = g.orig[id].x + mx; d.nodes[id].y = g.orig[id].y + my; });
        Object.keys(g.bends).forEach((lid) => { d.links[lid].points = g.bends[lid].map((p) => [p[0] + mx, p[1] + my]); });
      }
      else {
        // the side ends on the grid line, but never below the minimum size
        const gs = gridNow(), side = (lo, start, end) => { const s = snap(end) - start;
          return s >= lo ? s : gs.snap ? Math.ceil((start + lo) / gs.size) * gs.size - start : lo; };
        n.w = side(60, g.orig.x, g.orig.x + g.orig.w + dx); n.h = side(40, g.orig.y, g.orig.y + g.orig.h + dy);
        if (autoOn()) Object.assign(n, fitSize(S.model.elements[g.id], n.x, n.y, n.w));
      }
    }
    renderDiagram();
  });
  const finish = async (e) => {
    const g = S.drag;
    S.drag = null;
    if (!g || !S.active) return;
    const d = S.model.diagrams[S.active];
    if (g.type === 'pan') { if (!g.moved) select(null); return; }
    if (g.type === 'region') {
      // Shift+click (no drag) on a node: add or remove it, like Ctrl+click
      if (Math.abs(e.clientX - g.sx) + Math.abs(e.clientY - g.sy) < 4) { if (g.node) toggleNode(g.node); else renderDiagram(); return; }
      return selectNodes(nodesIn(regionRect(g)));
    }
    if (g.type === 'move' && !g.moved) { if (g.ids.length > 1) select('element', g.id); return; }
    if (g.type === 'connect') {
      const target = nodeAt(toDiagram(e));
      renderDiagram();
      if (target && target !== g.from && S.linkType) { const r = await op('link.create', { type: S.linkType, source: g.from, target }); if (r) select('link', r[0]); }
      return;
    }
    if (!g.moved) return;
    if (g.type === 'bend') return op('diagram.link', { diagram: S.active, link: g.id, points: d.links[g.id].points });
    const n = d.nodes[g.id];
    if (g.type === 'move') return post(g.ids.map((id) => ({ op: 'diagram.layout', args: { diagram: S.active, element: id, x: d.nodes[id].x, y: d.nodes[id].y } }))
      .concat(Object.keys(g.bends).map((lid) => ({ op: 'diagram.link', args: { diagram: S.active, link: lid, points: d.links[lid].points } }))));
    op('diagram.layout', { diagram: S.active, element: g.id, w: n.w, h: n.h });
  };
  svg.addEventListener('pointerup', finish);
  svg.addEventListener('pointercancel', () => { S.drag = null; load(); });
  function onDouble(e) {
    const t = hit(e), d = S.model.diagrams[S.active], pt = toDiagram(e).map(Math.round);
    if (t.kind === 'node') { const a = $('props').querySelector('textarea'); if (a) { a.focus(); a.select(); } }
    else if (t.kind === 'bend') { const pts = d.links[t.id].points.slice(); pts.splice(t.i, 1); op('diagram.link', { diagram: S.active, link: t.id, points: pts }); }
    else if (t.kind === 'link') {
      const o = d.links[t.id] || {}, custom = (o.routing || ltOf(S.model.links[t.id].type).routing) === 'custom';
      const pts = custom ? (o.points || []).slice() : [], geo = custom ? linkPoints(d, t.id) : null;
      let at = pts.length;
      if (geo) { let best = Infinity; for (let i = 0; i < geo.length - 1; i++) { const dist = segDist(pt, geo[i], geo[i + 1]); if (dist < best) { best = dist; at = i; } } }
      pts.splice(at, 0, pt);
      op('diagram.link', { diagram: S.active, link: t.id, routing: 'custom', points: pts });
    }
  }
  svg.addEventListener('wheel', (e) => {
    if (!S.active) return;
    e.preventDefault();
    const v = view(S.active), r = svg.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = Math.max(MIN_ZOOM, Math.min(3, v.k * (e.deltaY < 0 ? 1.1 : 1 / 1.1)));
    v.x = mx - (mx - v.x) * k / v.k; v.y = my - (my - v.y) * k / v.k; v.k = k;
    renderDiagram();
  }, { passive: false });
  svg.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    if (!S.active) return;
    const t = hit(e), d = S.model.diagrams[S.active], pt = toDiagram(e).map(Math.round);
    if (t.kind === 'node' || t.kind === 'resize' || t.kind === 'connect') {
      const cur = selNodes();
      if (cur.length > 1 && cur.includes(t.id)) return menu(e, [
        alignMenu(), ['Fit to text', () => fitToText(cur)], null,
        ['Remove ' + cur.length + ' elements from this diagram', () => post(cur.map((id) => ({ op: 'diagram.remove', args: { diagram: S.active, element: id } })))]]);
      select('element', t.id);
      menu(e, [['Fit to text', () => fitToText([t.id])], ['Find in explorer', () => findInExplorer('element', t.id)], ['Find in all diagrams', () => findInDiagrams(t.id)], ['Trace', () => showPanel({ kind: 'trace', id: t.id })], ['History', () => showPanel({ kind: 'history', id: t.id })], null,
        ['Remove from this diagram', () => op('diagram.remove', { diagram: S.active, element: t.id })], ['Delete from model…', () => deleteElement(t.id)]]);
    } else if (t.kind === 'link' || t.kind === 'bend') {
      select('link', t.id);
      menu(e, [['Hide on this diagram', () => op('diagram.link', { diagram: S.active, link: t.id, hidden: true })],
        ['Delete link from model…', () => confirmDialog('Delete this link from the model?', () => op('link.delete', { id: t.id }))]]);
    } else {
      menu(e, Object.keys(cfg().stereotypes).filter((k) => !cfg().stereotypes[k].retired).map((k) =>
        ['New ' + stOf(k).label + ' here…', () => newElement(k, d.folder, { diagram: S.active, x: pt[0], y: pt[1] })]));
    }
  });
  const wrapEl = $('canvasWrap');
  wrapEl.addEventListener('dragover', (e) => e.preventDefault());
  wrapEl.addEventListener('drop', (e) => {
    e.preventDefault();
    if (!S.active) return;
    let d; try { d = JSON.parse(e.dataTransfer.getData('text/plain')); } catch (x) { return; }
    const pt = toDiagram(e).map(Math.round);
    if (d.kind !== 'element') return;
    const nodes = S.model.diagrams[S.active].nodes, ids = (d.ids || [d.id]).filter((x) => S.model.elements[x] && !nodes[x]);
    if (!ids.length) return toast((d.ids || []).length > 1 ? 'All of them are already on this diagram' : 'Already on this diagram');
    // several: in rows of four from the drop point, as one change
    const ops = [], g = gridNow();
    let x0 = pt[0] - 95, x = x0, y = pt[1] - 48, rowH = 0;
    ids.forEach((id, i) => {
      if (i && i % 4 === 0) { x = x0; y += rowH + 40; rowH = 0; }
      const px = snap(x), py = snap(y), size = autoOn() ? fitSize(S.model.elements[id], px, py, 190) : { w: 190, h: 96 };
      ops.push({ op: 'diagram.place', args: Object.assign({ diagram: S.active, element: id, x: px, y: py }, size) });
      x = px + size.w + (g.snap ? g.size * 2 : 40); rowH = Math.max(rowH, size.h);
    });
    post(ops).then((r) => { if (r && (d.ids || []).length > ids.length) toast((d.ids.length - ids.length) + ' already on this diagram'); });
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { hideMenu(); if (!$('overlay').hidden) closeModal(); return; }
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || !$('overlay').hidden) return;
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'z') { e.preventDefault(); return undo(); }
    const num = { Digit1: 'start', Digit2: 'center', Digit3: 'end' }[e.code];
    if (num && e.shiftKey && (e.altKey !== (e.ctrlKey || e.metaKey))) { e.preventDefault(); return align(e.altKey ? 'y' : 'x', num); }
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'a' && S.active) {
      e.preventDefault(); return selectNodes(Object.keys(S.model.diagrams[S.active].nodes));
    }
    if (e.key === 'Delete' && selNodes().length)
      post(selNodes().map((id) => ({ op: 'diagram.remove', args: { diagram: S.active, element: id } })));
  });
  document.addEventListener('pointerdown', (e) => { if (!$('menu').contains(e.target)) hideMenu(); });
}
function segDist(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}
function exportDiagram(kind) {
  const d = S.model.diagrams[S.active];
  if (!Object.keys(d.nodes).length) return toast('Nothing to export');
  const b = bounds(d), vp = $('vp').cloneNode(true);
  vp.querySelectorAll('[data-ui]').forEach((e) => e.remove());
  vp.setAttribute('transform', 'translate(' + (-b.x) + ',' + (-b.y) + ')');
  const svg = sv('svg', { xmlns: SVGNS, width: Math.ceil(b.w), height: Math.ceil(b.h), viewBox: '0 0 ' + Math.ceil(b.w) + ' ' + Math.ceil(b.h) },
    sv('rect', { width: '100%', height: '100%', fill: '#ffffff' }), vp);
  const text = new XMLSerializer().serializeToString(svg), name = d.name.replace(/[^\w.-]+/g, '_');
  const save = (blob, ext) => { const a = h('a', { href: URL.createObjectURL(blob), download: name + '.' + ext }); document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); };
  const blob = new Blob([text], { type: 'image/svg+xml' });
  if (kind === 'svg') return save(blob, 'svg');
  // PNG at twice the size, less for a very large diagram (browsers refuse canvases over about 16000 pixels
  // a side or 64 million pixels in all); for the clipboard the promise goes straight into the ClipboardItem, which keeps
  // the click's permission to write while the image is drawn
  const png = new Promise((resolve, reject) => {
    const img = new Image(), url = URL.createObjectURL(blob);
    const k = Math.min(2, 16000 / Math.max(b.w, b.h), Math.sqrt(64e6 / (b.w * b.h)));
    img.onload = () => { const c = h('canvas', { width: Math.max(1, Math.round(b.w * k)), height: Math.max(1, Math.round(b.h * k)) }); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url); c.toBlob((p) => (p ? resolve(p) : reject(new Error('no image'))), 'image/png'); };
    img.onerror = () => reject(new Error('no image'));
    img.src = url;
  });
  if (kind === 'png') return png.then((p) => save(p, 'png'), () => toast('PNG export failed; use SVG', true));
  if (!navigator.clipboard || typeof ClipboardItem === 'undefined') return toast('This browser cannot copy images; use PNG file', true);
  navigator.clipboard.write([new ClipboardItem({ 'image/png': png })])
    .then(() => toast('Diagram copied to the clipboard as an image'), (e) => toast('Copy failed: ' + e.message + '. Use PNG file.', true));
}

// ---- bottom panel: search, trace, history, check ---------------------------
async function showPanel(p) {
  try {
    if (p.kind === 'trace') p.data = await get('/api/trace', { id: p.id });
    if (p.kind === 'history') p.data = await get('/api/history', { id: p.id });
    if (p.kind === 'search') p.data = await get('/api/search', p.params);
  } catch (e) { return toast(e.message, true); }
  S.panel = p; renderPanel();
}
const doSearch = (params) => showPanel({ kind: 'search', params });
const findInDiagrams = (id) => showPanel({ kind: 'search', params: { q: id } });
function elLink(s) { return h('span', {}, chip(s.stereotype), ' ', h('span', { class: 'link', onclick: () => { S.expanded.add(s.folder); select('element', s.id); } }, elName(s))); }
function renderPanel() {
  const el = $('panel'), p = S.panel;
  el.hidden = $('splitB').hidden = !p;
  if (!p) return;
  clear(el);
  const head = (t) => put(el, h('h3', {}, t, h('span', { class: 'x', onclick: () => { S.panel = null; renderPanel(); } }, '×')));
  if (p.kind === 'search') {
    head('Search results (' + p.data.length + ')');
    if (!p.data.length) put(el, h('p', { class: 'mute' }, 'Nothing found.'));
    p.data.forEach((r) => put(el, h('div', { class: 'res' }, elLink(r), h('span', { class: 'mute' }, '  ' + r.folderPath + ' · ' + statusOf(r.status).label + ' · ' + r.id.slice(0, 8)),
      h('div', {}, r.diagrams.length ? r.diagrams.map((d) => h('span', { class: 'dg', title: 'Double-click to open and show the element', 'data-diagram': d.id,
        ondblclick: () => openDiagram(d.id, r.id) }, '▦ ' + d.name)) : h('span', { class: 'mute' }, 'on no diagram')))));
  } else if (p.kind === 'trace') {
    head(['Traceability of ', elLink(p.data.element)]);
    const tree = (nodes, depth) => nodes.map((n) => [h('div', { style: 'padding-left:' + depth * 18 + 'px' }, h('span', { class: 'mute' }, ltOf(n.linkType).label + ' '), elLink(n)), tree(n.children, depth + 1)]);
    put(el, h('div', { class: 'cols' },
      h('div', {}, h('b', {}, 'Traces to →'), p.data.to.length ? tree(p.data.to, 0) : h('p', { class: 'mute' }, 'nothing')),
      h('div', {}, h('b', {}, '← Traced from (impact: what depends on it)'), p.data.from.length ? tree(p.data.from, 0) : h('p', { class: 'mute' }, 'nothing'))));
  } else if (p.kind === 'history') {
    head('History of ' + (S.model.elements[p.id] ? elName(S.model.elements[p.id]) : p.id));
    if (!p.data.length) put(el, h('p', { class: 'mute' }, 'No committed history yet. History comes from git commits.'));
    p.data.forEach((ev) => put(el, h('div', { class: 'res' }, h('b', {}, ev.changes.join('; ')), h('span', { class: 'mute' }, ' — by ' + ev.by + ', ' + ev.date.slice(0, 16).replace('T', ' ') + ' (' + ev.commit + ' ' + ev.subject + ')'))));
  } else {
    head('Check');
    if (S.integrity.length) put(el, h('div', { class: 'note' }, S.integrity[0], h('div', { class: 'btns' },
      h('button', { onclick: adopt }, 'Adopt this content under my name'), h('span', { class: 'mute' }, 'or restore the file: git checkout -- <file>'))));
    else put(el, h('p', {}, '✓ Change stamp is intact (last change: ' + S.model.stamp.op + ' by ' + S.model.stamp.user + ', ' + S.model.stamp.at + ').'));
    (S.model.conflicts || []).forEach((c, i) => {
      const show = (s) => s.present ? JSON.stringify(s.value).slice(0, 300) : '(deleted)';
      put(el, h('div', { class: 'res' }, h('b', {}, 'Conflict: ' + describePath(c.path)),
        h('div', {}, 'Mine: ', h('code', {}, show(c.ours))), h('div', {}, 'Theirs: ', h('code', {}, show(c.theirs))),
        h('div', { class: 'btns' }, h('button', { onclick: () => op('conflict.resolve', { index: i, choice: 'ours' }) }, 'Keep mine'),
          h('button', { onclick: () => op('conflict.resolve', { index: i, choice: 'theirs' }) }, 'Take theirs'))));
    });
    const rest = S.problems.filter((x) => x.code !== 'conflict');
    if (!rest.length) put(el, h('p', {}, '✓ No validation problems.'));
    rest.forEach((x) => put(el, h('div', { class: 'res' }, h('span', { style: 'color:' + (x.level === 'error' ? '#b91c1c' : '#b45309') }, x.level.toUpperCase() + ' '),
      S.model.elements[x.ref] ? h('span', { class: 'link', onclick: () => select('element', x.ref) }, x.message) : x.message)));
  }
}
function describePath(path) {
  const m = S.model, item = (m[path[0]] || {})[path[1]];
  const name = item ? (item.label || item.name || item.topic || '') : '';
  return path[0] + (name ? ' "' + name + '"' : '') + (path.length > 2 ? ' → ' + path.slice(2).join('/') : '');
}
async function adopt() {
  try { setState(await call('POST', '/api/adopt', {})); render(); toast('Adopted'); } catch (e) { toast(e.message, true); }
}

// ---- menus and dialogs ----------------------------------------------------
function menu(e, items) {
  e.preventDefault();
  const m = clear($('menu'));
  const entry = (it) => !it ? h('hr') : Array.isArray(it[1])
    ? h('div', { class: 'sub' }, h('span', {}, it[0]), h('span', { class: 'arr' }, '▸'), h('div', { class: 'submenu' }, it[1].map(entry)))
    : h('div', { onclick: (e) => { e.stopPropagation(); hideMenu(); it[1](); } }, it[0]);
  items.forEach((it) => put(m, entry(it)));
  m.hidden = false;
  m.classList.toggle('flip', Math.min(e.clientX, innerWidth - 200) + 560 > innerWidth);   // submenus open to the left
  m.style.left = Math.min(e.clientX, innerWidth - 200) + 'px';
  m.style.top = Math.min(e.clientY, innerHeight - m.offsetHeight - 8) + 'px';
}
function hideMenu() { $('menu').hidden = true; }
function modal(title, body, buttons) {
  const o = clear($('overlay'));
  put(o, h('div', { class: 'modal' }, h('h2', {}, title), body, h('div', { class: 'foot' }, buttons)));
  o.hidden = false;
  const first = o.querySelector('input,textarea,select');
  if (first) first.focus();
}
function closeModal() { $('overlay').hidden = true; clear($('overlay')); }
function formDialog(title, fields, onOk) {
  const inputs = {};
  const ok = async () => {
    const v = {};
    for (const f of fields) { v[f.key] = inputs[f.key].value.trim(); if (!v[f.key] && !f.optional) return inputs[f.key].focus(); }
    if (await onOk(v)) closeModal();
  };
  const body = h('div', {}, fields.map((f) => field(f.label, inputs[f.key] = h('input', { type: 'text', value: f.value || '', onkeydown: (e) => { if (e.key === 'Enter') ok(); } }))));
  modal(title, body, [h('button', { onclick: closeModal }, 'Cancel'), h('button', { class: 'primary', onclick: ok }, 'OK')]);
}
/* `back` re-opens the dialog the question was asked from, when there was one. */
function confirmDialog(text, fn, back) {
  modal('Please confirm', h('p', {}, text), [h('button', { onclick: () => { closeModal(); if (back) back(); } }, 'Cancel'),
    h('button', { class: 'primary', id: 'confirmYes', onclick: () => { closeModal(); fn(); } }, 'Yes')]);
}
function deleteFolder(id) {
  confirmDialog('Delete folder "' + S.model.folders[id].name + '" from the model? Only an empty folder can be deleted.', () => op('folder.delete', { id }));
}
async function deleteElement(id) {
  let u; try { u = await get('/api/usage', { id }); } catch (e) { return toast(e.message, true); }
  const body = h('div', {}, h('p', {}, 'This deletes "' + elName(u.element) + '" from the whole model, not just from a diagram.'),
    h('b', {}, 'Used on ' + u.diagrams.length + ' diagram(s):'), h('ul', {}, u.diagrams.map((d) => h('li', {}, d.name + ' (' + d.folderPath + ')'))),
    h('b', {}, u.links.length + ' link(s) will be deleted too:'), h('ul', {}, u.links.map((l) => h('li', {}, (l.direction === 'out' ? '→ ' : '← ') + ltOf(l.type).label + ' ' + elName(l.other)))));
  modal('Delete from model?', body, [h('button', { onclick: closeModal }, 'Cancel'),
    h('button', { class: 'primary', id: 'confirmDelete', onclick: () => { closeModal(); post([{ op: 'element.delete', args: { id } }], true); } }, 'Delete everywhere')]);
}
async function matrixDialog() {
  const sts = Object.keys(cfg().stereotypes), lts = cfg().linkTypes, out = h('div', { style: 'margin-top:10px;overflow:auto;max-height:55vh' });
  const rows = selectIn(sts.map((k) => [k, stOf(k).label]), sts.includes('ADR') ? 'ADR' : sts[0], run), cols = selectIn(sts.map((k) => [k, stOf(k).label]), sts.includes('REQ') ? 'REQ' : sts[0], run);
  const checks = Object.keys(lts).map((k) => h('label', {}, h('input', { type: 'checkbox', value: k, checked: lts[k].traceable !== false, onchange: run }), lts[k].label));
  async function run() {
    const types = checks.map((c) => c.firstChild).filter((c) => c.checked).map((c) => c.value);
    let mx; try { mx = await get('/api/matrix', { rows: rows.value, cols: cols.value, types: types.join(',') || 'none' }); } catch (e) { return toast(e.message, true); }
    put(clear(out), !mx.rows.length || !mx.cols.length ? h('p', { class: 'mute' }, 'No elements of these types.') : h('table', { class: 'mx' },
      h('tr', {}, h('th', {}), mx.cols.map((c) => h('th', { title: c.topic }, c.label || c.topic.slice(0, 14)))),
      mx.rows.map((r) => h('tr', {}, h('th', {}, elName(r)), mx.cols.map((c) => { const cell = ((mx.cells[r.id] || {})[c.id]) || [];
        return h('td', { title: cell.map((x) => ltOf(x.type).label).join(', ') }, cell.map((x) => (x.dir === 'out' ? '→' : '←')).join(' ')); })))));
  }
  modal('Traceability matrix', h('div', {}, h('div', { class: 'cols' }, field('Rows', rows), field('Columns', cols)), field('Link types', h('div', { class: 'checks' }, checks)),
    h('p', { class: 'mute' }, '→ row links to column, ← column links to row. Hover a cell for the link type.'), out), [h('button', { onclick: closeModal }, 'Close')]);
  run();
}
function usersDialog() {
  const m = S.model, admin = S.me.role === 'admin' && !readOnly();
  const name = h('input', { type: 'text', placeholder: 'name' }), key = h('input', { type: 'text', placeholder: 'ssh-ed25519 AAAA… (their public key)' });
  const role = selectIn([['user', 'user'], ['admin', 'admin']], 'user', () => {});
  const redo = async (p) => { if (await p) usersDialog(); };
  const body = h('div', {}, h('table', {}, h('tr', {}, h('th', {}, 'Name'), h('th', {}, 'Role'), h('th', {}, 'Keys'), h('th', {})),
    Object.keys(m.users).sort().map((n) => h('tr', {}, h('td', {}, n), h('td', {}, admin ? selectIn([['user', 'user'], ['admin', 'admin']], m.users[n].role, (v) => redo(op('user.update', { name: n, role: v }))) : m.users[n].role),
      h('td', {}, m.users[n].keys.map((k) => h('div', { title: k, class: 'mute' }, k.split(' ')[0] + ' …' + k.slice(-10)))),
      h('td', {}, admin && n !== S.me.user ? h('button', { class: 'danger', onclick: () => confirmDialog('Remove user "' + n + '" from the model?', async () => { await op('user.remove', { name: n }); usersDialog(); }, usersDialog) }, 'Remove') : null)))),
    admin ? h('div', { style: 'margin-top:12px' }, h('b', {}, 'Add a user'), h('div', { class: 'cols', style: 'gap:6px;margin-top:4px' }, name, role), h('div', { style: 'margin-top:4px' }, key),
      h('p', { class: 'mute' }, 'Users identify themselves with the SSH key they already use for git (~/.ssh/id_ed25519.pub). No passwords.'))
      : h('p', { class: 'mute' }, 'Only an administrator can change users.'));
  modal('Users', body, [h('button', { onclick: closeModal }, 'Close'),
    admin ? h('button', { class: 'primary', onclick: () => redo(op('user.add', { name: name.value.trim(), key: key.value.trim(), role: role.value })) }, 'Add user') : null]);
}

// ---- configuration dialog -------------------------------------------------
const ARROWS = ['none', 'open', 'triangle', 'hollow-triangle', 'diamond', 'hollow-diamond'];
const SCHEMA = {
  stereotypes: [['label', 'Label', 'text'], ['description', 'Description: what this means in this project, for people and agents', 'textarea'], ['fill', 'Fill colour', 'color'], ['border', 'Border colour', 'color'], ['icon', 'Symbol (one character)', 'text'],
    ['shape', 'Shape', 'select', ['rect', 'rounded', 'hexagon', 'ellipse']], ['labelPrefix', 'Label prefix (REQ gives REQ-3d6e7863…)', 'text'],
    ['statuses', 'Allowed statuses (none ticked = all)', 'keys', 'statuses'], ['fields', 'Custom fields', 'fields'], ['retired', 'Retired: keep existing items, allow no new ones', 'bool']],
  statuses: [['label', 'Label', 'text'], ['description', 'Description: what this means in this project, for people and agents', 'textarea'], ['color', 'Colour', 'color'], ['symbol', 'Symbol', 'text'], ['order', 'Order', 'number'], ['retired', 'Retired: keep existing items, allow no new ones', 'bool']],
  linkTypes: [['label', 'Label', 'text'], ['description', 'Description: what this means in this project, for people and agents', 'textarea'], ['lineStyle', 'Line style', 'select', ['solid', 'dashed', 'dotted']], ['color', 'Colour', 'color'],
    ['sourceArrow', 'Arrow at the start', 'select', ARROWS], ['targetArrow', 'Arrow at the end', 'select', ARROWS], ['showLabel', 'Show the type name on the link', 'bool'],
    ['routing', 'Default routing', 'select', ['straight', 'auto', 'custom']], ['traceable', 'Counts for traceability', 'bool'],
    ['sources', 'May start at (none ticked = any)', 'keys', 'stereotypes'], ['targets', 'May end at (none ticked = any)', 'keys', 'stereotypes'],
    ['retired', 'Retired: keep existing items, allow no new ones', 'bool']],
  coverageRules: [['description', 'Rule in words', 'text'], ['stereotype', 'Every element of type', 'pick', 'stereotypes'], ['statuses', 'in status (none ticked = any)', 'keys', 'statuses'],
    ['linkType', 'must have a link of type', 'pick', 'linkTypes'], ['direction', 'direction (incoming = the other element points to it)', 'select', ['incoming', 'outgoing']],
    ['other', 'with an element of type', 'pickAny', 'stereotypes']],
};
const KIND_NAMES = { stereotypes: 'Stereotypes', statuses: 'Statuses', linkTypes: 'Link types', coverageRules: 'Coverage rules' };
function blank(kind) {
  const c = cfg();
  return { stereotypes: { label: 'New type', description: '', fill: '#e0e7ff', border: '#3730a3', icon: '★', shape: 'rect', labelPrefix: '', statuses: null, fields: {}, retired: false },
    statuses: { label: 'New status', description: '', color: '#0f766e', symbol: '•', retired: false },
    linkTypes: { label: 'new link', description: '', lineStyle: 'solid', color: '#374151', sourceArrow: 'none', targetArrow: 'open', showLabel: true, routing: 'auto', traceable: true, sources: null, targets: null, retired: false },
    coverageRules: { description: '', stereotype: Object.keys(c.stereotypes)[0], statuses: null, linkType: Object.keys(c.linkTypes)[0], direction: 'incoming', other: null } }[kind];
}
function configDialog(kind, key) {
  const coll = cfg()[kind], isNew = key === '+';
  if (!isNew && !coll[key]) key = Object.keys(coll)[0];
  const val = JSON.parse(JSON.stringify(isNew ? blank(kind) : (coll[key] || null)));
  const dis = readOnly();
  const tabs = h('div', { class: 'btns' }, Object.keys(SCHEMA).map((k) => h('button', { class: k === kind ? 'primary' : '', onclick: () => configDialog(k) }, KIND_NAMES[k])));
  const list = h('div', { class: 'list' }, Object.keys(coll).map((k) => h('div', { class: 'row' + (k === key ? ' sel' : ''), title: coll[k].description || k, onclick: () => configDialog(kind, k) },
    h('span', { class: 't' }, coll[k].label || coll[k].description || k), coll[k].retired ? h('span', { class: 'lk mute' }, 'retired') : null)),
    h('div', { class: 'row mute' + (isNew ? ' sel' : ''), onclick: () => configDialog(kind, '+') }, '+ new'));
  const form = h('div', { class: 'form' });
  let fieldRows = null;
  if (val) SCHEMA[kind].forEach(([k, label, type, extra]) => {
    if (type === 'textarea') put(form, field(label, h('textarea', { rows: 3, value: val[k] == null ? '' : val[k], disabled: dis, oninput: (e) => { val[k] = e.target.value; } })));
    else if (type === 'text' || type === 'number') put(form, field(label, h('input', { type, value: val[k] == null ? '' : val[k], disabled: dis, oninput: (e) => { val[k] = type === 'number' ? Number(e.target.value) : e.target.value; } })));
    else if (type === 'color') put(form, field(label, h('input', { type: 'color', value: val[k] || '#888888', disabled: dis, style: 'width:60px;height:26px;padding:1px', oninput: (e) => { val[k] = e.target.value; } })));
    else if (type === 'bool') put(form, field(label, h('input', { type: 'checkbox', checked: k === 'traceable' ? val[k] !== false : !!val[k], disabled: dis, onchange: (e) => { val[k] = e.target.checked; } }), true));
    else if (type === 'select') put(form, field(label, selectIn(extra.map((x) => [x, x]), val[k], (v) => { val[k] = v; }, dis)));
    else if (type === 'pick' || type === 'pickAny') put(form, field(label, selectIn((type === 'pickAny' ? [['', 'any']] : []).concat(Object.keys(cfg()[extra]).map((x) => [x, cfg()[extra][x].label])), val[k] || '', (v) => { val[k] = v || null; }, dis)));
    else if (type === 'keys') put(form, field(label, h('div', { class: 'checks' }, Object.keys(cfg()[extra]).map((x) => h('label', {}, h('input', { type: 'checkbox', disabled: dis, checked: (val[k] || []).includes(x),
      onchange: (e) => { const set = new Set(val[k] || []); e.target.checked ? set.add(x) : set.delete(x); val[k] = set.size ? Array.from(set) : null; } }), cfg()[extra][x].label)))));
    else if (type === 'fields') {
      fieldRows = Object.keys(val.fields || {}).map((fk) => Object.assign({ key: fk, existing: true }, val.fields[fk]));
      const box = h('div', {});
      const draw = () => { put(clear(box), h('table', {}, h('tr', {}, h('th', {}, 'Key'), h('th', {}, 'Label'), h('th', {}, 'Type'), h('th', {}, 'Options (for enum, comma separated)'), h('th', {})),
        fieldRows.map((r, i) => h('tr', {}, h('td', {}, h('input', { type: 'text', value: r.key, disabled: r.existing || dis, style: 'width:90px', oninput: (e) => { r.key = e.target.value.trim(); } })),
          h('td', {}, h('input', { type: 'text', value: r.label || '', disabled: dis, style: 'width:110px', oninput: (e) => { r.label = e.target.value; } })),
          h('td', {}, selectIn(['string', 'text', 'number', 'boolean', 'enum', 'date'].map((x) => [x, x]), r.type, (v) => { r.type = v; }, dis)),
          h('td', {}, h('input', { type: 'text', value: (r.options || []).join(', '), disabled: dis, oninput: (e) => { r.options = e.target.value.split(',').map((x) => x.trim()).filter(Boolean); } })),
          h('td', {}, h('button', { disabled: dis, onclick: () => { fieldRows.splice(i, 1); draw(); } }, '×'))))),
        h('button', { disabled: dis, style: 'margin-top:4px', onclick: () => { fieldRows.push({ key: '', label: '', type: 'string' }); draw(); } }, '+ field')); };
      draw();
      put(form, field(label, box));
    }
  });
  else put(form, h('p', { class: 'mute' }, kind === 'coverageRules' ? 'No coverage rules. Example: "every approved REQ must be implemented by an ADR". Violations show up under Check.' : 'Nothing here yet.'));
  const save = async () => {
    if (fieldRows) { val.fields = {}; fieldRows.forEach((r) => { if (r.key) { val.fields[r.key] = { label: r.label || r.key, type: r.type }; if (r.type === 'enum') val.fields[r.key].options = r.options || []; } }); }
    const r = await op('config.put', isNew ? { kind, value: val } : { kind, key, value: val });
    if (r) { toast('Saved'); configDialog(kind, isNew ? r[0] : key); }
  };
  const del = () => confirmDialog('Delete "' + (coll[key].label || coll[key].description || key) + '" from the configuration?',
    async () => configDialog(kind, (await op('config.delete', { kind, key })) ? undefined : key), () => configDialog(kind, key));
  modal('Configuration', h('div', {}, tabs, h('div', { class: 'cfg' }, list, form)), [
    val && !isNew ? h('button', { class: 'danger', disabled: dis, onclick: del, title: 'Only possible when nothing uses it; otherwise tick Retired' }, 'Delete') : null,
    h('button', { onclick: closeModal }, 'Close'), val ? h('button', { class: 'primary', id: 'cfgSave', disabled: dis, onclick: save }, isNew ? 'Create' : 'Save') : null]);
}

// ---- resizable panes ------------------------------------------------------
/* The snap grid (ADR-027): view state kept per browser, the same default for everyone. */
const GRID_DEFAULT = { size: 20, snap: true };
function grid() {
  let g = null;
  try { g = JSON.parse(localStorage.getItem('sggrid')); } catch (e) { /* no storage: the default */ }
  g = Object.assign({}, GRID_DEFAULT, g || {});
  if (!Number.isInteger(g.size) || g.size < 2 || g.size > 200) g.size = GRID_DEFAULT.size;
  return g;
}
function setGrid(change) {
  const g = Object.assign(gridNow(), change);
  try { localStorage.setItem('sggrid', JSON.stringify(g)); } catch (e) { S.gridOnce = g; }
  renderDiagram();
}
/* A coordinate on the grid when snapping is on. */
const gridNow = () => S.gridOnce || grid();
function snap(v) { const g = gridNow(); return g.snap ? Math.round(v / g.size) * g.size : Math.round(v); }
/* The sizes of the side panes and the bottom panel are kept per browser (localStorage), not in the model. */
const PANES = { splitL: ['tree', 'width', 1], splitR: ['props', 'width', -1], splitB: ['panel', 'height', -1] };
function paneSizes() { try { return JSON.parse(localStorage.getItem('sgpanes')) || {}; } catch (e) { return {}; } }
/* px null = back to the default size. `keep` remembers it for the next visit. */
function setPane(key, px, keep) {
  const id = PANES[key][0], dim = PANES[key][1], el = $(id);
  if (px == null) el.style[dim] = '';
  else {
    const max = dim === 'width' ? $('main').clientWidth - $(id === 'tree' ? 'props' : 'tree').offsetWidth - 210 : $('center').clientHeight - 120;
    el.style[dim] = Math.round(Math.max(dim === 'width' ? 120 : 60, Math.min(max, px))) + 'px';
  }
  if (!keep) return;
  const all = paneSizes();
  if (px == null) delete all[key]; else all[key] = parseInt(el.style[dim], 10);
  try { localStorage.setItem('sgpanes', JSON.stringify(all)); } catch (e) { /* storage refused: the size lasts for this visit */ }
}
function bindSplitters() {
  const saved = paneSizes();
  Object.keys(PANES).forEach((key) => {
    const id = PANES[key][0], dim = PANES[key][1], sign = PANES[key][2], bar = $(key);
    if (saved[key] > 0) setPane(key, saved[key]);
    bar.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      bar.setPointerCapture(e.pointerId); bar.classList.add('on');
      const at = (ev) => (dim === 'width' ? ev.clientX : ev.clientY), from = at(e), size = $(id).getBoundingClientRect()[dim];
      const move = (ev) => setPane(key, size + sign * (at(ev) - from));
      const stop = () => {
        bar.removeEventListener('pointermove', move); bar.removeEventListener('pointerup', stop); bar.removeEventListener('pointercancel', stop);
        bar.classList.remove('on');
        if ($(id).style[dim]) setPane(key, parseInt($(id).style[dim], 10), true);
      };
      bar.addEventListener('pointermove', move); bar.addEventListener('pointerup', stop); bar.addEventListener('pointercancel', stop);
    });
    bar.addEventListener('dblclick', () => setPane(key, null, true));
  });
}

// ---- start ----------------------------------------------------------------
async function poll() {
  if (S.drag || document.hidden) return;
  try {
    const r = await get('/api/head');
    if (r.head !== S.head || S.loadError) { const active = document.activeElement; if (active && /^(INPUT|TEXTAREA)$/.test(active.tagName) && !S.loadError) return; await load(); toast('The model file changed — reloaded'); }
  } catch (e) { S.loadError = e.message; if (S.model) renderBar(); else render(); }
}
function boot() {
  const m = location.hash.match(/t=([^&]+)/);
  try {
    if (m) { sessionStorage.setItem('sgtoken', m[1]); history.replaceState(null, '', location.pathname); }
    S.token = sessionStorage.getItem('sgtoken');
  } catch (e) { S.token = m && m[1]; }
  if (!S.token) { put($('banner'), h('div', { class: 'err' }, 'Open the tool with the link printed by "serve" (it carries a one-time access token).')); return; }
  bindCanvas(); bindMini(); bindSplitters();
  load().then(() => { if (S.model) { Object.keys(S.model.folders).forEach((f) => { if (S.model.folders[f].parent == null) S.expanded.add(f); }); renderTree(); } });
  setInterval(poll, 3000);
}
boot();
