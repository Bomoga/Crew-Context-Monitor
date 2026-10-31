import { render } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router";
import type { Status } from "../src/api/types.gen";
import { AppRoutes } from "../src/App";
import { StatusContext } from "../src/hooks/StatusContext";
import type { Polled } from "../src/hooks/usePolling";

const fixtures = import.meta.glob("../../contracts/examples/api/valid/*.json", {
  eager: true,
  import: "default",
});

/** A valid API fixture by file name, for example `fixture("status.all_green")`. */
export function fixture<T = unknown>(name: string): T {
  const key = Object.keys(fixtures).find((k) => k.endsWith(`/${name}.json`));
  if (!key) throw new Error(`no fixture named ${name}`);
  return fixtures[key] as T;
}

export function status(name: string, checkinDue?: boolean): Status {
  const s = fixture<Status>(`status.${name}`);
  return checkinDue === undefined ? s : { ...s, checkin_due: checkinDue };
}

export function polled(data: Status | null, over: Partial<Polled<Status>> = {}): Polled<Status> {
  return {
    data,
    error: null,
    stale: false,
    lastSuccessAt: data ? Date.now() : null,
    loading: false,
    refresh: () => {},
    ...over,
  };
}

/** Render the whole app at `path` with the given polled status instead of a network. */
export function renderRoute(path: string, value: Polled<Status> = polled(status("all_green"))) {
  return render(
    <StatusContext.Provider value={value}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </StatusContext.Provider>,
  );
}

/**
 * Stub `fetch` with a router: `route(url, init)` returns a JSON body, a `Response` or a promise of
 * one (to control timing), or `undefined` for a 404. Every request is recorded in `calls`.
 */
export function mockApi(route: (url: URL, init?: RequestInit) => unknown) {
  const calls: { url: URL; init?: RequestInit }[] = [];
  vi.stubGlobal("fetch", (input: string, init?: RequestInit) => {
    const url = new URL(input, "http://localhost");
    calls.push({ url, init });
    const body = route(url, init);
    if (body instanceof Response || body instanceof Promise) return Promise.resolve(body);
    if (body === undefined) {
      return Promise.resolve(new Response('{"detail":"Not Found"}', { status: 404 }));
    }
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
  return calls;
}
