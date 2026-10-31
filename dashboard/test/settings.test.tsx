import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Settings } from "../src/api/types.gen";
import { fixture, mockApi, polled, renderRoute, status } from "./helpers";

const settings = fixture<Settings>("settings.default");

/** Serve settings; mutations get the settings back with `after` applied unless `fail` is set. */
function serve(options: { fail?: boolean } = {}) {
  const calls = mockApi((url, init) => {
    if (url.pathname === "/api/settings" && init?.method !== "PUT") return settings;
    if (init?.method === "PUT" || init?.method === "POST") {
      if (options.fail) return new Response('{"detail":"nope"}', { status: 500 });
      const body = JSON.parse(String(init.body));
      if (url.pathname === "/api/settings") return { ...settings, auto_approve: body };
      if (url.pathname === "/api/settings/enroll") {
        return { ...settings, crew: [...settings.crew, { ...body, enrolled_t: 1 }] };
      }
      return settings;
    }
    return undefined;
  });
  return {
    calls,
    writes: () =>
      calls
        .filter((c) => c.init?.method === "PUT" || c.init?.method === "POST")
        .map((c) => ({
          path: c.url.pathname,
          method: c.init?.method,
          body: JSON.parse(String(c.init?.body)),
        })),
  };
}

async function loaded() {
  await screen.findByRole("region", { name: "Crew" });
}

describe("settings view", () => {
  it("shows the crew and the auto-approve tiers from the API", async () => {
    serve();
    renderRoute("/settings", polled(status("all_green")));
    await loaded();
    const crew = screen.getByRole("region", { name: "Crew" });
    expect(within(crew).getByText("W1")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Crew only/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Flight surgeon/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Urgent/ })).not.toBeChecked();
  });

  it("sends the whole auto-approve object when a tier is toggled", async () => {
    const api = serve();
    renderRoute("/settings", polled(status("all_green")));
    await loaded();
    await userEvent.click(screen.getByRole("checkbox", { name: /Flight surgeon/ }));
    await waitFor(() => expect(api.writes()).toHaveLength(1));
    expect(api.writes()[0]).toEqual({
      path: "/api/settings",
      method: "PUT",
      body: { crew_only: true, flight_surgeon: true, urgent: false },
    });
    expect(screen.getByRole("checkbox", { name: /Flight surgeon/ })).toBeChecked();
  });

  it("puts a toggle back when saving fails", async () => {
    serve({ fail: true });
    renderRoute("/settings", polled(status("all_green")));
    await loaded();
    await userEvent.click(screen.getByRole("checkbox", { name: /Urgent/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("back to what it was");
    expect(screen.getByRole("checkbox", { name: /Urgent/ })).not.toBeChecked();
  });

  it("enrolls a crew member with the id and name as typed", async () => {
    const api = serve();
    renderRoute("/settings", polled(status("all_green")));
    await loaded();
    await userEvent.type(screen.getByLabelText("Crew id"), "W4");
    await userEvent.type(screen.getByLabelText("Name"), "Alex");
    await userEvent.click(screen.getByRole("button", { name: "Enroll" }));
    await waitFor(() => expect(api.writes()).toHaveLength(1));
    expect(api.writes()[0]).toEqual({
      path: "/api/settings/enroll",
      method: "POST",
      body: { id: "W4", name: "Alex" },
    });
    expect(await screen.findByText("Alex (W4) is enrolled.")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Crew" })).getByText("Alex"),
    ).toBeInTheDocument();
  });

  it("does not send an enroll request for a bad id or an empty name", async () => {
    const api = serve();
    renderRoute("/settings", polled(status("all_green")));
    await loaded();
    await userEvent.type(screen.getByLabelText("Crew id"), "crew4");
    await userEvent.type(screen.getByLabelText("Name"), "Alex");
    await userEvent.click(screen.getByRole("button", { name: "Enroll" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("W followed by a number");
    await userEvent.clear(screen.getByLabelText("Crew id"));
    await userEvent.type(screen.getByLabelText("Crew id"), "W4");
    await userEvent.clear(screen.getByLabelText("Name"));
    await userEvent.click(screen.getByRole("button", { name: "Enroll" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("1 to 40 characters");
    expect(api.writes()).toHaveLength(0);
  });

  it("asks in the app before resetting a baseline, and sends nothing on cancel", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const api = serve();
    renderRoute("/settings", polled(status("all_green")));
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Reset baseline for W2" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("Reset W2's baseline?");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(api.writes()).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(api.writes()).toHaveLength(0);
    expect(confirm).not.toHaveBeenCalled();
  });

  it("closes the dialog with Escape without sending anything", async () => {
    const api = serve();
    renderRoute("/settings", polled(status("all_green")));
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Reset baseline for W1" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(api.writes()).toHaveLength(0);
  });

  it("resets only after confirmation and sends the crew id with a null metric", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const api = serve();
    renderRoute("/settings", polled(status("all_green")));
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Reset baseline for W2" }));
    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Reset baseline" }),
    );
    await waitFor(() => expect(api.writes()).toHaveLength(1));
    expect(api.writes()[0]).toEqual({
      path: "/api/settings/reset-baseline",
      method: "POST",
      body: { crew: "W2", metric: null },
    });
    expect(await screen.findByText(/W2's baseline was reset/)).toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();
  });

  it("says so when the reset fails", async () => {
    serve({ fail: true });
    renderRoute("/settings", polled(status("all_green")));
    await loaded();
    await userEvent.click(screen.getByRole("button", { name: "Reset baseline for W1" }));
    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Reset baseline" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed");
  });
});
