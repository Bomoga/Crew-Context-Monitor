import { useCallback } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import type { Card, Domain as DomainName, History } from "../api/types.gen";
import { LevelBadge } from "../components/LevelBadge";
import { MetricChart } from "../components/MetricChart";
import { useSelectedCrew } from "../hooks/CrewSelection";
import { useStatusContext } from "../hooks/StatusContext";
import { usePolling } from "../hooks/usePolling";
import { formatValue } from "../lib/format";
import { DOMAIN_NAME, isDomain } from "../lib/levels";

interface Plot {
  metric: History["metric"];
  title: string;
  /** True for per-crew metrics, fetched for the selected crew member. */
  crew: boolean;
}

const PLOTS: Record<DomainName, Plot[]> = {
  cardio: [
    { metric: "hr", title: "Heart rate", crew: true },
    { metric: "prv", title: "Pulse-rate variability", crew: true },
    {
      metric: "hr_resid",
      title: "Heart-rate residual (what the model does not explain)",
      crew: true,
    },
  ],
  air: [
    { metric: "co2_mmhg", title: "Cabin CO2", crew: false },
    { metric: "voc", title: "VOC index", crew: false },
  ],
  thermal: [
    { metric: "temp_c", title: "Cabin temperature", crew: false },
    { metric: "skin_c", title: "Skin temperature", crew: true },
  ],
  radiation: [{ metric: "cpm", title: "Radiation proxy, counts per minute", crew: false }],
};

const WHY_NOT_FIXED =
  "Why not a fixed threshold? Radiation proxy counts are random, so a fixed line is either " +
  "crossed by chance on quiet days or missed in a real event. The line shown is the baseline " +
  "rate plus 4 standard deviations of a 10-minute count, and it takes one window above it for " +
  "yellow and two in a row for red.";

function ModelPanel({ model }: { model: NonNullable<Card["model"]> }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3 text-sm">
      <h3 className="font-semibold">Model for resting heart rate</h3>
      <p className="mt-1 text-muted">
        Heart rate = beta0 + beta1 × activity + beta2 × (cabin temperature − 22 C). What the model
        explains is not flagged.
      </p>
      <dl className="mt-2 grid grid-cols-3 gap-2">
        <div>
          <dt className="text-muted">beta0 (resting)</dt>
          <dd className="font-semibold">{formatValue(model.beta0)} bpm</dd>
        </div>
        <div>
          <dt className="text-muted">beta1 (activity)</dt>
          <dd className="font-semibold">{formatValue(model.beta1)} bpm per g</dd>
        </div>
        <div>
          <dt className="text-muted">beta2 (cabin temperature)</dt>
          <dd className="font-semibold">{formatValue(model.beta2)} bpm per C</dd>
        </div>
      </dl>
    </div>
  );
}

export default function Domain() {
  const { name } = useParams();
  const { data: status } = useStatusContext();
  const [crew] = useSelectedCrew(status?.crew.map((c) => c.id) ?? []);
  const domain = isDomain(name) ? name : null;

  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<History[]> => {
      if (!domain) return [];
      return Promise.all(
        PLOTS[domain].map((p) =>
          api.history({ metric: p.metric, crew: p.crew ? crew : null, hours: 6, step: 60 }, signal),
        ),
      );
    },
    [domain, crew],
  );
  const { data: histories, error } = usePolling(fetcher, 15_000, 45_000, `${domain}/${crew}`);

  if (!domain) {
    return (
      <section>
        <h1 className="text-2xl font-bold tracking-tight">Domain not found</h1>
        <p className="mt-2 text-muted">There is no domain called “{name}”.</p>
        <p className="mt-4">
          <Link to="/" className="font-medium text-accent underline">
            Back to the overview
          </Link>
        </p>
      </section>
    );
  }

  const card = status?.cards.find((c) => c.domain === domain) ?? null;
  return (
    <div className="flex flex-col gap-4">
      <p>
        <Link to="/" className="text-sm font-medium text-accent underline">
          ← Overview
        </Link>
      </p>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">{DOMAIN_NAME[domain]}</h1>
        {card ? <LevelBadge level={card.level} /> : null}
      </header>

      {card ? (
        <section
          aria-label="Summary"
          className="rounded-xl border border-line bg-panel p-4 shadow-sm"
        >
          <p className="text-base font-semibold">{card.reason}</p>
          {card.action ? (
            <p className="mt-1 text-sm text-muted">
              <span className="font-medium text-ink">Next step:</span> {card.action}
            </p>
          ) : null}
          <p data-testid="detector" className="mt-3 text-sm">
            <span className="font-medium">Detector:</span> {card.detector.name} ·{" "}
            <LevelBadge level={card.detector.state} className="align-middle" />{" "}
            <span className="text-muted">{card.detector.detail}</span>
          </p>
          {card.model ? (
            <div className="mt-3">
              <ModelPanel model={card.model} />
            </div>
          ) : null}
          {domain === "radiation" ? (
            <p data-testid="why-not-fixed" className="mt-3 text-sm">
              {WHY_NOT_FIXED}
            </p>
          ) : null}
        </section>
      ) : null}

      <section aria-label="Series" className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {histories ? (
          histories.map((h, i) => (
            <div key={h.metric} className="rounded-xl border border-line bg-panel p-4 shadow-sm">
              <MetricChart
                history={h}
                title={`${PLOTS[domain][i].title}${PLOTS[domain][i].crew && crew ? ` · ${crew}` : ""}`}
              />
            </div>
          ))
        ) : (
          <p className="text-muted">
            {error ? "Could not load the series." : "Loading the series."}
          </p>
        )}
      </section>
    </div>
  );
}
