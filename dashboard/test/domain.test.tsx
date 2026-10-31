import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { History } from "../src/api/types.gen";
import { fixture, mockApi, polled, renderRoute, status } from "./helpers";

const base = fixture<History>("history.prv_6h");
const UNITS: Record<string, string> = {
  hr: "bpm",
  prv: "ms",
  hr_resid: "bpm",
  co2_mmhg: "mmHg",
  voc: "index",
  temp_c: "C",
  skin_c: "C",
  cpm: "counts/min",
};
const LIMITS: Record<string, History["limits"]> = {
  co2_mmhg: { yellow: 2.5, red: 3.0 },
  temp_c: { yellow: null, red: 27 },
  cpm: { yellow: 23.4, red: 23.4 },
};

function history(metric: string, crew: string | null): History {
  return {
    ...base,
    metric: metric as History["metric"],
    unit: UNITS[metric],
    crew,
    limits: LIMITS[metric] ?? { yellow: null, red: null },
  };
}

function serve() {
  return mockApi((url) => {
    if (url.pathname !== "/api/history") return undefined;
    const metric = url.searchParams.get("metric")!;
    return history(metric, url.searchParams.get("crew"));
  });
}

async function charts(ids: string[]) {
  for (const id of ids) await screen.findByTestId(`chart-${id}`);
  return ids.map((id) => screen.getByTestId(`chart-${id}`));
}

describe("domain detail view", () => {
  it("cardio: raw series with baseline bands, the detector and the model coefficients", async () => {
    const calls = serve();
    renderRoute("/domain/cardio", polled(status("cardio_yellow_individual")));
    const [hr, prv, resid] = await charts(["hr", "prv", "hr_resid"]);
    for (const chart of [hr, prv, resid]) {
      await waitFor(() => expect(chart.querySelector(".series-main")).not.toBeNull());
      expect(chart.querySelector(".baseline-band")).not.toBeNull();
      expect(chart.querySelector(".limit-line")).toBeNull();
    }
    expect(calls.map((c) => c.url.search)).toContain("?metric=prv&crew=W1&hours=6&step=60");
    const s = status("cardio_yellow_individual");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Cardiovascular");
    expect(screen.getByText(s.cards[0].reason)).toBeInTheDocument();
    const detector = screen.getByTestId("detector");
    expect(detector).toHaveTextContent("residual cusum");
    expect(detector).toHaveTextContent("alarm 40 min ago");
    const model = screen.getByRole("heading", {
      name: /model for resting heart rate/i,
    }).parentElement!;
    expect(model).toHaveTextContent("38.2 bpm");
    expect(model).toHaveTextContent("21.5 bpm per g");
    expect(model).toHaveTextContent("0.7 bpm per C");
  });

  it("air: both limit lines and the detector state", async () => {
    serve();
    renderRoute("/domain/air", polled(status("air_red_cabin")));
    const [co2] = await charts(["co2_mmhg", "voc"]);
    await waitFor(() => expect(co2.querySelector(".series-main")).not.toBeNull());
    expect(co2.querySelector(".limit-line.yellow")).not.toBeNull();
    expect(co2.querySelector(".limit-line.red")).not.toBeNull();
    expect(screen.getByTestId("detector")).toHaveTextContent("above 3.0 mmHg for 12 min");
    expect(screen.queryByText(/model for resting heart rate/i)).toBeNull();
    expect(screen.getByText(/Cabin CO2 3.1 mmHg, baseline 0.6 mmHg/)).toBeInTheDocument();
  });

  it("thermal: cabin and skin temperature with the red limit", async () => {
    serve();
    renderRoute("/domain/thermal", polled(status("thermal_red")));
    const [temp, skin] = await charts(["temp_c", "skin_c"]);
    await waitFor(() => expect(temp.querySelector(".series-main")).not.toBeNull());
    expect(temp.querySelectorAll(".limit-line")).toHaveLength(1);
    expect(temp.querySelector(".limit-line.red")).not.toBeNull();
    expect(skin.querySelector(".baseline-band")).not.toBeNull();
    expect(screen.getByTestId("detector")).toHaveTextContent("above 27 C for 15 min");
  });

  it("radiation: the Poisson threshold line and why a fixed threshold misfires", async () => {
    serve();
    renderRoute("/domain/radiation", polled(status("radiation_red")));
    const [cpm] = await charts(["cpm"]);
    await waitFor(() => expect(cpm.querySelector(".series-main")).not.toBeNull());
    expect(cpm.querySelectorAll(".limit-line")).toHaveLength(1);
    expect(cpm.querySelector(".limit-line.both")).not.toBeNull();
    const why = screen.getByTestId("why-not-fixed");
    expect(why).toHaveTextContent("Why not a fixed threshold?");
    expect(why).toHaveTextContent(/proxy/i);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Radiation (proxy)");
    expect(screen.getByTestId("detector")).toHaveTextContent("2 of 2 windows above threshold");
  });

  it("shows no why-not-fixed sentence outside the radiation domain", async () => {
    serve();
    renderRoute("/domain/air", polled(status("all_green")));
    await charts(["co2_mmhg"]);
    expect(screen.queryByTestId("why-not-fixed")).toBeNull();
  });

  it("an unknown domain shows a not-found message inside the shell", () => {
    serve();
    renderRoute("/domain/sleep", polled(status("all_green")));
    expect(screen.getByRole("heading", { name: "Domain not found" })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent("not a medical device");
    expect(
      within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link"),
    ).toHaveLength(4);
  });
});
