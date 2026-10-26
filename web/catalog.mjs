import { escapeHTML as e } from './render.mjs';
import { createRequestId } from './request.mjs';

export function catalogCard(p) {
  const verified = p.status === 'confirmed';
  return `<article class="panel"><h3>${e(p.name)} · ${e(p.brand || '')}</h3>
    <p>${e(p.basis)}: ${e(p.kcal)} kcal / B ${e(p.protein)} g / W ${e(p.carbs)} g / T ${e(p.fat)} g</p>
    <p>${e(p.barcode || 'Bez kodu')} · ${e(p.provenance)} · ${verified ? 'Potwierdzony' : 'Szkic do sprawdzenia'} · wersja ${e(p.version)}</p>
    <button class="secondary" data-edit="${p.id}">Popraw</button>
    ${p.source_event_id ? `<button class="secondary" data-label="${p.id}">Pokaż etykietę</button>` : ''}
    ${verified ? `<button class="primary" data-portion="${p.id}">Zapisz porcję</button>` : `<button class="primary" data-confirm="${p.id}">Sprawdziłem wartości — zatwierdź wersję ${e(p.version)}</button>`}</article>`;
}

export function setupCatalog(api, root, report) {
  let products = new Map(), selected = null, pending = null, draftRequest = null;
  const list = root.querySelector('#catalog-list');
  const editor = root.querySelector('#catalog-editor');
  const portion = root.querySelector('#catalog-portion');
  const field = name => editor.elements.namedItem(name);
  async function load() {
    const rows = await api(`/api/catalog?query=${encodeURIComponent(root.querySelector('#catalog-search').value)}`);
    products = new Map(rows.map(p => [String(p.id), p]));
    list.innerHTML = rows.map(catalogCard).join('') || '<p>Brak produktów. Dodaj własną etykietę w rozmowie lub wpisz wartości ręcznie.</p>';
  }
  function edit(p = null) {
    selected = p;
    draftRequest = null;
    editor.reset();
    for (const key of ['name','brand','barcode','kcal','protein','carbs','fat','basis']) field(key).value = p?.[key] ?? (key === 'basis' ? '100g' : '');
    editor.hidden = false;
    portion.hidden = true;
    field('name').focus();
  }
  root.querySelector('#catalog-new').onclick = () => edit();
  root.querySelector('#catalog-search-form').onsubmit = event => { event.preventDefault(); load().catch(report); };
  editor.onsubmit = async event => {
    event.preventDefault();
    const button = editor.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const product = Object.fromEntries(['name','brand','barcode','basis','kcal','protein','carbs','fat'].map(k => [k,field(k).value]));
      product.barcode ||= null;
      product.provenance = 'manual';
      if (!selected) {
        const signature = JSON.stringify(product);
        if (draftRequest?.signature !== signature) draftRequest = {signature, id:createRequestId()};
        product.request_id = draftRequest.id;
      }
      await api(selected ? `/api/catalog/${selected.id}` : '/api/catalog', {
        method:selected ? 'PUT':'POST', body:JSON.stringify(selected ? {version:selected.version,product}:product)});
      editor.hidden = true;
      await load();
    } catch (err) { report(err); } finally { button.disabled = false; }
  };
  list.onclick = async event => {
    const button = event.target.closest('button');
    if (!button) return;
    const action = ['edit','confirm','portion','label'].find(k => button.dataset[k]);
    const p = products.get(button.dataset[action]);
    if (!p) return;
    button.disabled = true;
    try {
      if (action === 'edit') edit(p);
      if (action === 'confirm') {
        await api(`/api/catalog/${p.id}/confirm`, {method:'POST',body:JSON.stringify({version:p.version})});
        await load();
      }
      if (action === 'portion') {
        selected = p; pending = null; editor.hidden = true; portion.hidden = false;
        root.querySelector('#catalog-portion-name').textContent = `${p.name} · wersja ${p.version} · ilość w ${p.basis === '100g' ? 'g':'ml'}`;
        root.querySelector('#catalog-quantity').value = '';
      }
      if (action === 'label') {
        const result = await api(`/api/catalog/${p.id}/label`);
        root.querySelector('#catalog-label').src = result.image;
        root.querySelector('#catalog-label').hidden = false;
      }
    } catch (err) { report(err); } finally { button.disabled = false; }
  };
  portion.onsubmit = async event => {
    event.preventDefault();
    const button = root.querySelector('#catalog-log'); button.disabled = true;
    try {
      const quantity = root.querySelector('#catalog-quantity').value;
      const signature = JSON.stringify([selected.id,selected.version,quantity]);
      if (pending?.signature !== signature) pending = {signature,id:createRequestId()};
      const result = await api(`/api/catalog/${selected.id}/portion`, {method:'POST',body:JSON.stringify({version:selected.version,quantity,unit:selected.basis==='100g'?'g':'ml',request_id:pending.id})});
      root.querySelector('#catalog-status').textContent = `Zapisano porcję: ${result.nutrition.kcal} kcal`;
      portion.hidden = true;
    } catch (err) { report(err); } finally { button.disabled = false; }
  };
  root.querySelector('#catalog-lookup').onclick = async event => {
    const button = event.target; button.disabled = true;
    try {
      const result = await api('/api/catalog/lookup', {method:'POST',body:JSON.stringify({barcode:root.querySelector('#catalog-barcode').value})});
      root.querySelector('#catalog-external').textContent = result.provenance === 'openfoodfacts'
        ? `NIEPOTWIERDZONE — ${result.name}, ${result.brand}, ${result.basis}: ${result.kcal} kcal / B ${result.protein} / W ${result.carbs} / T ${result.fat}. ${result.attribution}. ${result.source_url}. Sprawdź własną etykietę przed dodaniem.`
        : `Znaleziono lokalnie: ${result.name} · ${result.status}. Wyszukaj produkt w katalogu.`;
    } catch (err) { report(err); } finally { button.disabled = false; }
  };
  return load;
}
