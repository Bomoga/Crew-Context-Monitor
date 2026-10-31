import { expect, test } from "@playwright/test";

// Smoke test of the production build served by the Python process (make serve-mock): no Node
// process, no Vite. Run against a server started with `make serve-mock` by setting CCM_BASE_URL.
test("the production build is served by the mock API and the home page renders", async ({
  page,
}) => {
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  expect(response?.headers()["server"] ?? "").toContain("uvicorn");

  await expect(page.getByRole("heading", { name: "Home" })).toBeAttached();
  await expect(page.getByTestId("status-bar")).toBeVisible();
  for (const domain of ["cardio", "air", "thermal", "radiation"]) {
    await expect(page.getByTestId(`card-${domain}`)).toBeVisible();
  }
  await expect(page.getByRole("contentinfo")).toContainText(
    "Decision-support prototype, not a medical device",
  );
  // the page is built JavaScript from /assets, not a dev server
  const scripts = await page
    .locator("script[src]")
    .evaluateAll((els) => els.map((el) => el.getAttribute("src")));
  expect(scripts.length).toBeGreaterThan(0);
  for (const src of scripts) expect(src).toMatch(/^\/assets\/.+\.js$/);
});

test("a client-side route works on a full page load", async ({ page }) => {
  const response = await page.goto("/domain/air");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Air quality");
  await expect(page.getByRole("contentinfo")).toContainText("not a medical device");
});

test("an unknown API path is a JSON 404, not the app", async ({ request }) => {
  const response = await request.get("/api/nope");
  expect(response.status()).toBe(404);
  expect(response.headers()["content-type"]).toContain("application/json");
});
