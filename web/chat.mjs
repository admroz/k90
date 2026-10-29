import { renderTimeline } from './render.mjs';

const rendered = new WeakMap();

// Compare renderer output with its previous output, never DOM serialization.
// Unchanged rows keep their text descendants (and the browser's native selection).
export function reconcileMessages(box, rows, timezone) {
  const previous = rendered.get(box) || new Map();
  const next = new Map();
  let cursor = box.firstElementChild;
  let changed = false;
  const entries = rows.length ? rows.map(row => [String(row.id), renderTimeline([row], timezone)])
    : [['empty', renderTimeline([], timezone)]];
  for (const [id, html] of entries) {
    const old = previous.get(id);
    let node = old?.node;
    if (!node || node.parentNode !== box || old.html !== html) {
      const template = box.ownerDocument.createElement('template');
      template.innerHTML = html;
      const replacement = template.content.firstElementChild;
      if (node?.parentNode === box) {
        if (cursor === node) cursor = replacement;
        node.replaceWith(replacement);
      }
      node = replacement;
      changed = true;
    }
    if (node !== cursor) {
      box.insertBefore(node, cursor);
      changed = true;
    }
    cursor = node.nextElementSibling;
    next.set(id, {html, node});
  }
  while (cursor) {
    const following = cursor.nextElementSibling;
    cursor.remove();
    cursor = following;
    changed = true;
  }
  rendered.set(box, next);
  return changed;
}

export function trackSelectionGesture(box) {
  let active = false;
  box.addEventListener('pointerdown', () => { active = true; });
  const end = () => { active = false; };
  box.ownerDocument.addEventListener('pointerup', end);
  box.ownerDocument.addEventListener('pointercancel', end);
  box.ownerDocument.defaultView.addEventListener('blur', end);
  return () => active;
}

export function hasMessageSelection(box) {
  const selection = box.ownerDocument.getSelection();
  if (!selection || selection.isCollapsed) return false;
  for (let i = 0; i < selection.rangeCount; i++) {
    if (selection.getRangeAt(i).intersectsNode(box)) return true;
  }
  return false;
}
