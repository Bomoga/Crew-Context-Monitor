import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LevelBadge } from "../src/components/LevelBadge";
import { FOOTER_TEXT } from "../src/components/Layout";
import { LEVEL_WORD, LEVELS } from "../src/lib/levels";
import { polled, renderRoute, status } from "./helpers";

const ROUTES = [
  ["/", "Home"],
  ["/domain/air", "Air quality"],
  ["/domain/cardio", "Cardiovascular"],
  ["/domain/thermal", "Thermal"],
  ["/domain/radiation", "Radiation (proxy)"],
  ["/history", "History"],
  ["/events", "Events"],
  ["/settings", "Settings"],
] as const;

describe("app shell", () => {
  it.each(ROUTES)("renders %s with its title and the footer", (path, title) => {
    renderRoute(path);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent(FOOTER_TEXT);
  });

  it("shows the footer on an unknown domain inside the shell", () => {
    renderRoute("/domain/nonsense");
    expect(screen.getByRole("heading", { name: "Domain not found" })).toBeInTheDocument();
    expect(screen.getByText(FOOTER_TEXT)).toBeInTheDocument();
  });

  it("has a main navigation with the four destinations and marks the current page", () => {
    renderRoute("/history");
    const nav = screen.getByRole("navigation", { name: "Main" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["Home", "History", "Events", "Settings"]);
    expect(within(nav).getByRole("link", { name: "History" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("keeps the banner slot at the same height with and without a banner", () => {
    const { unmount } = renderRoute("/", polled(status("all_green")));
    const quiet = screen.getByTestId("banner-slot");
    expect(quiet).toBeEmptyDOMElement();
    const height = quiet.style.height;
    expect(height).not.toBe("");
    unmount();

    const stale = renderRoute("/", polled(status("all_green"), { stale: true }));
    const slot = screen.getByTestId("banner-slot");
    expect(slot.style.height).toBe(height);
    expect(within(slot).getByRole("status")).toHaveTextContent(/last data/i);
    stale.unmount();

    renderRoute("/", polled(status("node_offline")));
    const offline = screen.getByTestId("banner-slot");
    expect(offline.style.height).toBe(height);
    expect(offline).toHaveTextContent("Offline: W3, C1");
  });

  it("says so when there is no data yet", () => {
    renderRoute("/", polled(null, { loading: true }));
    expect(screen.getByTestId("banner-slot")).toHaveTextContent("Waiting for the monitor");
    renderRoute("/", polled(null, { error: new Error("down") }));
    expect(screen.getAllByTestId("banner-slot")[1]).toHaveTextContent("Cannot reach the monitor");
  });
});

describe("level badge", () => {
  it.each(LEVELS)("shows the word for %s next to its color", (level) => {
    render(<LevelBadge level={level} />);
    const badge = screen.getByText(LEVEL_WORD[level]);
    expect(badge).toHaveAttribute("data-level", level);
  });

  it("uses the same size classes for every level", () => {
    const sizes = LEVELS.map((level) => {
      const { container, unmount } = render(<LevelBadge level={level} />);
      const classes = (container.firstElementChild as HTMLElement).className
        .split(" ")
        .filter((c) => /^(min-w|px|py|gap|text-sm|font|rounded|inline-flex)/.test(c))
        .sort()
        .join(" ");
      unmount();
      return classes;
    });
    expect(new Set(sizes).size).toBe(1);
  });
});
