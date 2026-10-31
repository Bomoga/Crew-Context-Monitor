import { useCallback, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { Events, History } from "../api/types.gen";
import { useSelectedCrew } from "../hooks/CrewSelection";
import { useStatusContext } from "../hooks/StatusContext";
import { usePolling } from "../hooks/usePolling";
import { clockTime } from "../lib/format";

const WINDOW_HOURS = 6;
const REFRESH_MS = 15_000;

export type Series = "prv" | "hr_resid";

const SERIES_LABEL: Record<Series, { name: string; unit: string }> = {
  prv: { name: "Pulse-rate variability", unit: "ms" },
  hr_resid: { name: "HR residual", unit: "bpm" },
};

interface TimelineData {
  co2: History;
  crewSeries: History;
  events: Events;
}

/** Cabin CO2 (left axis) over the selected crew member's pulse-rate variability (right axis). */
export function Timeline() {
  const { data: status } = useStatusContext();
  const [crew] = useSelectedCrew(status?.crew.map((c) => c.id) ?? []);
  const [series, setSeries] = useState<Series>("prv");

  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<TimelineData> => {
      const [co2, crewSeries, events] = await Promise.all([
        api.history({ metric: "co2_mmhg", hours: WINDOW_HOURS, step: 60 }, signal),
        api.history({ metric: series, crew, hours: WINDOW_HOURS, step: 60 }, signal),
        api.events({ limit: 200 }, signal),
      ]);
      return { co2, crewSeries, events };
    },
    [crew, series],
  );
  const { data, error } = usePolling(fetcher, REFRESH_MS, 45_000, `${crew}/${series}`);

  const label = SERIES_LABEL[series];
  const tEnd = status?.t ?? data?.co2.points.at(-1)?.t ?? 0;
  const tStart = tEnd - WINDOW_HOURS * 3600;
  const events = (data?.events.events ?? []).filter((e) => e.t >= tStart && e.t <= tEnd);
  const correlation = status?.correlation ?? null;
  const corrEvent = events.find((e) => e.kind === "correlation");

  return (
    <section aria-label="Timeline" className="rounded-xl border border-line bg-panel p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold">
          Cabin CO2 and {label.name.toLowerCase()}
          {crew ? <span className="text-muted"> · {crew}</span> : null}
        </h2>
        <div role="group" aria-label="Series" className="flex gap-1">
          {(Object.keys(SERIES_LABEL) as Series[]).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={series === key}
              onClick={() => setSeries(key)}
              className={`rounded-md border px-3 py-1.5 text-sm font-medium ${
                series === key
                  ? "border-accent bg-panel text-ink ring-2 ring-accent"
                  : "border-line text-muted"
              }`}
            >
              {SERIES_LABEL[key].name}
            </button>
          ))}
        </div>
      </div>

      <p data-testid="lag-label" className="mt-2 h-6 text-sm font-medium">
        {correlation ? correlation.sentence : ""}
      </p>

      <div
        role="img"
        aria-label={`Last ${WINDOW_HOURS} hours: cabin CO2 in mmHg and ${label.name.toLowerCase()} in ${label.unit}, with event markers`}
        data-testid="timeline-chart"
        className="h-80 w-full"
      >
        {data ? (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" />
              <XAxis
                dataKey="t"
                type="number"
                domain={[tStart, tEnd]}
                tickFormatter={clockTime}
                stroke="var(--muted)"
                allowDuplicatedCategory={false}
              />
              <YAxis
                yAxisId="co2"
                orientation="left"
                stroke="var(--series-co2)"
                label={{
                  value: "CO2 (mmHg)",
                  angle: -90,
                  position: "insideLeft",
                  fill: "var(--series-co2)",
                }}
              />
              <YAxis
                yAxisId="crew"
                orientation="right"
                stroke="var(--series-prv)"
                label={{
                  value: `${label.name} (${label.unit})`,
                  angle: 90,
                  position: "insideRight",
                  fill: "var(--series-prv)",
                }}
              />
              {correlation && corrEvent ? (
                <ReferenceArea
                  yAxisId="co2"
                  x1={corrEvent.t - correlation.lag_min * 60}
                  x2={corrEvent.t}
                  className="lag-band"
                  fill="var(--accent)"
                  fillOpacity={0.12}
                />
              ) : null}
              {events.map((e) => (
                <ReferenceLine
                  key={e.id}
                  yAxisId="co2"
                  x={e.t}
                  className={`event-marker ${e.simulated ? "simulated" : "observed"}`}
                  stroke={e.simulated ? "var(--accent)" : "var(--muted)"}
                  strokeDasharray={e.simulated ? "5 4" : undefined}
                  strokeWidth={e.simulated ? 2 : 1.5}
                />
              ))}
              <Line
                yAxisId="co2"
                data={data.co2.points}
                dataKey="mean"
                name="Cabin CO2 (mmHg)"
                stroke="var(--series-co2)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                className="series-co2"
              />
              <Line
                yAxisId="crew"
                data={data.crewSeries.points}
                dataKey="mean"
                name={`${label.name} (${label.unit})`}
                stroke="var(--series-prv)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                className="series-crew"
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <p className="pt-8 text-center text-muted">
            {error ? "Could not load the timeline." : "Loading the timeline."}
          </p>
        )}
      </div>
      <p className="mt-2 text-sm text-muted">
        Solid lines mark events seen by the monitor; dashed lines mark simulated events.
      </p>
    </section>
  );
}
