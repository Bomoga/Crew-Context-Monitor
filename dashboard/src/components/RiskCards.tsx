import { Link } from "react-router";
import type { Card } from "../api/types.gen";
import { useStatusContext } from "../hooks/StatusContext";
import { formatValue } from "../lib/format";
import { DOMAIN_NAME } from "../lib/levels";
import { LevelBadge } from "./LevelBadge";

/** One risk card. The whole card is the link to the domain's detail view. */
export function RiskCard({ card }: { card: Card }) {
  return (
    <Link
      to={`/domain/${card.domain}`}
      data-testid={`card-${card.domain}`}
      data-level={card.level}
      className="flex h-72 flex-col gap-3 overflow-hidden rounded-xl border border-line bg-panel p-4 shadow-sm hover:border-accent"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-lg font-bold leading-tight">{DOMAIN_NAME[card.domain]}</h2>
        <LevelBadge level={card.level} />
      </div>
      <dl className="flex flex-col gap-1">
        {card.numbers.slice(0, 3).map((n) => (
          <div key={n.label} className="flex items-baseline justify-between gap-2 text-sm">
            <dt className="text-muted">{n.label}</dt>
            <dd className="text-right">
              <span className="font-semibold">
                {formatValue(n.value)} {n.unit}
              </span>
              <span className="text-muted"> · baseline {formatValue(n.baseline)}</span>
            </dd>
          </div>
        ))}
      </dl>
      <p className="line-clamp-4 text-sm">{card.reason}</p>
      {card.action ? (
        <p className="mt-auto line-clamp-2 text-sm text-muted">
          <span className="font-medium text-ink">Next step:</span> {card.action}
        </p>
      ) : null}
    </Link>
  );
}

/** The four cards in their fixed order: Cardiovascular, Air quality, Thermal, Radiation (proxy). */
export function RiskCards() {
  const { data: status } = useStatusContext();
  return (
    <section aria-label="Risk cards">
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {status?.cards.map((card) => (
          <li key={card.domain} className="flex flex-col">
            <RiskCard card={card} />
          </li>
        ))}
      </ul>
    </section>
  );
}
