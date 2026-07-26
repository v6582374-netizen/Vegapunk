import { expect, test } from "@playwright/test";

const desktopViewports = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
];

const mobileViewports = [320, 375, 414, 768];

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
