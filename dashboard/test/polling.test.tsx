import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import allGreen from "../../contracts/examples/api/valid/status.all_green.json";
import airYellow from "../../contracts/examples/api/valid/status.air_yellow.json";
import { ApiError, api } from "../src/api/client";
import { useStatus } from "../src/hooks/useStatus";

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn(() => Promise.resolve(reply(allGreen)));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("useStatus", () => {
  it("fetches on mount and then every 5 seconds", async () => {
    const { result } = renderHook(() => useStatus());
    await advance(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/status");
    expect(result.current.data?.crew_status.level).toBe("green");
    expect(result.current.loading).toBe(false);
    await advance(4_900);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await advance(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await advance(10_000);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("marks the data stale after 15 seconds without a success, keeps it, and recovers", async () => {
    const { result } = renderHook(() => useStatus());
    await advance(0);
    expect(result.current.stale).toBe(false);

    fetchMock.mockImplementation(() => Promise.reject(new TypeError("network down")));
    await advance(10_000);
    expect(result.current.error?.message).toBe("network down");
    expect(result.current.stale).toBe(false); // 10 s since the last success
    expect(result.current.data?.crew_status.sentence).toContain("resting HR 62");

    await advance(6_000);
    expect(result.current.stale).toBe(true); // 16 s
    expect(result.current.data).not.toBeNull();

    fetchMock.mockImplementation(() => Promise.resolve(reply(airYellow)));
    await advance(5_000);
    expect(result.current.stale).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.data?.crew_status.level).toBe("yellow");
  });

  it("is stale when the very first request never succeeds", async () => {
    fetchMock.mockImplementation(() => Promise.reject(new Error("offline")));
    const { result } = renderHook(() => useStatus());
    await advance(16_000);
    expect(result.current.data).toBeNull();
    expect(result.current.stale).toBe(true);
  });

  it("aborts the request in flight when it unmounts and stops polling", async () => {
    let signal: AbortSignal | undefined;
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      signal = init?.signal ?? undefined;
      return new Promise(() => {});
    });
    const { unmount } = renderHook(() => useStatus());
    await advance(0);
    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
    const calls = fetchMock.mock.calls.length;
    await advance(30_000);
    expect(fetchMock).toHaveBeenCalledTimes(calls);
  });

  it("aborts a hung request when the next poll starts", async () => {
    const signals: AbortSignal[] = [];
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.signal) signals.push(init.signal);
      return new Promise(() => {});
    });
    renderHook(() => useStatus());
    await advance(5_100);
    expect(signals).toHaveLength(2);
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });
});

describe("api client", () => {
  it("logs a contract violation for a malformed response in dev mode", async () => {
    const bad = { ...allGreen, cards: allGreen.cards.slice(0, 3) };
    fetchMock.mockImplementation(() => Promise.resolve(reply(bad)));
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const status = await api.status();
    expect(status.cards).toHaveLength(3); // the data still comes through
    await vi.waitFor(() => expect(errors).toHaveBeenCalledTimes(1));
    expect(String(errors.mock.calls[0][0])).toContain("contract violation in /api/status");
    expect(JSON.stringify(errors.mock.calls[0][1])).toContain("cards");
  });

  it("accepts every valid status fixture and names the problem in an invalid one", async () => {
    const { contractViolations } = await import("../src/api/validate");
    expect(contractViolations("status", allGreen)).toEqual([]);
    expect(contractViolations("status", airYellow)).toEqual([]);
    const problems = contractViolations("status", { ...allGreen, source_mode: "demo" });
    expect(problems.join(" ")).toContain("/source_mode");
  });

  it("throws ApiError with the detail from the body on a non-2xx response", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(reply({ detail: "unknown crew member" }, 404)),
    );
    await expect(api.history({ metric: "hr", crew: "W9" })).rejects.toMatchObject({
      status: 404,
      detail: "unknown crew member",
    });
    await expect(api.history({ metric: "hr", crew: "W9" })).rejects.toBeInstanceOf(ApiError);
  });

  it("builds query strings and request bodies", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(reply({})));
    vi.spyOn(console, "error").mockImplementation(() => {});
    await api.history({ metric: "prv", crew: "W2", hours: 24, step: 300 });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/history?metric=prv&crew=W2&hours=24&step=300");
    await api.history({ metric: "co2_mmhg", crew: null });
    expect(fetchMock.mock.calls[1][0]).toBe("/api/history?metric=co2_mmhg");
    await api.events({ since: 12.5, limit: 50 });
    expect(fetchMock.mock.calls[2][0]).toBe("/api/events?since=12.5&limit=50");
    await api.approve("q-2");
    expect(fetchMock.mock.calls[3][0]).toBe("/api/earth-queue/q-2/approve");
    expect(fetchMock.mock.calls[3][1].method).toBe("POST");
    const body = { crew: "W1", mood: 4, sleep: 3, note: null };
    await api.checkin(body);
    expect(fetchMock.mock.calls[4][1].method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toEqual(body);
    await api.putAutoApprove({ crew_only: true, flight_surgeon: false, urgent: false });
    expect(fetchMock.mock.calls[5][1].method).toBe("PUT");
  });
});
