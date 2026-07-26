import { expect, test, type Page } from "@playwright/test";

const desktopViewports = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
];

const mobileViewports = [320, 375, 414, 768];

const longPromptText = Array.from(
  { length: 40 },
  (_, index) => `Prompt editor regression coverage line ${index + 1}.`,
).join("\n");

const promptFixtures = Array.from({ length: 43 }, (_, index) => ({
  id: `test.long_prompt_${index + 1}`,
  name: index === 0 ? "Long Prompt Editor" : `Prompt Fixture ${index + 1}`,
  description: "Prompt Library browser fixture",
  workflow: "deep_research",
  stage: "planning",
  order: index + 1,
  invocation_type: "single" as const,
  mutual_exclusion_group: null,
  template_variables: [],
  required_template_variables: [],
  file: `config/prompts/test-${index + 1}.txt`,
  text: longPromptText,
}));

async function mockSystemSettingsRequests(page: Page) {
  await page.route("**/api/admin/provider-connections", (route) =>
    route.fulfill({ json: { connections: [] } }),
  );
  await page.route("**/api/admin/prompts", (route) =>
    route.fulfill({ json: { prompts: promptFixtures } }),
  );
  await page.route("**/api/admin/default-configuration", (route) =>
    route.fulfill({
      json: {
        revision: "test-revision",
        bindings: {
          active_text_model: "relay/test",
          image_model: "relay/test",
          embedding_model: "relay/test",
        },
        models: [],
        parameter_catalog: [],
        parameters: {},
        readiness: { ready: false, connections: [] },
      },
    }),
  );
}

test("preserves the workspace controls while the substrate stays behind content", async ({ page }) => {
  await page.goto("/");

  const substrate = page.locator(".occluded-point-cloud");
  await expect(substrate).toHaveClass(/occluded-point-cloud--exhibition/);
  await expect(substrate).not.toHaveClass(/is-responding/);
  await expect(substrate).toHaveCSS("pointer-events", "none");
  await expect(substrate).toHaveCSS("z-index", "0");
  await expect(page.locator(".workspace-header")).toHaveCSS("z-index", "1");

  const initialPointSignature = await substrate.locator("circle").evaluateAll((points) =>
    points.map((point) => point.outerHTML).join(""),
  );

  const moduleNavigation = page.getByRole("navigation", { name: "工作区模块" });

  await moduleNavigation.getByRole("button", { name: "论文工具" }).click();
  await expect(page.getByRole("heading", { name: /论文工作台/ })).toBeVisible();
  await expect(substrate).toHaveClass(/occluded-point-cloud--quiet/);
  await expect(substrate).toHaveClass(/is-responding/);
  await expect(substrate.locator("circle").evaluateAll((points) =>
    points.map((point) => point.outerHTML).join(""),
  )).resolves.toBe(initialPointSignature);

  await page.getByRole("tab", { name: "引文核验" }).click();
  await expect(page.getByRole("tabpanel")).toContainText("引文核验即将开放");

  await moduleNavigation.getByRole("button", { name: "具身智能" }).click();
  await page.getByRole("button", { name: /查看高位总览/ }).click();
  await expect(page.getByRole("heading", { name: "高位总览" })).toBeVisible();

  const moduleButton = moduleNavigation.getByRole("button", { name: "系统设置" });
  await moduleButton.focus();
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  await expect(moduleButton).toBeFocused();
  await expect(moduleButton).toHaveCSS("outline-style", "solid");
  await expect(moduleButton).toHaveCSS("outline-width", "3px");
  await expect(moduleButton).toHaveCSS("outline-offset", "4px");

  await moduleButton.click();
  await expect(substrate).toHaveClass(/occluded-point-cloud--none/);
  await expect(substrate).toHaveCSS("display", "none");

  const settingsTabs = page.getByRole("navigation", { name: "系统设置分类" });
  const defaultsTab = settingsTabs.getByRole("button", { name: "默认参数" });
  await defaultsTab.click();
  await expect(defaultsTab).toHaveAttribute("aria-current", "page");
});

test("removes the substrate response when reduced motion is enabled", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");

  await page.getByRole("navigation", { name: "工作区模块" })
    .getByRole("button", { name: "论文工具" })
    .click();
  const substrate = page.locator(".occluded-point-cloud");
  await expect(substrate).toHaveClass(/is-responding/);
  await expect(substrate).toHaveCSS("animation-name", "none");
});

test("contains prompt editor scrolling and removes the nested browser focus frame", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 650 });
  await mockSystemSettingsRequests(page);
  await page.goto("/");

  await page.getByRole("navigation", { name: "工作区模块" })
    .getByRole("button", { name: "系统设置" })
    .click();
  await page.getByRole("navigation", { name: "系统设置分类" })
    .getByRole("button", { name: "Prompt 库" })
    .click();
  await expect.poll(() => page.evaluate(() => document.scrollingElement?.scrollHeight ?? 0))
    .toBeGreaterThan(650);

  await page.getByRole("button", { name: /Long Prompt Editor/ }).click();
  const dialog = page.getByRole("dialog");
  const editor = dialog.getByRole("textbox");
  await expect(editor).toBeFocused();

  await editor.hover();
  await editor.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect.poll(() => editor.evaluate((element) => element.scrollTop)).toBe(
    await editor.evaluate((element) => element.scrollHeight - element.clientHeight),
  );
  const pageScrollBeforeOverscroll = await page.evaluate(
    () => document.scrollingElement?.scrollTop ?? 0,
  );

  await page.mouse.wheel(0, 1_000);
  await expect.poll(() => page.evaluate(() => document.scrollingElement?.scrollTop ?? 0))
    .toBe(pageScrollBeforeOverscroll);
  await expect(editor).toHaveCSS("outline-style", "none");

  await dialog.getByRole("button", { name: "关闭 Prompt 编辑器" }).click();
  await expect(dialog).not.toBeVisible();
  await page.mouse.wheel(0, 1_000);
  await expect.poll(() => page.evaluate(() => document.scrollingElement?.scrollTop ?? 0))
    .toBeGreaterThan(pageScrollBeforeOverscroll);
});

for (const viewport of desktopViewports) {
  test(`keeps the desktop composition within ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");

    await expect(page.locator(".occluded-point-cloud")).toBeVisible();
    await expect(page.evaluate(() => document.documentElement.scrollWidth)).resolves.toBe(viewport.width);
  });
}

for (const width of mobileViewports) {
  test(`does not introduce horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");

    await expect(page.evaluate(() => document.documentElement.scrollWidth)).resolves.toBe(width);
  });
}
