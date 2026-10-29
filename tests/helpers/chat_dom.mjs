// Small DOM stand-in for reconciliation operations; native selection is tested in Chromium.
export class Element {
  constructor(html = '', document = null) {
    this.html = html; this.ownerDocument = document; this.children = []; this.parentNode = null;
    this.dataset = {messageId: /data-message-id="([^"]+)"/.exec(html)?.[1]};
    this.textNode = {}; // identity marker for unchanged descendants
  }
  get firstElementChild() { return this.children[0] || null; }
  get nextElementSibling() { return this.parentNode?.children[this.parentNode.children.indexOf(this)+1] || null; }
  get innerHTML() { return this.children.length ? this.children.map(n=>n.html).join('') : this.html; }
  set innerHTML(html) { this.html = html; }
  insertBefore(node, cursor) {
    node.remove();
    const index = cursor ? this.children.indexOf(cursor) : this.children.length;
    if (index < 0) throw Error('Invalid insertion cursor');
    this.children.splice(index, 0, node); node.parentNode = this;
  }
  replaceWith(node) { const parent=this.parentNode; parent.insertBefore(node,this); this.remove(); }
  remove() { if(this.parentNode) {const p=this.parentNode; p.children.splice(p.children.indexOf(this),1); this.parentNode=null;} }
  replaceChildren() { for(const n of [...this.children])n.remove(); this.html=''; }
  getBoundingClientRect() { return {top:0,bottom:10}; }
  scrollTo() {}
  addEventListener() {}
  setAttribute() {}
}
export function chatBox() {
  const doc = {getSelection:()=>null, addEventListener(){}, defaultView:{addEventListener(){}}, createElement(){
    return {set innerHTML(html){this.content={firstElementChild:new Element(html,doc)};}};
  }};
  return new Element('',doc);
}
