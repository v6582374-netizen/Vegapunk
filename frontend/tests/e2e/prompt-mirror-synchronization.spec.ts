import { expect, test, type Page } from "@playwright/test";

const englishText = "The runtime English prompt body.";
const chineseText = "这是已持久化的中文提示词镜像。";
const updatedChineseText = "这是经人工修改后需要同步的中文提示词。";
const updatedEnglishText = "The synchronized runtime English prompt body.";

function promptFixture() {
  return {
    id: "test.ready",
    name: "Synchronizable Chinese Prompt",
    description: "Prompt synchronization browser fixture",
    workflow: "deep_research",
    stage: "planning",
    order: 1,
    invocation_type: "single" as const,
    mutual_exclusion_group: null,
    template_variables: [],
    required_template_variables: [],
    file: "deep_research/test.txt",
    text: englishText,
    source_revision: "english-revision-1",
    chinese_mirror: {
      state: "ready" as const,
      file: "prompt_localizations/zh-CN/test/ready.yaml",
      text: chineseText,
    },
  };
}

async function mockPromptSynchronizationRequests(
  page: Page,
  response: "success" | "conflict" = "success",
) {
  const prompt = promptFixture();
  const synchronizationPayloads: unknown[] = [];
  await page.route("**/api/admin/provider-connections", (route) =>
    route.fulfill({ json: { connections: [] } }),
  );
  await page.route("**/api/admin/prompt-translation-instruction", (route) =>
    route.fulfill({ json: { instruction: "Translate faithfully.", configured: true } }),
  );
  await page.route("**/api/admin/discovery-input-conversion-prompt", (route) =>
    route.fulfill({ json: { instruction: "", configured: false } }),
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
  await page.route("**/api/admin/prompt-mirror-batches/availability", (route) =>
    route.fulfill({ json: { available: true, reason: null, model_id: "relay/test" } }),
  );
  await page.route("**/api/admin/prompts", (route) =>
    route.fulfill({ json: { prompts: [prompt] } }),
  );
  await page.route("**/api/admin/prompts/test.ready/synchronize", async (route) => {
    synchronizationPayloads.push(route.request().postDataJSON());
    if (response === "conflict") {
      await route.fulfill({
        status: 409,
        json: { detail: "英文 Prompt 已被其他修改更新，请重新打开后再同步。" },
      });
      return;
    }
    prompt.text = updatedEnglishText;
    prompt.source_revision = "english-revision-2";
    prompt.chinese_mirror = { ...prompt.chinese_mirror, text: updatedChineseText };
    await route.fulfill({ json: prompt });
  });
  return { prompt, synchronizationPayloads };
}

async function openChinesePrompt(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "系统设置" }).click();
  await page.getByRole("group", { name: "系统设置子模块" })
    .getByRole("button", { name: "Prompt 库" })
    .click();
  await page.getByRole("group", { name: "Synchronizable Chinese Prompt 语言" })
    .getByRole("button", { name: "中文" })
    .click();
  await page.getByRole("button", { name: "打开 Synchronizable Chinese Prompt" }).click();
}

test("synchronizes an edited Chinese draft and discards an unsynchronized draft on close", async ({ page }) => {
  const mock = await mockPromptSynchronizationRequests(page);
  await openChinesePrompt(page);

  const dialog = page.getByRole("dialog");
  const editor = dialog.getByRole("textbox");
  const synchronize = dialog.getByRole("button", { name: "同步到英文版本" });
  await expect(editor).toHaveValue(chineseText);
  await expect(synchronize).toBeDisabled();

  await editor.fill("仅用于验证撤销的草稿。");
  await dialog.getByRole("button", { name: "撤销修改" }).click();
  await expect(editor).toHaveValue(chineseText);
  await expect(synchronize).toBeDisabled();

  await editor.fill("仅用于验证关闭后丢弃的草稿。");
  await dialog.getByRole("button", { name: "关闭 Prompt 编辑器" }).click();
  await page.getByRole("button", { name: "打开 Synchronizable Chinese Prompt" }).click();
  await expect(page.getByRole("dialog").getByRole("textbox")).toHaveValue(chineseText);

  await page.getByRole("dialog").getByRole("textbox").fill("仅用于验证 Escape 后丢弃的草稿。");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "打开 Synchronizable Chinese Prompt" }).click();
  await expect(page.getByRole("dialog").getByRole("textbox")).toHaveValue(chineseText);

  await page.getByRole("dialog").getByRole("textbox").fill("仅用于验证遮罩后丢弃的草稿。");
  await page.locator(".prompt-dialog-backdrop").click({ position: { x: 1, y: 1 } });
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "打开 Synchronizable Chinese Prompt" }).click();
  await expect(page.getByRole("dialog").getByRole("textbox")).toHaveValue(chineseText);

  await page.getByRole("dialog").getByRole("textbox").fill(updatedChineseText);
  await page.getByRole("dialog").getByRole("button", { name: "同步到英文版本" }).click();

  await expect.poll(() => mock.synchronizationPayloads).toEqual([
    { chinese_text: updatedChineseText, source_revision: "english-revision-1" },
  ]);
  await expect(page.getByRole("dialog").getByRole("textbox")).toHaveValue(updatedChineseText);
  await expect(page.getByRole("button", { name: "打开 Synchronizable Chinese Prompt" }))
    .toContainText(updatedChineseText);
  await expect(page.getByRole("dialog").getByRole("status"))
    .toContainText("已同步到英文版本");
});

test("retains an edited Chinese draft when synchronization reports an English conflict", async ({ page }) => {
  await mockPromptSynchronizationRequests(page, "conflict");
  await openChinesePrompt(page);

  const dialog = page.getByRole("dialog");
  const editor = dialog.getByRole("textbox");
  await editor.fill(updatedChineseText);
  await dialog.getByRole("button", { name: "同步到英文版本" }).click();

  await expect(dialog.getByRole("alert")).toContainText("英文 Prompt 已被其他修改更新");
  await expect(editor).toHaveValue(updatedChineseText);
});
