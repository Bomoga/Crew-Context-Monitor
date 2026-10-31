import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Status } from "../src/api/types.gen";
import { polled, renderRoute, status } from "./helpers";

const FIXTURES = [
  "all_green",
  "air_yellow",
  "air_red_cabin",
  "cardio_yellow_individual",
  "radiation_red",
  "thermal_red",
  "learning",
] as const;
const ORDER = ["cardio", "air", "thermal", "radiation"] as const;
const TITLES = ["Cardiovascular", "Air quality", "Thermal", "Radiation (proxy)"];

function cardEls(): HTMLElement[] {
  return ORDER.map((d) => screen.getByTestId(`card-${d}`));
}

describe("risk cards", () => {
  it.each(FIXTURES)("shows four cards in the fixed order for %s", (name) => {
    renderRoute("/", polled(status(name)));
    const cards = cardEls();
    const dom = Array.from(
      screen.getByRole("region", { name: "Risk cards" }).querySelectorAll("[data-testid^=card-]"),
    );
    expect(dom).toEqual(cards); // fixed order in the document
    cards.forEach((card, i) => {
      expect(within(card).getByRole("heading", { level: 2 })).toHaveTextContent(TITLES[i]);
    });
  });

  it.each(FIXTURES)(
    "shows each card's level word, numbers with baselines, and reason (%s)",
    (name) => {
      const s: Status = status(name);
      renderRoute("/", polled(s));
      s.cards.forEach((c) => {
        const el = screen.getByTestId(`card-${c.domain}`);
        expect(el).toHaveAttribute("data-level", c.level);
        expect(el).toHaveTextContent({ green: "Green", yellow: "Yellow", red: "Red" }[c.level]);
        expect(el).toHaveTextContent(c.reason);
        expect(c.numbers.length).toBeGreaterThanOrEqual(1);
        for (const n of c.numbers.slice(0, 3)) {
          expect(el).toHaveTextContent(n.label);
          expect(el).toHaveTextContent(/baseline/);
        }
        if (c.action) expect(el).toHaveTextContent(c.action);
      });
    },
  );

  it("makes the whole card a link to its domain detail view", () => {
    renderRoute("/", polled(status("all_green")));
    for (const d of ORDER) {
      expect(screen.getByTestId(`card-${d}`)).toHaveAttribute("href", `/domain/${d}`);
    }
  });

  it("keeps card positions and sizes the same between fixtures", () => {
    const layouts = FIXTURES.map((name) => {
      const { unmount } = renderRoute("/", polled(status(name)));
      const layout = cardEls().map((el) => ({
        domain: el.getAttribute("data-testid"),
        sizeClasses: el.className
          .split(" ")
          .filter((c) => /^(h-|w-|p-|flex|gap-|overflow)/.test(c))
          .sort(),
        wrapperClass: el.parentElement?.className,
      }));
      unmount();
      return layout;
    });
    for (const layout of layouts) expect(layout).toEqual(layouts[0]);
    expect(layouts[0][0].sizeClasses).toContain("h-72");
  });

  it("never renders a z value", () => {
    for (const name of FIXTURES) {
      const { unmount, container } = renderRoute("/", polled(status(name)));
      expect(container.textContent).not.toMatch(/z[- ]?score|\bz\s*[=:]\s*-?\d/i);
      unmount();
    }
  });

  it("shows a dash for a missing number instead of inventing one", () => {
    const s = structuredClone(status("all_green"));
    s.cards[0].numbers[0].value = null;
    renderRoute("/", polled(s));
    expect(within(screen.getByTestId("card-cardio")).getByText(/—/)).toBeInTheDocument();
  });
});
