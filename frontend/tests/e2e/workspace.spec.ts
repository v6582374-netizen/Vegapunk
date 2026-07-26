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

type TranslationSettingsFixture = {
  instruction?: string;
  conversionInstruction?: string;
  defaultTextModelReady?: boolean;
};

async function mockSystemSettingsRequests(
  page: Page,
  { instruction = "", conversionInstruction = "", defaultTextModelReady = false }: TranslationSettingsFixture = {},
) {
  let savedInstruction = instruction;
  let savedPayload: { instruction: string } | null = null;
  let savedConversionInstruction = conversionInstruction;
  let savedConversionPayload: { instruction: string } | null = null;
  const textModel = "relay/test";
  await page.route("**/api/admin/provider-connections", (route) =>
    route.fulfill({ json: { connections: [] } }),
  );
  await page.route("**/api/admin/prompts", (route) =>
    route.fulfill({ json: { prompts: promptFixtures } }),
  );
  await page.route("**/api/admin/prompt-mirror-batches/availability", (route) =>
    route.fulfill({
      json: {
        available: false,
        reason: "请先配置 Prompt 翻译指令。",
        model_id: null,
      },
    }),
  );
  await page.route("**/api/admin/default-configuration", (route) =>
    route.fulfill({
      json: {
        revision: "test-revision",
        bindings: {
          active_text_model: textModel,
          image_model: "relay/test",
          embedding_model: "relay/test",
        },
        models: [{ id: textModel, provider: "relay", model: "test", capabilities: ["text"] }],
        parameter_catalog: [],
        parameters: {},
        readiness: {
          ready: defaultTextModelReady,
          connections: defaultTextModelReady
            ? [{
                provider: "relay",
                name: "Relay",
                base_url: "",
                base_url_configurable: false,
                credential_configured: true,
                credential_source: "vault",
                environment_variable: null,
                verification_status: "valid",
                model_count: 1,
              }]
            : [],
        },
      },
    }),
  );
  await page.route("**/api/admin/prompt-translation-instruction", async (route) => {
    if (route.request().method() === "PUT") {
      savedPayload = route.request().postDataJSON() as { instruction: string };
      if (!savedPayload.instruction.trim()) {
        await route.fulfill({
          status: 422,
          json: { detail: "Prompt Translation Instruction must not be empty" },
        });
        return;
      }
      savedInstruction = savedPayload.instruction;
    }
    await route.fulfill({
      json: { instruction: savedInstruction, configured: Boolean(savedInstruction.trim()) },
    });
  });
  await page.route("**/api/admin/discovery-input-conversion-prompt", async (route) => {
    if (route.request().method() === "PUT") {
      savedConversionPayload = route.request().postDataJSON() as { instruction: string };
      if (!savedConversionPayload.instruction.trim()) {
        await route.fulfill({
          status: 422,
          json: { detail: "Discovery Input Conversion Prompt must not be empty" },
        });
        return;
      }
      savedConversionInstruction = savedConversionPayload.instruction;
    }
    await route.fulfill({
      json: {
        instruction: savedConversionInstruction,
        configured: Boolean(savedConversionInstruction.trim()),
      },
    });
  });
  return {
    savedPayload: () => savedPayload,
    savedConversionPayload: () => savedConversionPayload,
  };
}

test("preserves the workspace controls while the substrate stays behind content", async ({ page }) => {
  await page.goto("/");

  const substrate = page.locator(".occluded-point-cloud");
  await expect(substrate).toHaveClass(/occluded-point-cloud--quiet/);
  await expect(substrate).not.toHaveClass(/is-responding/);
  await expect(substrate).toHaveCSS("pointer-events", "none");
  await expect(substrate).toHaveCSS("z-index", "0");
  await expect(page.locator(".paper-tools")).toHaveCSS("z-index", "1");

  const initialPointSignature = await substrate.locator("circle").evaluateAll((points) =>
    points.map((point) => point.outerHTML).join(""),
  );

  const moduleNavigation = page.getByRole("navigation", { name: "协作空间模块" });

  await moduleNavigation.getByRole("button", { name: "具身智能" }).click();
  await expect(substrate).toHaveClass(/occluded-point-cloud--quiet/);
  await expect(substrate).toHaveClass(/is-responding/);
  await expect(substrate.locator("circle").evaluateAll((points) =>
    points.map((point) => point.outerHTML).join(""),
  )).resolves.toBe(initialPointSignature);

  await moduleNavigation.getByRole("button", { name: "论文工具" }).click();
  await expect(page.getByRole("tablist", { name: "论文工具子模块" })).toBeVisible();
  await expect(page.locator("main").getByRole("heading", { name: "论文工具" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /先把位置留出来/ })).toHaveCount(0);
  const researchTopic = page.getByRole("searchbox", { name: "输入研究主题或搜索要求" });
  await expect(researchTopic).toBeVisible();
  await researchTopic.fill("反渗透膜污染缓解的最新证据");
  await expect(researchTopic).toHaveValue("反渗透膜污染缓解的最新证据");
  const highInterestPapers = page.getByRole("region", { name: "高热论文" });
  await expect(highInterestPapers).toContainText("100 篇已核验");
  const firstPaperLink = highInterestPapers.getByRole("link", {
    name: "Self-Driving Laboratories for Chemistry and Materials Science",
    exact: true,
  });
  await expect(firstPaperLink).toHaveAttribute("href", "https://doi.org/10.1021/acs.chemrev.4c00055");
  await expect(firstPaperLink).toHaveAttribute("target", "_blank");
  await highInterestPapers.getByRole("button", { name: "海水淡化" }).click();
  await expect(highInterestPapers).toContainText("20 篇已核验");
  await expect(highInterestPapers).toContainText("The Future of Seawater Desalination");
  await highInterestPapers.getByRole("navigation", { name: "海水淡化 论文分页" })
    .getByRole("button", { name: "下一页" })
    .click();
  await expect(highInterestPapers).toContainText("第 2 / 4 页");
  const doiLink = highInterestPapers.locator("a.paper-record-link").first();
  await expect(doiLink).toHaveAttribute("href", /^https:\/\/doi\.org\//);
  await expect(doiLink).toHaveAttribute("target", "_blank");
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

  const settingsSubnav = page.getByRole("group", { name: "系统设置子模块" });
  const defaultsTab = settingsSubnav.getByRole("button", { name: "默认参数" });
  await defaultsTab.click();
  await expect(defaultsTab).toHaveAttribute("aria-current", "page");
});

test("keeps System Settings submodules expanded and opens a selected submodule", async ({ page }) => {
  await mockSystemSettingsRequests(page);
  await page.goto("/");

  const moduleNavigation = page.getByRole("navigation", { name: "协作空间模块" });
  const settingsSubnav = moduleNavigation.getByRole("group", { name: "系统设置子模块" });
  await expect(settingsSubnav).toBeVisible();
  await expect(settingsSubnav.getByRole("button")).toHaveCount(5);

  const promptLibrary = settingsSubnav.getByRole("button", { name: "Prompt 库" });
  await promptLibrary.click();
  await expect(moduleNavigation.getByRole("button", { name: "系统设置" }))
    .toHaveAttribute("aria-current", "page");
  await expect(promptLibrary).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("region", { name: "系统设置" })).toBeVisible();
});

test("removes the substrate response when reduced motion is enabled", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");

  await page.getByRole("navigation", { name: "协作空间模块" })
    .getByRole("button", { name: "具身智能" })
    .click();
  const substrate = page.locator(".occluded-point-cloud");
  await expect(substrate).toHaveClass(/is-responding/);
  await expect(substrate).toHaveCSS("animation-name", "none");
});

test("contains prompt editor scrolling and removes the nested browser focus frame", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 650 });
  await mockSystemSettingsRequests(page);
  await page.goto("/");

  await page.getByRole("navigation", { name: "协作空间模块" })
    .getByRole("button", { name: "系统设置" })
    .click();
  await page.getByRole("group", { name: "系统设置子模块" })
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

test("keeps the workspace switcher visible at the bottom of the fixed sidebar", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 650 });
  await mockSystemSettingsRequests(page);
  await page.goto("/");

  await page.getByRole("button", { name: "系统设置" }).click();
  await page.getByRole("group", { name: "系统设置子模块" })
    .getByRole("button", { name: "Prompt 库" })
    .click();
  await expect.poll(() => page.evaluate(() => document.scrollingElement?.scrollHeight ?? 0))
    .toBeGreaterThan(650);

  const spaceSwitcher = page.getByRole("radiogroup", { name: "工作区空间" });
  await expect(spaceSwitcher).toBeInViewport();
  await page.evaluate(() => window.scrollTo(0, 400));
  await expect(spaceSwitcher).toBeInViewport();
  await expect(page.locator(".workspace-sidebar")).toHaveCSS("position", "sticky");
});

test("manages the independent Prompt Translation Instruction without model controls", async ({ page }) => {
  const settings = await mockSystemSettingsRequests(page, {
    instruction: "Translate the English source prompt into precise Chinese.",
    defaultTextModelReady: true,
  });
  await page.goto("/");

  await page.getByRole("navigation", { name: "协作空间模块" })
    .getByRole("button", { name: "系统设置" })
    .click();
  await page.getByRole("group", { name: "系统设置子模块" })
    .getByRole("button", { name: "翻译指令" })
    .click();

  await expect(page.getByRole("heading", { name: "Prompt 翻译指令" })).toBeVisible();
  await expect(page.getByText("relay/test 已验证", { exact: true })).toBeVisible();
  await expect(page.getByText("翻译操作可用")).toBeVisible();
  await expect(page.getByText("API Key", { exact: true })).toHaveCount(0);
  await expect(page.locator(".translation-instruction-editor select")).toHaveCount(0);

  const editor = page.getByRole("textbox", { name: "Prompt 翻译指令" });
  await editor.fill("Draft that should be discarded.");
  await page.getByRole("button", { name: "放弃修改" }).click();
  await expect(editor).toHaveValue("Translate the English source prompt into precise Chinese.");

  await editor.fill("Use terminology appropriate for AI scientists.");
  await page.getByRole("button", { name: "保存翻译指令" }).click();
  await expect(page.getByText("Prompt 翻译指令已保存")).toBeVisible();
  expect(settings.savedPayload()).toEqual({
    instruction: "Use terminology appropriate for AI scientists.",
  });

  await editor.fill("  \n");
  await page.getByRole("button", { name: "保存翻译指令" }).click();
  await expect(page.getByRole("alert")).toContainText("must not be empty");
});

test("explains why translation is unavailable when its prerequisites are missing", async ({ page }) => {
  await mockSystemSettingsRequests(page);
  await page.goto("/");

  await page.getByRole("navigation", { name: "协作空间模块" })
    .getByRole("button", { name: "系统设置" })
    .click();
  await page.getByRole("group", { name: "系统设置子模块" })
    .getByRole("button", { name: "翻译指令" })
    .click();

  await expect(page.getByText("尚未配置 Prompt 翻译指令")).toBeVisible();
  await expect(page.getByText("默认文本模型尚不可用")).toBeVisible();
});

test("maintains the independent Discovery Input Conversion Prompt outside the Prompt Library", async ({ page }) => {
  const settings = await mockSystemSettingsRequests(page, {
    conversionInstruction: "Transform any research material into a Discovery-ready input.",
  });
  await page.goto("/");

  await page.getByRole("navigation", { name: "协作空间模块" })
    .getByRole("button", { name: "系统设置" })
    .click();
  await page.getByRole("group", { name: "系统设置子模块" })
    .getByRole("button", { name: "转换指令" })
    .click();

  const field = page.getByRole("textbox", { name: "Discovery Input 转换指令" });
  await expect(field).toHaveValue("Transform any research material into a Discovery-ready input.");
  await expect(page.getByText("它不是 Prompt 库条目", { exact: false })).toBeVisible();

  await field.fill("Turn loose research notes into a structured Discovery input.");
  await page.getByRole("button", { name: "保存转换指令" }).click();
  await expect(page.getByText("Discovery Input 转换指令已保存")).toBeVisible();
  expect(settings.savedConversionPayload()).toEqual({
    instruction: "Turn loose research notes into a structured Discovery input.",
  });
});

test("switches between Space-specific module navigation without leaving the Unified Workspace", async ({ page }) => {
  await page.goto("/");

  const spaceSwitcher = page.getByRole("radiogroup", { name: "工作区空间" });
  const collaborationSpace = spaceSwitcher.getByRole("radio", { name: "协作空间" });
  const autonomousDiscoverySpace = spaceSwitcher.getByRole("radio", { name: "自主发现空间" });
  const collaborationModules = page.getByRole("navigation", { name: "协作空间模块" });

  await expect(collaborationSpace).toHaveAttribute("aria-checked", "true");
  await expect(collaborationModules.getByRole("button")).toHaveCount(9);
  await expect(collaborationModules.getByRole("button", { name: "论文工具" })).toBeVisible();
  await expect(collaborationModules.getByRole("button", { name: "具身智能" })).toBeVisible();
  await expect(collaborationModules.getByRole("button", { name: "Skill 管理" })).toBeVisible();
  await expect(collaborationModules.getByRole("button", { name: "系统设置" })).toBeVisible();
  await expect(collaborationModules.getByRole("button", { name: "论文工具" }))
    .toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("tablist", { name: "论文工具子模块" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /先把位置留出来/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "对话", exact: true })).toHaveCount(0);
  await expect(page.getByText("课题空间", { exact: true })).toHaveCount(0);
  await expect(page.getByText("INTRANET / 01", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /让长上下文推理的/ })).toHaveCount(0);

  await collaborationModules.getByRole("button", { name: "Skill 管理" }).click();
  await expect(collaborationModules.getByRole("button", { name: "Skill 管理" }))
    .toHaveAttribute("aria-current", "page");
  await expect(page.locator("main").getByText("Skill 管理", { exact: true })).toHaveCount(0);

  await autonomousDiscoverySpace.focus();
  await expect(autonomousDiscoverySpace).toBeFocused();
  await page.keyboard.press("Enter");
  const discoveryModules = page.getByRole("navigation", { name: "自主发现空间模块" });
  await expect(autonomousDiscoverySpace).toHaveAttribute("aria-checked", "true");
  await expect(discoveryModules.getByRole("button")).toHaveCount(2);
  await expect(discoveryModules.getByRole("button", { name: "Discovery Preparation" })).toBeVisible();
  await expect(discoveryModules.getByRole("button", { name: "Discovery Launch Archive" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Discovery 控制台" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Discovery 控制台" }))
    .toContainText("等待 Discovery Launch");
  await expect(page.getByRole("textbox", { name: "原始课题资料" })).toHaveCount(0);

  await discoveryModules.getByRole("button", { name: "Discovery Launch Archive" }).click();
  await expect(discoveryModules.getByRole("button", { name: "Discovery Launch Archive" }))
    .toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("region", { name: "Discovery Launch Archive" })).toBeVisible();

  await collaborationSpace.focus();
  await expect(collaborationSpace).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(collaborationSpace).toHaveAttribute("aria-checked", "true");
  await expect(collaborationModules.getByRole("button", { name: "Skill 管理" }))
    .toHaveAttribute("aria-current", "page");

  await autonomousDiscoverySpace.focus();
  await page.keyboard.press("Enter");
  await expect(discoveryModules.getByRole("button", { name: "Discovery Launch Archive" }))
    .toHaveAttribute("aria-current", "page");
});

test("creates a reusable Discovery Preparation and surfaces unsupported source errors", async ({ page }) => {
  const createdPreparation = {
    id: "prep-1",
    created_at: "2026-07-26T08:00:00+00:00",
    research_text: "What controls the material transition?",
    sources: [{ name: "observations.md", kind: "reference", extension: ".md" }],
    revisions: [],
  };
  let savedPreparations: typeof createdPreparation[] = [];

  await page.route("**/api/workspace/discovery-preparations", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: { preparations: savedPreparations } });
      return;
    }

    const requestBody = route.request().postDataBuffer()?.toString() ?? "";
    if (requestBody.includes("unsupported.exe")) {
      await route.fulfill({
        status: 422,
        json: { detail: "unsupported source type: unsupported.exe" },
      });
      return;
    }

    savedPreparations = [createdPreparation];
    await route.fulfill({ status: 201, json: createdPreparation });
  });

  await page.goto("/");
  await page.getByRole("radiogroup", { name: "工作区空间" })
    .getByRole("radio", { name: "自主发现空间" })
    .click();

  await expect(page.getByRole("region", { name: "Discovery 控制台" })).toBeVisible();
  await page.getByRole("button", { name: "新建资料" }).click();
  const creationDrawer = page.getByRole("dialog", { name: "新建 Preparation" });
  await creationDrawer.getByRole("textbox", { name: "原始课题资料" })
    .fill("What controls the material transition?");
  await creationDrawer.getByLabel("上传研究资料").setInputFiles({
    name: "observations.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Observations"),
  });
  await expect(creationDrawer.getByText("observations.md", { exact: true })).toBeVisible();

  await creationDrawer.getByRole("button", { name: "保存为新的 Preparation" }).click();
  await expect(page.getByText("Preparation 已保存")).toBeVisible();
  const savedPreparation = page.getByRole("button", { name: /What controls the material transition/ });
  await expect(savedPreparation).toBeVisible();
  await savedPreparation.click();
  const detailsDrawer = page.getByRole("dialog", { name: "已保存的研究资料" });
  await expect(detailsDrawer.getByText("observations.md", { exact: true })).toBeVisible();
  await detailsDrawer.getByRole("button", { name: "关闭 Preparation 详情" }).click();

  await page.getByRole("button", { name: "新建资料" }).click();
  await page.getByRole("dialog", { name: "新建 Preparation" }).getByLabel("上传研究资料").setInputFiles({
    name: "unsupported.exe",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("not a supported source"),
  });
  await page.getByRole("dialog", { name: "新建 Preparation" })
    .getByRole("button", { name: "保存为新的 Preparation" })
    .click();
  await expect(page.getByRole("dialog", { name: "新建 Preparation" }).getByRole("alert"))
    .toContainText("unsupported source type: unsupported.exe");
});

test("converts a Preparation into a right-side editable draft and saves only on request", async ({ page }) => {
  const preparation = {
    id: "prep-convert-1",
    created_at: "2026-07-26T08:00:00+00:00",
    research_text: "What controls the observed transition?",
    sources: [],
    revisions: [],
  };
  let savedRevision: { formatted_input: string } | null = null;

  await page.route("**/api/workspace/discovery-preparations", (route) =>
    route.fulfill({ json: { preparations: [preparation] } }),
  );
  await page.route(`**/api/workspace/discovery-preparations/${preparation.id}/conversion`, (route) =>
    route.fulfill({
      json: {
        preparation_id: preparation.id,
        formatted_input: "# Formatted Discovery Input\n\nInitial draft.",
        model_id: "relay/test",
      },
    }),
  );
  await page.route(`**/api/workspace/discovery-preparations/${preparation.id}/revisions`, (route) => {
    savedRevision = route.request().postDataJSON() as { formatted_input: string };
    return route.fulfill({
      status: 201,
      json: {
        id: "revision-1",
        created_at: "2026-07-26T08:05:00+00:00",
        formatted_input: savedRevision.formatted_input,
      },
    });
  });

  await page.goto("/");
  await page.getByRole("radiogroup", { name: "工作区空间" })
    .getByRole("radio", { name: "自主发现空间" })
    .click();
  await page.getByRole("button", { name: /What controls the observed transition/ }).click();
  await page.getByRole("dialog", { name: "已保存的研究资料" })
    .getByRole("button", { name: "转换为格式化输入" })
    .click();

  const editor = page.getByRole("dialog", { name: "转换草稿" });
  await expect(editor).toBeVisible();
  await expect(editor).toHaveCSS("position", "fixed");
  await expect(editor).toHaveCSS("right", "0px");
  const draft = editor.getByRole("textbox", { name: "Formatted Discovery Input" });
  await expect(draft).toHaveValue("# Formatted Discovery Input\n\nInitial draft.");
  await draft.fill("# Formatted Discovery Input\n\nEdited draft.");
  await editor.getByRole("button", { name: "保存为新的输入修订版" }).click();

  await expect(editor).toBeHidden();
  await expect(page.getByRole("dialog", { name: "已保存的研究资料" })).toBeVisible();
  await expect(page.getByText("已保存新的输入修订版")).toBeVisible();
  await expect(page.getByText("1 个输入修订版")).toBeVisible();
  expect(savedRevision).toEqual({ formatted_input: "# Formatted Discovery Input\n\nEdited draft." });
});

for (const viewport of desktopViewports) {
  test(`keeps the desktop composition within ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");

    const spaceSwitcher = page.getByRole("radiogroup", { name: "工作区空间" });
    const collaborationSpace = spaceSwitcher.getByRole("radio", { name: "协作空间" });
    const autonomousDiscoverySpace = spaceSwitcher.getByRole("radio", { name: "自主发现空间" });
    await expect(page.locator(".occluded-point-cloud")).toBeVisible();
    await autonomousDiscoverySpace.focus();
    await page.keyboard.press("Enter");
    const discoveryModules = page.getByRole("navigation", { name: "自主发现空间模块" });
    await discoveryModules.getByRole("button", { name: "Discovery Launch Archive" }).click();
    await collaborationSpace.focus();
    await page.keyboard.press("Enter");
    const collaborationModules = page.getByRole("navigation", { name: "协作空间模块" });
    await collaborationModules.getByRole("button", { name: "Skill 管理" }).click();
    await autonomousDiscoverySpace.focus();
    await page.keyboard.press("Enter");
    await expect(discoveryModules.getByRole("button", { name: "Discovery Launch Archive" }))
      .toHaveAttribute("aria-current", "page");
    await collaborationSpace.focus();
    await page.keyboard.press("Enter");
    await expect(collaborationModules.getByRole("button", { name: "Skill 管理" }))
      .toHaveAttribute("aria-current", "page");
    await expect(page.evaluate(() => document.documentElement.scrollWidth)).resolves.toBe(viewport.width);
  });
}

for (const width of mobileViewports) {
  test(`does not introduce horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");

    await page.getByRole("navigation", { name: "协作空间模块" })
      .getByRole("button", { name: "论文工具" })
      .click();
    const highInterestPapers = page.getByRole("region", { name: "高热论文" });
    await highInterestPapers.getByRole("button", { name: "海水淡化" }).click();
    await expect(highInterestPapers).toContainText("20 篇已核验");
    await expect(page.evaluate(() => document.documentElement.scrollWidth)).resolves.toBe(width);
  });
}
