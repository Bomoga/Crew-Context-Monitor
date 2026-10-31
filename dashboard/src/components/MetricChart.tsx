import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import type { History } from "../api/types.gen";
import { clockTime } from "../lib/format";

interface Props {
  history: History;
  title: string;
  /** Shown above the chart as the plain-language description of the lines. */
  height?: string;
}

/**
 * One raw series with its baseline band and the yellow and red limit lines, if the metric has
 * them. The band and lines are drawn from the API; nothing here decides what is abnormal.
 */
export function MetricChart({ history, title, height = "h-64" }: Props) {
  const { points, baseline, limits, unit } = history;
  const band = (baseline ?? []).map((b) => ({ t: b.t, band: [b.lo, b.hi] as [number, number] }));
  const tMin = points[0]?.t ?? 0;
  const tMax = points.at(-1)?.t ?? 1;
  return (
    <figure className="m-0">
      <figcaption className="mb-1 flex items-baseline justify-between gap-2 text-sm">
        <span className="font-semibold">{title}</span>
        <span className="text-muted">
          {unit}
          {band.length > 0 ? " · shaded band is the baseline range" : ""}
        </span>
      </figcaption>
      <div
        role="img"
        aria-label={`${title} in ${unit} over time${band.length > 0 ? ", with the baseline range" : ""}${
          limits?.yellow != null || limits?.red != null ? " and limit lines" : ""
        }`}
        data-testid={`chart-${history.metric}`}
        className={`${height} w-full`}
      >
        {points.length === 0 ? (
          <p className="pt-8 text-center text-muted">No readings yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
              <CartesianGrid stroke="var(--line)" strokeDasharray="3 3" />
              <XAxis
                dataKey="t"
                type="number"
                domain={[tMin, tMax]}
                tickFormatter={clockTime}
                stroke="var(--muted)"
                allowDuplicatedCategory={false}
              />
              <YAxis stroke="var(--muted)" domain={["auto", "auto"]} />
              {band.length > 0 ? (
                <Area
                  data={band}
                  dataKey="band"
                  className="baseline-band"
                  stroke="none"
                  fill="var(--accent)"
                  fillOpacity={0.14}
                  isAnimationActive={false}
                />
              ) : null}
              {limits?.yellow != null ? (
                <ReferenceLine
                  y={limits.yellow}
                  className={`limit-line ${limits.red === limits.yellow ? "both" : "yellow"}`}
                  stroke="var(--yellow-mark)"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  ifOverflow="extendDomain"
                  label={{
                    value:
                      limits.red === limits.yellow
                        ? history.metric === "cpm"
                          ? "Poisson threshold"
                          : "Threshold"
                        : "Yellow line",
                    position: "insideTopRight",
                    fill: "var(--ink)",
                  }}
                />
              ) : null}
              {limits?.red != null && limits.red !== limits.yellow ? (
                <ReferenceLine
                  y={limits.red}
                  className="limit-line red"
                  stroke="var(--red-mark)"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  ifOverflow="extendDomain"
                  label={{ value: "Red line", position: "insideTopRight", fill: "var(--ink)" }}
                />
              ) : null}
              <Line
                data={points}
                dataKey="mean"
                name={title}
                className="series-main"
                stroke="var(--series-prv)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </figure>
  );
}
