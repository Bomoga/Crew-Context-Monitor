// The copy rules from PLAN P6 as a scanner over rendered text.

const CAUSED_BY = /\bcaus(?:ed|es|ing)\s+by\b/i;
const Z_VALUE = /\bz[- ]?scores?\b|\bz\s*[=:≈]\s*[-+]?\d/i;
const HRV = /\bHRV\b|\bheart[- ]rate variability\b/i;
const RADIATION = /\bradiation\b/i;
const PROXY = /\bproxy\b/i;

/** Rules a single piece of visible text must obey wherever it appears. */
export function textViolations(text: string): string[] {
  const found: string[] = [];
  if (CAUSED_BY.test(text)) found.push('says "caused by" (write "consistent with")');
  if (Z_VALUE.test(text)) found.push("shows a z-score");
  if (HRV.test(text))
    found.push('says HRV or heart-rate variability (write "pulse-rate variability")');
  return found;
}

/** Text-bearing leaf elements: those with no element children. */
function leaves(root: ParentNode): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>("*")).filter(
    (el) => el.children.length === 0 && (el.textContent ?? "").trim() !== "",
  );
}

/** Every copy-rule violation in everything visible under `root`, each with where it was found. */
export function copyViolations(root: HTMLElement): string[] {
  const found: string[] = [];
  for (const el of leaves(root)) {
    const text = (el.textContent ?? "").trim();
    for (const v of textViolations(text)) found.push(`${v}: "${text.slice(0, 80)}"`);
    if (RADIATION.test(text) && !PROXY.test(text)) {
      found.push(`mentions radiation without "proxy": "${text.slice(0, 80)}"`);
    }
  }
  return found;
}

const NUMBER = /\d/;
// the baseline, or for cabin readings the normal band, or the change since a given time
const COMPARISON = /baseline|normal band|lower|above|\bup \d|changed|not enough data/i;

/** A reason is one plain sentence with a number and a comparison (to baseline or normal). */
export function reasonViolations(text: string): string[] {
  const found = textViolations(text);
  if (!NUMBER.test(text)) found.push("a reason needs a number");
  if (!COMPARISON.test(text)) found.push("a reason needs a baseline comparison");
  if (/\n/.test(text.trim())) found.push("a reason is one sentence");
  return found;
}
