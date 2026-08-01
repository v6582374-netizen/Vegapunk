import { expect } from "@playwright/test";
import { test } from "./fixtures";

test.setTimeout(60_000);

test("Discovery is an independent shell on the native sidecar route", async ({ page }) => {
  const paths: string[] = [];
  page.on("request", (request) => {
    paths.push(new URL(request.url()).pathname);
  });

  await page.setViewportSize({ width: 1024, height: 720 });
  await page.goto("/");
  await page.getByTestId("nav-discovery").click();

  const view = page.getByTestId("discovery-view");
  await expect(view).toBeVisible();
  await expect(view.getByRole("heading", { name: "Discovery" })).toBeVisible();
  await expect(view.getByRole("tab", { name: "Preparation" })).toBeVisible();
  await expect(view.getByRole("heading", { name: "Your first Preparation is empty" })).toBeVisible();

  // Preparation, Current Launch, and History are internal tabs, not new sidebar destinations.
  await expect(page.locator(".sidebar").getByRole("button", { name: "Preparation", exact: true })).toHaveCount(0);
  await view.getByRole("tab", { name: "Current Launch" }).click();
  await expect(view.getByRole("heading", { name: "No current Launch" })).toBeVisible();
  await view.getByRole("tab", { name: "History" }).click();
  await expect(view.getByRole("heading", { name: "No Launch history yet" })).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(view).toBeVisible();
  await expect(view.getByRole("tab", { name: "History" })).toBeVisible();

  await expect.poll(() => paths.includes("/v1/discovery")).toBe(true);
  expect(paths.filter((path) => /^\/api\/(workspace|admin)(\/|$)/.test(path))).toEqual([]);
});
