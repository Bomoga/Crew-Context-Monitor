import { expect, test } from "@playwright/test";
import { loadExpected, type Domain } from "./expected";
import { useScenario } from "./lib";

// For every scenario: restart the mock already part way in, frozen at each checkpoint time (speed
// "max" runs no clock), load the dashboard, and check the states the scenario's expect block says
// it should show. Runs one scenario at a time against the one shared mock.
const expected = loadExpected();
const DOMAINS: Domain[] = ["cardio", "air", "thermal", "radiation"];
const RANK = { green: 0, yellow: 1, red: 2 } as const;
const WORD = { green: "Green", yellow: "Yellow", red: "Red" } as const;

test.describe.configure({ mode: "serial" });

test.afterAll(async ({ request }) => {
  // leave the shared mock where the other specs expect it
  await useScenario(request, "scrubber_failure", 13_200, 60);
});

for (const [name, spec] of Object.entries(expected)) {
  test.describe(name, () => {
    for (const cp of spec.checkpoints) {
      test(`at +${Math.round(cp.offset / 60)} min`, async ({ page, request }) => {
        test.setTimeout(150_000);
        await useScenario(request, name, cp.offset, "max");
        await page.goto("/");
        await expect(page.getByTestId("status-bar")).toBeVisible();

        // card levels, in the fixed order, with the level word on each
        for (const domain of DOMAINS) {
          const want = cp.cards[domain];
          const card = page.getByTestId(`card-${domain}`);
          await expect(card, `${name} ${domain} card`).toHaveAttribute("data-level", want.level);
          await expect(card).toContainText(WORD[want.level]);
        }

        // the status bar shows the worst level
        const worst = DOMAINS.map((d) => cp.cards[d].level).reduce((a, b) =>
          RANK[b] > RANK[a] ? b : a,
        );
        await expect(page.getByTestId("status-bar")).toHaveAttribute("data-state", worst);

        // attribution text and which crew members are named
        const cardio = cp.cards.cardio;
        const cardioCard = page.getByTestId("card-cardio");
        if (cardio.level !== "green" && cardio.attribution === "cabin") {
          await expect(cardioCard).toContainText("lower pulse-rate variability");
          await expect(cardioCard).toContainText(`${cardio.crew.length} of 3 crew`);
        } else if (cardio.level !== "green" && cardio.attribution === "individual") {
          await expect(cardioCard).toContainText(`Only ${cardio.crew.join(" and ")} changed`);
          await expect(cardioCard).toContainText("cabin within normal");
        } else {
          await expect(cardioCard).not.toContainText("lower pulse-rate variability");
        }
        const crewButtons = page.getByTestId("crew-strip").getByRole("button");
        for (const id of ["W1", "W2", "W3"]) {
          const level =
            cardio.level !== "green" && cardio.crew.includes(id) ? cardio.level : "green";
          const offline = cp.offline.includes(id);
          const chip = crewButtons.filter({ hasText: id }).first();
          await expect(chip).toContainText(WORD[level]);
          await expect(chip).toContainText(offline ? "Offline" : "Online");
        }

        // the correlation lag label
        const lag = page.getByTestId("lag-label");
        if (cp.correlation)
          await expect(lag).toContainText("Pulse-rate variability began dropping");
        else await expect(lag).toBeEmpty();

        // timeline markers: one per simulated event in the last six hours
        const chart = page.getByTestId("timeline-chart");
        await expect(chart.locator(".series-co2")).toBeAttached();
        await expect(chart.locator(".event-marker.simulated")).toHaveCount(cp.sim_events.length);

        // offline nodes are named in the banner; otherwise the slot is empty
        const banner = page.getByTestId("banner-slot");
        if (cp.offline.length > 0) {
          await expect(banner).toContainText(`Offline: ${[...cp.offline].join(", ")}`);
        } else {
          await expect(banner).toBeEmpty();
        }

        await page.screenshot({
          path: `test-results/scenarios/${name}-${Math.round(cp.offset)}.png`,
          fullPage: true,
        });
      });
    }
  });
}
