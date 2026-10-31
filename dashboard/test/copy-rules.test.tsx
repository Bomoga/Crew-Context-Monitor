import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Events, History, Status } from "../src/api/types.gen";
import { FOOTER_TEXT } from "../src/components/Layout";
import { copyViolations, reasonViolations, textViolations } from "./copy";
import { fixture, mockApi, polled, renderRoute } from "./helpers";

const STATUS_NAMES = [
  "all_green",
  "learning",
  "air_yellow",
  "air_red_cabin",
  "cardio_yellow_individual",
  "radiation_red",
  "thermal_red",
  "node_offline",
  "correlation_active",
];
const DOMAINS = ["cardio", "air", "thermal", "radiation"];

const prv = fixture<History>("history.prv_6h");
const events = fixture<Events>("events.mixed");

function serveEverything() {
  mockApi((url) => {
    switch (url.pathname) {
      case "/api/history":
        return { ...prv, metric: url.searchParams.get("metric") ?? "prv" };
      case "/api/events":
        return events;
      case "/api/earth-queue":
        return fixture("earth_queue.pending");
      case "/api/settings":
        return fixture("settings.default");
      default:
        return undefined;
    }
  });
}

/** Wait until the route has shown the data it loads, so the scan sees real content. */
async function loaded(path: string) {
  if (path === "/") {
    await screen.findByTestId("window-countdown");
    await screen.findByTestId("queue-q-2");
    await waitFor(() =>
      expect(screen.getByTestId("timeline-chart").querySelector(".series-co2")).not.toBeNull(),
    );
  } else if (path.startsWith("/domain/")) {
    await waitFor(() =>
      expect(document.querySelector("[data-testid^=chart-] .series-main")).not.toBeNull(),
    );
  } else if (path === "/history") {
    await screen.findByTestId("chart-prv");
  } else if (path === "/events") {
    await within(await screen.findByRole("region", { name: "Event log" })).findAllByRole(
      "listitem",
    );
  } else {
    await screen.findByRole("region", { name: "Crew" });
  }
}

/** The sentences that must be reasons: the status bar's and each card's. */
function reasonsOf(s: Status): string[] {
  return [s.crew_status.sentence, ...s.cards.map((c) => c.reason)];
}

describe("the scanner itself", () => {
  it("catches each kind of violation in a deliberately broken string", () => {
    const broken =
      "Radiation 238 counts per minute, caused by the flare (z-score 3.1); HRV is down 12 ms.";
    expect(textViolations(broken)).toHaveLength(3);
    const el = document.createElement("div");
    el.innerHTML = `<p>${broken}</p><p>Radiation proxy 238 counts per minute.</p>`;
    const found = copyViolations(el);
    expect(found.some((v) => v.includes("caused by"))).toBe(true);
    expect(found.some((v) => v.includes("z-score"))).toBe(true);
    expect(found.some((v) => v.includes("HRV"))).toBe(true);
    expect(found.some((v) => v.includes('without "proxy"'))).toBe(true);
    expect(found.some((v) => v.includes("Radiation proxy 238"))).toBe(false);
    expect(reasonViolations("Pulse-rate variability is lower.")).toContain(
      "a reason needs a number",
    );
    expect(reasonViolations("Cabin CO2 3.1 mmHg.")).toContain(
      "a reason needs a baseline comparison",
    );
    expect(reasonViolations("Cabin CO2 3.1 mmHg, baseline 0.6 mmHg.")).toEqual([]);
  });
});

describe("home page, every status fixture", () => {
  it.each(STATUS_NAMES)(
    "%s: reasons, wording, footer and source badges follow the rules",
    async (name) => {
      serveEverything();
      const s = fixture<Status>(`status.${name}`);
      const { container } = renderRoute("/", polled(s));
      await loaded("/");

      for (const sentence of reasonsOf(s)) {
        expect(reasonViolations(sentence), sentence).toEqual([]);
        expect(container.textContent).toContain(sentence);
      }
      if (s.correlation) {
        // the correlation sentence is not a reason, but it still obeys the wording rules
        expect(textViolations(s.correlation.sentence)).toEqual([]);
        expect(container.textContent).toContain(s.correlation.sentence);
      }
      expect(copyViolations(container)).toEqual([]);
      expect(screen.getByRole("contentinfo")).toHaveTextContent(FOOTER_TEXT);

      for (const c of s.crew) {
        expect(screen.getByTestId(`source-${c.id}`).textContent).toMatch(/^(Hardware|Simulator)$/);
      }
      expect(screen.getByTestId("card-radiation")).toHaveTextContent(/proxy/i);
    },
  );
});

describe("every other route", () => {
  const routes = [
    ...DOMAINS.flatMap((d) => STATUS_NAMES.map((n) => [`/domain/${d}`, n] as const)),
    ["/history", "all_green"],
    ["/events", "all_green"],
    ["/settings", "all_green"],
  ] as const;

  it.each(routes)("%s with %s follows the rules and shows the footer", async (path, name) => {
    serveEverything();
    const { container } = renderRoute(path, polled(fixture<Status>(`status.${name}`)));
    await loaded(path);
    expect(copyViolations(container)).toEqual([]);
    expect(screen.getByRole("contentinfo")).toHaveTextContent(FOOTER_TEXT);
    if (path === "/domain/radiation") {
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Radiation (proxy)");
    }
  });
});

describe("the unknown-domain page", () => {
  it("also shows the footer and obeys the rules", () => {
    serveEverything();
    const { container } = renderRoute(
      "/domain/nonsense",
      polled(fixture<Status>("status.all_green")),
    );
    expect(copyViolations(container)).toEqual([]);
    expect(screen.getByRole("contentinfo")).toHaveTextContent(FOOTER_TEXT);
  });
});
