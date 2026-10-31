import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Settings as SettingsData } from "../api/types.gen";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { usePolling } from "../hooks/usePolling";
import { clockTime } from "../lib/format";

type Tier = keyof SettingsData["auto_approve"];

const TIERS: { key: Tier; label: string; help: string }[] = [
  { key: "crew_only", label: "Crew only", help: "Summaries that stay with the crew" },
  { key: "flight_surgeon", label: "Flight surgeon", help: "Summaries for the flight surgeon" },
  { key: "urgent", label: "Urgent", help: "Anything marked urgent" },
];

export default function Settings() {
  const { data, error } = usePolling((s) => api.settings(s), 30_000);
  const [latest, setLatest] = useState<SettingsData | null>(null);
  const settings = latest ?? data;

  const [toggleError, setToggleError] = useState<string | null>(null);
  const [resetting, setResetting] = useState<string | null>(null);
  const [resetDone, setResetDone] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [enrolled, setEnrolled] = useState<string | null>(null);

  async function toggle(tier: Tier, on: boolean) {
    if (!settings) return;
    const before = settings;
    const next = { ...settings.auto_approve, [tier]: on };
    setToggleError(null);
    setLatest({ ...settings, auto_approve: next }); // optimistic
    try {
      setLatest(await api.putAutoApprove(next));
    } catch {
      setLatest(before); // roll back
      setToggleError("Could not save that change. The setting is back to what it was.");
    }
  }

  async function enroll(e: FormEvent) {
    e.preventDefault();
    setEnrolled(null);
    if (!/^W[0-9]+$/.test(id)) {
      setFormError("Crew id must be W followed by a number, for example W4.");
      return;
    }
    if (name.trim().length === 0 || name.trim().length > 40) {
      setFormError("Enter a name of 1 to 40 characters.");
      return;
    }
    setFormError(null);
    try {
      setLatest(await api.enroll({ id, name: name.trim() }));
      setEnrolled(`${name.trim()} (${id}) is enrolled.`);
      setId("");
      setName("");
    } catch {
      setFormError("Could not enroll that crew member. Try again.");
    }
  }

  async function confirmReset() {
    if (!resetting) return;
    const crew = resetting;
    setResetting(null);
    setResetError(null);
    setResetDone(null);
    try {
      setLatest(await api.resetBaseline({ crew, metric: null }));
      setResetDone(
        `${crew}'s baseline was reset. Alerts for ${crew} resume after it has learned again.`,
      );
    } catch {
      setResetError(`Could not reset ${crew}'s baseline. Nothing was changed.`);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
      {!settings ? (
        <p className="text-muted">
          {error ? "Could not load the settings." : "Loading the settings."}
        </p>
      ) : (
        <>
          <section
            aria-label="Crew"
            className="rounded-xl border border-line bg-panel p-4 shadow-sm"
          >
            <h2 className="text-lg font-bold">Crew</h2>
            <ul className="mt-2 divide-y divide-line">
              {settings.crew.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>
                    <span className="font-semibold">{c.name}</span>
                    <span className="text-muted">
                      {" "}
                      · {c.id} · enrolled {clockTime(c.enrolled_t)} UTC
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() => setResetting(c.id)}
                    aria-label={`Reset baseline for ${c.id}`}
                    className="rounded-md border border-line px-3 py-1.5 text-sm font-medium hover:border-accent"
                  >
                    Reset baseline
                  </button>
                </li>
              ))}
            </ul>
            {resetDone ? (
              <p role="status" className="mt-2 text-sm">
                {resetDone}
              </p>
            ) : null}
            {resetError ? (
              <p role="alert" className="mt-2 text-sm text-level-red">
                {resetError}
              </p>
            ) : null}

            <form
              onSubmit={enroll}
              aria-label="Enroll a crew member"
              className="mt-4 flex flex-wrap items-end gap-3"
            >
              <div className="flex flex-col gap-1">
                <label htmlFor="enroll-id" className="text-sm font-medium">
                  Crew id
                </label>
                <input
                  id="enroll-id"
                  value={id}
                  onChange={(e) => setId(e.target.value)}
                  placeholder="W4"
                  className="w-28 rounded-md border border-line bg-panel px-3 py-2"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="enroll-name" className="text-sm font-medium">
                  Name
                </label>
                <input
                  id="enroll-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-56 rounded-md border border-line bg-panel px-3 py-2"
                />
              </div>
              <button
                type="submit"
                className="rounded-md border border-accent px-4 py-2 text-sm font-semibold"
              >
                Enroll
              </button>
            </form>
            {formError ? (
              <p role="alert" className="mt-2 text-sm text-level-red">
                {formError}
              </p>
            ) : null}
            {enrolled ? (
              <p role="status" className="mt-2 text-sm">
                {enrolled}
              </p>
            ) : null}
          </section>

          <section
            aria-label="Auto-approve"
            className="rounded-xl border border-line bg-panel p-4 shadow-sm"
          >
            <h2 className="text-lg font-bold">Send to Earth without asking</h2>
            <p className="mt-1 text-sm text-muted">
              When a tier is on, new summaries in it are approved automatically. Everything else
              waits for approval in the Earth queue.
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              {TIERS.map((t) => (
                <li key={t.key}>
                  <label className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={settings.auto_approve[t.key]}
                      onChange={(e) => void toggle(t.key, e.target.checked)}
                      className="h-5 w-5"
                    />
                    <span>
                      <span className="font-medium">{t.label}</span>
                      <span className="text-sm text-muted"> · {t.help}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
            {toggleError ? (
              <p role="alert" className="mt-2 text-sm text-level-red">
                {toggleError}
              </p>
            ) : null}
          </section>
        </>
      )}

      {resetting ? (
        <ConfirmDialog
          title={`Reset ${resetting}'s baseline?`}
          confirmLabel="Reset baseline"
          onConfirm={() => void confirmReset()}
          onCancel={() => setResetting(null)}
        >
          <p>
            The monitor forgets what is normal for {resetting} and learns it again. Alerts for{" "}
            {resetting} are held back while it learns.
          </p>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
