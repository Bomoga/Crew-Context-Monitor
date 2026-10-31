import type { Attribution, Status } from "../api/types.gen";
import { useStatusContext } from "../hooks/StatusContext";
import { formatDuration } from "../lib/format";
import { DOMAIN_NAME } from "../lib/levels";
import { LevelBadge } from "./LevelBadge";

const ATTRIBUTION_LABEL: Record<Exclude<Attribution, null>, string> = {
  cabin: "Cabin",
  individual: "Individual",
  unclear: "Unclear",
};

/** Seconds until alerts start while any baseline is still learning, else null. */
export function learningRemaining(status: Status): number | null {
  const ends = status.crew
    .filter((c) => c.baseline === "learning" && c.learning_ends_t !== null)
    .map((c) => (c.learning_ends_t as number) - status.t);
  return ends.length > 0 ? Math.max(...ends) : null;
}

// One fixed size for every state, so a change of level never moves the page.
const FRAME =
  "flex h-24 items-center gap-4 rounded-xl border border-line bg-panel px-5 py-3 shadow-sm";

/** The worst card's sentence, its attribution and the suggested action, in one row. */
export function StatusBar() {
  const { data: status } = useStatusContext();
  if (!status) {
    return (
      <section aria-label="Crew status" data-testid="status-bar" className={FRAME}>
        <p className="text-muted">Waiting for the first reading.</p>
      </section>
    );
  }
  const { crew_status: cs } = status;
  const remaining = learningRemaining(status);
  const learning = remaining !== null;
  return (
    <section
      aria-label="Crew status"
      data-testid="status-bar"
      data-state={learning ? "learning" : cs.level}
      className={FRAME}
    >
      <LevelBadge level={cs.level} />
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-base font-semibold">{cs.sentence}</p>
        {cs.action ? (
          <p className="truncate text-sm text-muted">
            <span className="font-medium text-ink">Next step:</span> {cs.action}
          </p>
        ) : null}
      </div>
      <div className="w-40 shrink-0 text-right text-sm text-muted">
        {learning ? (
          <p>
            <span className="font-medium text-ink">Learning.</span> Alerts start in{" "}
            {formatDuration(remaining)}
          </p>
        ) : (
          <>
            {cs.domain ? <p>{DOMAIN_NAME[cs.domain]}</p> : null}
            {cs.attribution ? (
              <p>
                <span className="font-medium text-ink">Attribution:</span>{" "}
                {ATTRIBUTION_LABEL[cs.attribution]}
              </p>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
