import test from 'node:test';
import assert from 'node:assert/strict';
import {reconcileMessages, hasMessageSelection} from '../web/chat.mjs';
import {chatBox} from './helpers/chat_dom.mjs';
const row=(id,text,state='done')=>({id,role:'assistant',state,content:{text}});
test('keyed chat preserves unchanged descendants across polls, append, prepend and status changes',()=>{
 const box=chatBox();const rows=[row(2,'Text & **markup**'),row(3,'Waiting','queued')];
 assert.equal(reconcileMessages(box,rows,'UTC'),true);
 const original=box.children[0], text=original.textNode, waiting=box.children[1];
 // A browser serialization difference must not be used as the comparison source.
 original.html='browser normalized HTML';
 assert.equal(reconcileMessages(box,rows,'UTC'),false);
 reconcileMessages(box,[row(1,'Older'),...rows,row(4,'New')],'UTC');
 assert.equal(box.children[1],original);assert.equal(original.textNode,text);
 reconcileMessages(box,[row(1,'Older'),rows[0],row(3,'Failed','failed'),row(4,'New')],'UTC');
 assert.equal(box.children[1],original);assert.notEqual(box.children[2],waiting);
 assert.match(box.children[2].html,/Błąd odpowiedzi/);
 reconcileMessages(box,[],'UTC');assert.equal(box.children.length,1);assert.match(box.innerHTML,/Zacznij/);
 reconcileMessages(box,rows,'UTC');assert.equal(box.children.length,2);
 box.replaceChildren();reconcileMessages(box,rows,'UTC');assert.equal(box.children.length,2);
});
test('selection crossing the message container blocks scrolling even with endpoints outside it',()=>{
 const box=chatBox();box.ownerDocument.getSelection=()=>({isCollapsed:false,rangeCount:1,getRangeAt:()=>({intersectsNode:n=>n===box})});
 assert.equal(hasMessageSelection(box),true);
 box.ownerDocument.getSelection=()=>({isCollapsed:true});assert.equal(hasMessageSelection(box),false);
});
