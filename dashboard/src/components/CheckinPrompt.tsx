import { useState } from "react";
import { api } from "../api/client";
import { useSelectedCrew } from "../hooks/CrewSelection";
import { useStatusContext } from "../hooks/StatusContext";

const MOOD_WORDS = ["Low", "Down", "Okay", "Good", "Great"];
const SLEEP_WORDS = ["Poor", "Short", "Okay", "Good", "Great"];

function Scale({
  label,
  words,
  value,
  onPick,
}: {
  label: string;
  words: string[];
  value: number | null;
  onPick: (n: number) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-1">
      <p className="text-sm font-medium">{label}</p>
      <div className="flex gap-1">
        {words.map((word, i) => {
          const n = i + 1;
          return (
            <button
              key={n}
              type="button"
              aria-pressed={value === n}
              aria-label={`${label} ${n} of 5, ${word}`}
              onClick={() => onPick(n)}
              className={`flex h-12 w-14 flex-col items-center justify-center rounded-md border text-sm ${
                value === n
                  ? "border-accent bg-surface font-bold ring-2 ring-accent"
                  : "border-line"
              }`}
            >
              <span className="text-base">{n}</span>
              <span className="text-[11px] text-muted">{word}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * The daily check-in: mood and sleep on a 1 to 5 scale and an optional note. It floats at the
 * bottom of the screen so it never moves the page, and it is context only: sending it changes
 * no level and no color.
 */
export function CheckinPrompt() {
  const { data: status, refresh } = useStatusContext();
  const [crew] = useSelectedCrew(status?.crew.map((c) => c.id) ?? []);
  const [mood, setMood] = useState<number | null>(null);
  const [sleep, setSleep] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [showNote, setShowNote] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!status?.checkin_due || dismissed || !crew) return null;

  async function send() {
    if (mood === null || sleep === null || crew === null) return;
    setSending(true);
    setError(null);
    try {
      await api.checkin({ crew, mood, sleep, note: note.trim() === "" ? null : note.trim() });
      setDismissed(true);
      refresh();
    } catch {
      setError("Could not send the check-in. Try again.");
    } finally {
      setSending(false);
    }
  }

  return (
    <aside
      role="dialog"
      aria-label="Daily check-in"
      className="fixed bottom-4 right-4 z-40 flex w-[22rem] max-w-[calc(100vw-2rem)] flex-col gap-3 rounded-xl border border-line bg-panel p-4 shadow-xl"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-base font-bold">Daily check-in for {crew}</h2>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="rounded-md px-2 py-1 text-sm text-muted underline"
        >
          Not now
        </button>
      </div>
      <p className="text-sm text-muted">
        Fifteen seconds. This adds context; it never changes a level.
      </p>
      <Scale label="Mood" words={MOOD_WORDS} value={mood} onPick={setMood} />
      <Scale label="Sleep" words={SLEEP_WORDS} value={sleep} onPick={setSleep} />
      {showNote ? (
        <div className="flex flex-col gap-1">
          <label htmlFor="checkin-note" className="text-sm font-medium">
            Note (optional)
          </label>
          <textarea
            id="checkin-note"
            value={note}
            maxLength={500}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            className="rounded-md border border-line bg-panel px-3 py-2 text-sm"
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowNote(true)}
          className="self-start text-sm text-accent underline"
        >
          Add a note
        </button>
      )}
      {error ? (
        <p role="alert" className="text-sm text-level-red">
          {error}
        </p>
      ) : null}
      <button
        type="button"
        disabled={mood === null || sleep === null || sending}
        onClick={() => void send()}
        className="rounded-md border border-accent px-4 py-2 text-sm font-semibold enabled:hover:bg-surface disabled:border-line disabled:text-muted"
      >
        Send check-in
      </button>
    </aside>
  );
}
