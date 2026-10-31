import { expect, test, type Page } from "@playwright/test";
import { open, useScenario } from "./lib";

const DOMAINS = ["cardio", "air", "thermal", "radiation"] as const;

async function cardBoxes(page: Page) {
  const boxes = [];
  for (const d of DOMAINS) {
    const box = await page.getByTestId(`card-${d}`).boundingBox();
    expect(box, `card-${d} is on the page`).not.toBeNull();
    boxes.push(box!);
  }
  return boxes;
}

test.describe("tablet first, 1280 x 800", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the four cards sit in one row and the page does not scroll sideways", async ({ page }) => {
    await open(page, "/");
    const boxes = await cardBoxes(page);
    const tops = new Set(boxes.map((b) => Math.round(b.y)));
    expect(tops.size).toBe(1);
    const lefts = boxes.map((b) => b.x);
    expect(lefts).toEqual([...lefts].sort((a, b) => a - b));
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test.describe("phone, 390 x 844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the four cards are stacked in one column, each below the one before", async ({ page }) => {
    await open(page, "/");
    const boxes = await cardBoxes(page);
    for (let i = 1; i < boxes.length; i++) {
      expect(boxes[i].y).toBeGreaterThanOrEqual(boxes[i - 1].y + boxes[i - 1].height - 1);
      expect(Math.round(boxes[i].x)).toBe(Math.round(boxes[0].x));
    }
    for (const b of boxes) expect(b.x + b.width).toBeLessThanOrEqual(390);
  });

  test("the page does not scroll sideways on any route", async ({ page }) => {
    for (const path of ["/", "/domain/air", "/history", "/events", "/settings"]) {
      await open(page, path);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, path).toBeLessThanOrEqual(0);
    }
  });
});

test("every card and the status bar show their level as a word", async ({ page }) => {
  await open(page, "/");
  for (const d of DOMAINS) {
    const card = page.getByTestId(`card-${d}`);
    const level = await card.getAttribute("data-level");
    expect(["green", "yellow", "red"]).toContain(level);
    await expect(card).toContainText(level![0].toUpperCase() + level!.slice(1));
  }
  await expect(page.getByTestId("status-bar")).toContainText(/Green|Yellow|Red/);
});

test("keyboard focus is clearly visible on links, buttons and fields", async ({ page }) => {
  await open(page, "/");
  const visible = async () =>
    page.evaluate(() => {
      const el = document.activeElement as HTMLElement;
      const style = getComputedStyle(el);
      return {
        tag: el.tagName,
        outline: style.outlineStyle,
        width: parseFloat(style.outlineWidth),
      };
    });
  const seen: string[] = [];
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    const focus = await visible();
    seen.push(focus.tag);
    expect(focus.outline, `outline on ${focus.tag} #${i}`).not.toBe("none");
    expect(focus.width).toBeGreaterThanOrEqual(2);
  }
  expect(seen).toContain("A");
  expect(seen).toContain("BUTTON");
});

test.describe("layout does not jump when the state changes", () => {
  test.describe.configure({ mode: "serial" });
  test.use({ viewport: { width: 1280, height: 800 } });

  test("the status bar and cards keep their boxes between a red and a green state", async ({
    page,
    request,
  }) => {
    await useScenario(request, "scrubber_failure", 13_200);
    await open(page, "/");
    await expect(page.getByTestId("status-bar")).toHaveAttribute("data-state", "red");
    const redBar = await page.getByTestId("status-bar").boundingBox();
    const redCards = await cardBoxes(page);

    await useScenario(request, "quiet_day", 1_200);
    await expect(page.getByTestId("status-bar")).toHaveAttribute("data-state", "green", {
      timeout: 15_000,
    });
    const greenBar = await page.getByTestId("status-bar").boundingBox();
    const greenCards = await cardBoxes(page);

    expect(greenBar).toEqual(redBar);
    expect(greenCards).toEqual(redCards);

    await useScenario(request, "scrubber_failure", 13_200);
  });
});
