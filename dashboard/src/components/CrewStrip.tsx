import { useSelectedCrew } from "../hooks/CrewSelection";
import { useStatusContext } from "../hooks/StatusContext";
import { LevelBadge } from "./LevelBadge";

const SOURCE_WORD = { hw: "Hardware", sim: "Simulator" } as const;

/** One chip per crew member: level, online state and where the data comes from. */
export function CrewStrip() {
  const { data: status } = useStatusContext();
  const ids = status?.crew.map((c) => c.id) ?? [];
  const [selected, select] = useSelectedCrew(ids);
  if (!status) return <div data-testid="crew-strip" className="h-[5.5rem]" />;
  return (
    <ul
      aria-label="Crew"
      data-testid="crew-strip"
      className="flex h-[5.5rem] flex-wrap items-stretch gap-3"
    >
      {status.crew.map((c) => (
        <li key={c.id} className="flex">
          <button
            type="button"
            aria-pressed={selected === c.id}
            onClick={() => select(c.id)}
            className={`flex w-60 flex-col justify-between rounded-xl border px-4 py-3 text-left ${
              selected === c.id
                ? "border-accent bg-panel ring-2 ring-accent"
                : "border-line bg-panel"
            }`}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="text-base font-semibold">{c.name}</span>
              <LevelBadge level={c.level} />
            </span>
            <span className="flex items-center justify-between text-sm text-muted">
              <span data-testid={`source-${c.id}`}>{SOURCE_WORD[c.src]}</span>
              <span>{c.online ? "Online" : "Offline"}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
