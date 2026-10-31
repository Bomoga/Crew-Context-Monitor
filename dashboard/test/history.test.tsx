import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { History } from "../src/api/types.gen";
import { fixture, mockApi, polled, renderRoute, status } from "./helpers";

const prv = fixture<History>("history.prv_6h");
const co2 = fixture<History>("history.co2_cabin");

function serve() {
  return mockApi((url) => {
    if (url.pathname !== "/api/history") return undefined;
    return url.searchParams.get("metric") === "co2_mmhg" ? co2 : prv;
  });
}

const searches = (calls: ReturnType<typeof serve>) => calls.map((c) => c.url.search);

describe("history view", () => {
  it("asks for the 7-day trend of pulse-rate variability for the first crew member", async () => {
    const calls = serve();
    renderRoute("/history", polled(status("all_green")));
    await screen.findByTestId("chart-prv");
    expect(searches(calls)).toContain("?metric=prv&crew=W1&hours=168&step=3600");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("History");
    expect(screen.getByRole("img", { name: /pulse-rate variability/i })).toBeInTheDocument();
  });

  it("requests the chosen metric and crew when the selectors change", async () => {
    const calls = serve();
    renderRoute("/history", polled(status("all_green")));
    await screen.findByTestId("chart-prv");

    await userEvent.selectOptions(screen.getByLabelText("Measure"), "hr");
    await waitFor(() =>
      expect(searches(calls)).toContain("?metric=hr&crew=W1&hours=168&step=3600"),
    );
    await userEvent.selectOptions(screen.getByLabelText("Crew member"), "W3");
    await waitFor(() =>
      expect(searches(calls)).toContain("?metric=hr&crew=W3&hours=168&step=3600"),
    );
    await userEvent.selectOptions(screen.getByLabelText("Time span"), "24 hours");
    await waitFor(() => expect(searches(calls)).toContain("?metric=hr&crew=W3&hours=24&step=600"));
  });

  it("sends no crew for a cabin measure and disables the crew selector", async () => {
    const calls = serve();
    renderRoute("/history", polled(status("all_green")));
    await screen.findByTestId("chart-prv");
    await userEvent.selectOptions(screen.getByLabelText("Measure"), "co2_mmhg");
    await waitFor(() => expect(searches(calls)).toContain("?metric=co2_mmhg&hours=168&step=3600"));
    expect(screen.getByLabelText("Crew member")).toBeDisabled();
    expect(screen.getByText(/not per crew member/i)).toBeInTheDocument();
  });

  it("shows the CUSUM panel with the alarm line when the API sends one", async () => {
    serve();
    renderRoute("/history", polled(status("all_green")));
    const chart = await screen.findByTestId("cusum-chart");
    await waitFor(() => expect(chart.querySelector(".cusum-pos")).not.toBeNull());
    expect(chart.querySelectorAll(".alarm-line")).toHaveLength(1);
    expect(chart.querySelector(".cusum-neg")).not.toBeNull();
    expect(screen.getByText("Drift detector (CUSUM)")).toBeInTheDocument();
  });

  it("says there is no drift detector for a measure without a CUSUM", async () => {
    serve();
    renderRoute("/history", polled(status("all_green")));
    await screen.findByTestId("cusum-chart");
    await userEvent.selectOptions(screen.getByLabelText("Measure"), "co2_mmhg");
    expect(
      await screen.findByText("There is no drift detector for this measure."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("cusum-chart")).toBeNull();
  });

  it("shows the limit lines for CO2", async () => {
    serve();
    renderRoute("/history", polled(status("all_green")));
    await screen.findByTestId("chart-prv");
    await userEvent.selectOptions(screen.getByLabelText("Measure"), "co2_mmhg");
    const chart = await screen.findByTestId("chart-co2_mmhg");
    await waitFor(() => expect(chart.querySelectorAll(".limit-line")).toHaveLength(2));
  });
});
