import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const ROUTES = ["/", "/domain/air", "/domain/cardio", "/history", "/events", "/settings"];

/** Go to a route and wait until its data has loaded. */
export async function open(page: Page, path: string) {
  await page.goto(path);
  await expect(page.getByRole("contentinfo")).toContainText("not a medical device");
  if (path === "/") {
    await expect(page.getByTestId("status-bar")).toBeVisible();
    await expect(page.getByTestId("card-air")).toBeVisible();
    await expect(page.getByTestId("timeline-chart").locator(".series-co2")).toBeAttached();
  } else if (path.startsWith("/domain/")) {
    await expect(page.locator("[data-testid^=chart-] .series-main").first()).toBeAttached();
  } else if (path === "/history") {
    await expect(page.getByTestId("chart-prv").locator(".series-main")).toBeAttached();
  } else if (path === "/events") {
    await expect(
      page.getByRole("region", { name: "Event log" }).getByRole("listitem").first(),
    ).toBeVisible();
  } else if (path === "/settings") {
    await expect(page.getByRole("region", { name: "Crew" })).toBeVisible();
  }
}

/** Restart the mock on a scenario, already `fastForward` simulated seconds in. */
export async function useScenario(
  request: APIRequestContext,
  name: string,
  fastForward = 0,
  speed = 60,
) {
  const response = await request.post("/api/_mock/scenario", {
    data: { name, speed, fast_forward: fastForward },
  });
  expect(response.ok()).toBeTruthy();
}
