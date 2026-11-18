// Periodic-table element picker for the materials explorer. Pure rendering:
// the page owns state and passes counts and the current selection in.
import { esc, ELEMENT_SYMBOLS } from "./records.mjs";

const SYMBOLS = [...ELEMENT_SYMBOLS];

const NAMES = ("Hydrogen Helium Lithium Beryllium Boron Carbon Nitrogen Oxygen Fluorine Neon Sodium Magnesium " +
  "Aluminium Silicon Phosphorus Sulfur Chlorine Argon Potassium Calcium Scandium Titanium Vanadium Chromium " +
  "Manganese Iron Cobalt Nickel Copper Zinc Gallium Germanium Arsenic Selenium Bromine Krypton Rubidium " +
  "Strontium Yttrium Zirconium Niobium Molybdenum Technetium Ruthenium Rhodium Palladium Silver Cadmium " +
  "Indium Tin Antimony Tellurium Iodine Xenon Caesium Barium Lanthanum Cerium Praseodymium Neodymium " +
  "Promethium Samarium Europium Gadolinium Terbium Dysprosium Holmium Erbium Thulium Ytterbium Lutetium " +
  "Hafnium Tantalum Tungsten Rhenium Osmium Iridium Platinum Gold Mercury Thallium Lead Bismuth Polonium " +
  "Astatine Radon Francium Radium Actinium Thorium Protactinium Uranium Neptunium Plutonium Americium Curium " +
  "Berkelium Californium Einsteinium Fermium Mendelevium Nobelium Lawrencium Rutherfordium Dubnium " +
  "Seaborgium Bohrium Hassium Meitnerium Darmstadtium Roentgenium Copernicium Nihonium Flerovium Moscovium " +
  "Livermorium Tennessine Oganesson").split(" ");

// Grid row and column (group) of an element in the 18-column layout. Rows 9
// and 10 hold the lanthanide and actinide series below a spacer row.
export function elementPosition(z) {
  if (z === 1) return [1, 1];
  if (z === 2) return [1, 18];
  if (z <= 10) return [2, z <= 4 ? z - 2 : z + 8];
  if (z <= 18) return [3, z <= 12 ? z - 10 : z];
  if (z <= 36) return [4, z - 18];
  if (z <= 54) return [5, z - 36];
  if (z >= 58 && z <= 71) return [9, z - 54];
  if (z >= 90 && z <= 103) return [10, z - 86];
  if (z <= 86) return [6, z <= 57 ? z - 54 : z - 68];
  return [7, z <= 89 ? z - 86 : z - 100];
}

export const ELEMENTS = SYMBOLS.map((symbol, index) => {
  const z = index + 1;
  const [row, column] = elementPosition(z);
  return { z, symbol, name: NAMES[index], row, column };
});

export const ELEMENT_BY_SYMBOL = new Map(ELEMENTS.map(element => [element.symbol, element]));

// Five coverage steps keep the shading readable in both themes; the exact
// count is always printed in the cell and in its accessible name.
export function heatLevel(count, max) {
  if (!count || !max) return 0;
  return Math.min(5, Math.max(1, Math.ceil((count / max) * 5)));
}

export function renderPeriodicTable({ counts = new Map(), selected = new Set(), available = new Set(), noun = "record" } = {}) {
  // Counts may carry other keys (a facet tally also holds its "all" total).
  const max = Math.max(0, ...ELEMENTS.map(element => counts.get(element.symbol) || 0));
  // The f-block rows are drawn only when one of their elements has data.
  const fBlock = ELEMENTS.some(element => element.row >= 9 && available.has(element.symbol));
  const cells = ELEMENTS.filter(element => fBlock || element.row < 9).map(element => {
    const style = `grid-row:${element.row};grid-column:${element.column}`;
    const count = counts.get(element.symbol) || 0;
    if (!available.has(element.symbol)) {
      return `<span class="pt-cell pt-empty" style="${style}" aria-hidden="true"><small>${element.z}</small><b>${element.symbol}</b></span>`;
    }
    const isSelected = selected.has(element.symbol);
    const label = `${element.name} (${element.symbol}), ${count} ${noun}${count === 1 ? "" : "s"}`;
    return `<button type="button" class="pt-cell pt-heat-${heatLevel(count, max)}${isSelected ? " is-selected" : ""}" style="${style}" data-element="${esc(element.symbol)}" aria-pressed="${isSelected}" aria-label="${esc(label)}" title="${esc(label)}"><small>${element.z}</small><b>${element.symbol}</b><i>${count}</i></button>`;
  }).join("");
  // Row 8 is left empty: the stylesheet gives it a small fixed height so the
  // f-block series sit visibly apart from the main table.
  return `<div class="ptable${fBlock ? " has-f-block" : ""}" role="group" aria-label="Periodic table element filter">${cells}</div>`;
}
