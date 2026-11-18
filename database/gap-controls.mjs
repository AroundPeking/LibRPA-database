// Gap-view state is independent of the searchable materials catalog. Keep the
// full comparison in its URL so a figure can be shared and revisited.
import { esc, recordElements } from './records.mjs';
import { gapMethods, defaultGapMethods } from './gaps.mjs';
import { ELEMENT_BY_SYMBOL } from './ptable.mjs';

// A reproducible composition preset, not an inference about oxidation state.
export function binaryTransitionMetalOxide(record) {
  const elements = recordElements(record);
  return elements.length === 2 && elements.includes('O') && elements.some(symbol => {
    const { row, column } = ELEMENT_BY_SYMBOL.get(symbol) || {};
    return row >= 4 && row <= 7 && column >= 3 && column <= 11;
  });
}

export function gapInventory(records) {
  const eligible = records.filter(record => gapMethods([record]).length);
  return { records: eligible, methods: gapMethods(eligible), materials: [...new Set(eligible.map(r => r.material))].sort() };
}

export function readGapParams(params, inventory) {
  const axis = ['material', 'experiment'].includes(params.get('x')) ? params.get('x') : 'ks';
  // A stale shared link must not broaden a missing material to the entire catalog.
  const materials = [...new Set(params.getAll('material').filter(Boolean))];
  const series = params.has('series') ? params.get('series').split(',') : defaultGapMethods(inventory.methods);
  return { axis, family: params.get('family') === 'tm-oxides' ? 'tm-oxides' : 'all',
    materials,
    methods: inventory.methods.map(m => m.key).filter(key => series.includes(key) && !(axis === 'ks' && key === 'ks')) };
}

export function writeGapParams(selection) {
  const params = new URLSearchParams();
  if (selection.axis !== 'ks') params.set('x', selection.axis);
  if (selection.family !== 'all') params.set('family', selection.family);
  for (const material of selection.materials) params.append('material', material);
  params.set('series', selection.methods.join(',')); // includes an intentional empty selection
  return params;
}

function familyRecords(inventory, family) {
  return family === 'tm-oxides' ? inventory.records.filter(binaryTransitionMetalOxide) : inventory.records;
}
export function selectedGapRecords(inventory, selection) {
  return familyRecords(inventory, selection.family).filter(r => !selection.materials.length || selection.materials.includes(r.material));
}

// The select stays small even in large catalogs; native type-ahead adds an
// exact material, not every formula with that substring. Chips remove one.
export function syncGapControls(panel, inventory, selection) {
  const { axis, methods, family, materials } = selection;
  panel.querySelector('#gap-axis').value = axis;
  panel.querySelector('#gap-family').value = family;
  const choices = [...new Set(familyRecords(inventory, family).map(r => r.material))].sort();
  panel.querySelector('#gap-add-material').innerHTML = '<option value="">Add a material…</option>' + choices.filter(m => !materials.includes(m)).map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join('');
  panel.querySelector('#gap-material-chips').innerHTML = materials.length ? materials.map(m => `<button type="button" class="element-pill" data-gap-remove="${esc(m)}" aria-label="Remove ${esc(m)}">${esc(m)} ×</button>`).join('') : `<span>${choices.length === 1 ? esc(choices[0]) + ' · only material in scope' : `All ${choices.length} materials in scope`}</span>`;
  const available = gapMethods(selectedGapRecords(inventory, selection));
  panel.querySelector('#gap-series').innerHTML = inventory.methods.filter(m => axis !== 'ks' || m.key !== 'ks').map(m => {
    const checked = methods.includes(m.key), missing = !available.some(item => item.key === m.key);
    return `<label><input type="checkbox" value="${esc(m.key)}"${checked ? ' checked' : ''}${missing && !checked ? ' disabled' : ''}> ${esc(m.label)}${missing ? ' (no values)' : ''}</label>`;
  }).join('');
}

export function installGapControls(panel, inventory, get, update) {
  panel.addEventListener('change', ({ target }) => {
    const selection = get();
    if (target.id === 'gap-family') {
      selection.family = target.value;
      selection.materials = [];
      if (selection.family === 'tm-oxides') {
        selection.axis = 'material';
        selection.methods = gapMethods(selectedGapRecords(inventory, selection)).map(m => m.key);
      }
    } else if (target.id === 'gap-axis') {
      selection.axis = target.value;
      if (selection.axis === 'ks') selection.methods = selection.methods.filter(m => m !== 'ks');
    } else if (target.id === 'gap-add-material' && target.value) {
      selection.materials.push(target.value);
    } else if (target.closest('#gap-series')) {
      selection.methods = [...panel.querySelectorAll('#gap-series input:checked')].map(input => input.value);
    } else return;
    update();
    if (target.closest('#gap-series') || target.type === 'checkbox') [...panel.querySelectorAll('#gap-series input')].find(input => input.value === target.value)?.focus();
  });
  panel.addEventListener('click', ({ target }) => {
    const selection = get(), chip = target.closest('[data-gap-remove]');
    if (chip) selection.materials = selection.materials.filter(m => m !== chip.dataset.gapRemove);
    else if (target.closest('#gap-reset')) Object.assign(selection, readGapParams(new URLSearchParams(), inventory));
    else return;
    update();
    if (chip) panel.querySelector('#gap-add-material').focus();
  });
}
