import { expect, test } from "@playwright/test";

const launchId = "Discovery/20260727_101500_launch";

test("shows the selected Launch wheel, raw console, and contextual artifact actions", async ({ page }) => {
  await page.route("**/api/workspace/discovery-preparations", (route) => route.fulfill({
    json: {
      preparations: [{
        id: "prep-1",
        created_at: "2026-07-27T10:00:00Z",
        research_text: "Investigate a transition mechanism in catalytic membranes",
        sources: [{ name: "notes.md", kind: "reference", extension: ".md" }],
        revisions: [{
          id: "rev-1",
          created_at: "2026-07-27T10:15:00Z",
          formatted_input: "Study the transition mechanism.",
        }],
      }],
    },
  }));
  await page.route("**/api/workspace/discovery-launches", (route) => route.fulfill({
    json: {
      launches: [{
        id: launchId,
        task: "Discovery",
        started_at: "2026-07-27T10:15:00",
        state: "running",
      }],
    },
  }));
  await page.route(`**/api/workspace/discovery-launches/${launchId}/status`, (route) => route.fulfill({
    json: {
      state: "running",
      stage: "discovery",
      rounds: 2,
      total_rounds: 4,
      stopped_how: null,
      recent_artifacts: [],
    },
  }));
  await page.route(`**/api/workspace/discovery-launches/${launchId}/artifacts/tree`, (route) => route.fulfill({
    json: {
      tree: [{
        path: "round_02",
        name: "round_02",
        kind: "directory",
        children: [
          { path: "round_02/idea-ledger.md", name: "idea-ledger.md", kind: "file", size: 100 },
          { path: "round_02/paper.pdf", name: "paper.pdf", kind: "file", size: 100 },
        ],
      }],
    },
  }));
  await page.route(`**/api/workspace/discovery-launches/${launchId}/logs/stream*`, (route) => route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body: "data: Loaded immutable input snapshot revision 7\n\ndata: Discovery Round 2 started\n\n",
  }));
  await page.route(`**/api/workspace/discovery-launches/${launchId}/artifacts/file*`, (route) => route.fulfill({
    status: 200,
    contentType: "text/markdown",
    body: "# Idea ledger\n\nA human-readable persisted artifact.",
  }));

  await page.goto("/");
  await page.getByRole("radio", { name: "自主发现空间" }).click();

  await expect(page.getByRole("region", { name: "Discovery Launch Archive" })).toContainText("Autonomous Discovery");
  await expect(page.getByRole("region", { name: "Discovery 控制台" })).toContainText("Raw Discovery Console");
  await expect(page.getByRole("region", { name: "Discovery 控制台" })).toContainText("Discovery Round 2 started");
  await expect(page.locator(".discovery-wheel-stage.is-focused")).toContainText("Discovery Round");

  await page.locator(".discovery-wheel-stages").press("ArrowRight");
  await expect(page.locator(".discovery-wheel-stage.is-focused")).toContainText("论文交接");
  await page.getByRole("button", { name: "回到当前状态" }).click();
  await expect(page.locator(".discovery-wheel-stage.is-focused")).toContainText("Discovery Round");

  await page.getByRole("button", { name: /idea-ledger\.md/ }).click();
  await expect(page.getByRole("complementary", { name: "Artifact Preview" })).toContainText("A human-readable persisted artifact.");

  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("button", { name: /paper\.pdf/ }).click();
  const popup = await popupPromise;
  await expect(popup).toHaveURL(new RegExp("/api/workspace/discovery-launches/Discovery/20260727_101500_launch/artifacts/file"));
  await popup.close();
});
