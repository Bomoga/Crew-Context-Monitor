// Print the gzip size of the production JavaScript and warn above the budget (it does not fail).
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const BUDGET_KB = 400;
const assets = join(dirname(fileURLToPath(import.meta.url)), "..", "dist", "assets");

let total = 0;
for (const file of readdirSync(assets).filter((f) => f.endsWith(".js"))) {
  const kb = gzipSync(readFileSync(join(assets, file))).length / 1024;
  total += kb;
  console.log(`  ${file}: ${kb.toFixed(1)} kB gzip`);
}
console.log(`JavaScript total: ${total.toFixed(1)} kB gzip (budget ${BUDGET_KB} kB)`);
if (total > BUDGET_KB) {
  console.warn(`WARNING: the JavaScript bundle is over the ${BUDGET_KB} kB gzip budget`);
}
