import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { open, ROUTES } from "./lib";

for (const scheme of ["light", "dark"] as const) {
  test.describe(`axe, ${scheme} scheme`, () => {
    test.use({ colorScheme: scheme });

    for (const path of ROUTES) {
      test(`no serious or critical violations on ${path}`, async ({ page }) => {
        await open(page, path);
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        const bad = results.violations.filter(
          (v) => v.impact === "serious" || v.impact === "critical",
        );
        const summary = bad.map(
          (v) =>
            `${v.id} (${v.impact}): ${v.nodes
              .slice(0, 3)
              .map((n) => n.html.slice(0, 120))
              .join(" | ")}`,
        );
        expect(summary).toEqual([]);
      });
    }
  });
}

test("a phone viewport has no serious or critical violations on the home page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, "/");
  const results = await new AxeBuilder({ page }).analyze();
  const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(bad.map((v) => v.id)).toEqual([]);
});
