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
  await expect(view.getByRole("heading", { name: "Gather context" })).toBeVisible();

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

test("Gather accepts multiple files, saves explicitly, and keeps saved state separate", async ({ page }) => {
  const paths: string[] = [];
  page.on("request", (request) => {
    paths.push(new URL(request.url()).pathname);
  });

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await page.getByTestId("nav-discovery").click();

  const view = page.getByTestId("discovery-view");
  await expect(view.getByRole("heading", { name: "Gather context" })).toBeVisible();

  await view.getByRole("textbox", { name: "Research text" }).fill("Compare membrane performance in saline water.");
  const intake = page.waitForRequest(
    (request) =>
      request.url().endsWith("/v1/discovery/preparation/intake") && request.method() === "POST",
  );
  await view.getByLabel("Source files").setInputFiles([
    {
      name: "brief.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("Membrane notes"),
    },
    {
      name: "measurements.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("salinity,flux\n10,42\n"),
    },
  ]);
  const intakeRequest = await intake;
  const intakeBody = intakeRequest.postDataJSON();
  expect(intakeBody.text).toBe("Compare membrane performance in saline water.");
  expect(intakeBody.files).toHaveLength(2);
  expect(intakeBody.files.map((file: { filename: string }) => file.filename)).toEqual([
    "brief.md",
    "measurements.csv",
  ]);

  await expect(view.getByText("brief.md")).toBeVisible();
  await expect(view.getByText("measurements.csv")).toBeVisible();
  await expect(view.getByText("Draft changes not saved")).toBeVisible();

  const firstSave = page.waitForRequest(
    (request) =>
      request.url().endsWith("/v1/discovery/preparation/save") && request.method() === "POST",
  );
  await view.getByRole("button", { name: "Save Preparation" }).click();
  const firstSaveRequest = await firstSave;
  expect(firstSaveRequest.postDataJSON()).toEqual({
    text: "Compare membrane performance in saline water.",
  });
  await expect(view.getByText("Preparation saved")).toBeVisible();

  const deleteRequest = page.waitForRequest(
    (request) =>
      request.url().includes("/v1/discovery/preparation/sources/") && request.method() === "DELETE",
  );
  await view.getByRole("button", { name: "Remove brief.md" }).click();
  await deleteRequest;
  await expect(view.getByText("brief.md")).toHaveCount(0);
  await expect(view.getByText("measurements.csv")).toBeVisible();
  await expect(view.getByText(/Saved Preparation remains unchanged until Save/)).toBeVisible();

  const secondSave = page.waitForRequest(
    (request) =>
      request.url().endsWith("/v1/discovery/preparation/save") && request.method() === "POST",
  );
  await view.getByRole("button", { name: "Save Preparation" }).click();
  await secondSave;
  await expect(view.getByText("Preparation saved")).toBeVisible();
  await expect(view.getByText(/Saved Preparation remains unchanged until Save/)).toHaveCount(0);

  await view.getByRole("textbox", { name: "Research text" }).fill("");
  await view.getByRole("button", { name: "Remove measurements.csv" }).click();
  await expect(view.getByText("Draft changes not saved")).toBeVisible();
  const resetSave = page.waitForRequest(
    (request) =>
      request.url().endsWith("/v1/discovery/preparation/save") && request.method() === "POST",
  );
  await view.getByRole("button", { name: "Save Preparation" }).click();
  expect((await resetSave).postDataJSON()).toEqual({ text: "" });
  await expect(view.getByText("Preparation reset")).toBeVisible();

  expect(paths.filter((path) => /^\/api\/(workspace|admin)(\/|$)/.test(path))).toEqual([]);
});

test("Gather surfaces validation errors without partially accepting a file batch", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-discovery").click();

  const view = page.getByTestId("discovery-view");
  await expect(view.getByRole("heading", { name: "Gather context" })).toBeVisible();
  await view.getByLabel("Source files").setInputFiles([
    {
      name: "accepted.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("valid"),
    },
    {
      name: "unsupported.exe",
      mimeType: "application/octet-stream",
      buffer: Buffer.from("invalid"),
    },
  ]);

  await expect(view.getByRole("alert")).toContainText("unsupported source type");
  await expect(view.getByText("accepted.md")).toHaveCount(0);
  await expect(view.getByText("No files yet.")).toBeVisible();
});

test("Preparation follows the Stage Canvas flow with Reviewable input below Gather", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-discovery").click();

  const view = page.getByTestId("discovery-view");
  await view.getByRole("textbox", { name: "Research text" }).fill("Compare two constrained baselines.");
  await view.getByLabel("Source files").setInputFiles({
    name: "brief.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("baseline notes"),
  });

  const saveRequest = page.waitForRequest(
    (request) =>
      request.url().endsWith("/v1/discovery/preparation/save") && request.method() === "POST",
  );
  await view.getByRole("button", { name: "Save Preparation" }).click();
  await saveRequest;
  await expect(view.getByText("Preparation saved")).toBeVisible();

  const order = await view.evaluate((root) => {
    const gather = root.querySelector("#discovery-gather-heading")?.closest("section");
    const review = root.querySelector("#discovery-review-heading")?.closest("section");
    return Boolean(gather && review && (gather.compareDocumentPosition(review) & Node.DOCUMENT_POSITION_FOLLOWING));
  });
  expect(order).toBe(true);
  await expect(view.getByRole("button", { name: "Convert" })).toBeDisabled();
  await expect(view.getByLabel("Preparation stages").getByLabel("Completed")).toHaveCount(1);
});
