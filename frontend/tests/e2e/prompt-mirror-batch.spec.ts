import { expect, test, type Page } from "@playwright/test";

const englishText = "The runtime English prompt body.";
const chineseText = "这是由批量翻译持久化的中文提示词镜像。";

function promptFixture() {
  return {
    id: "test.missing",
    name: "Missing Chinese Prompt",
    description: "Prompt mirror batch browser fixture",
    workflow: "deep_research",
    stage: "planning",
    order: 1,
    invocation_type: "single" as const,
    mutual_exclusion_group: null,
    template_variables: [],
    required_template_variables: [],
    file: "deep_research/test.txt",
    text: englishText,
    chinese_mirror: {
      state: "missing" as const,
      file: "prompt_localizations/zh-CN/test/missing.yaml",
      text: null,
    },
  };
}

async function mockPromptMirrorBatchRequests(page: Page) {
  const prompt = promptFixture();
  const failedBatch = {
    id: "batch-failed",
    state: "completed" as const,
    items: [{
      prompt_id: prompt.id,
      name: prompt.name,
      state: "failure" as const,
      error: "deterministic model outage",
    }],
    progress: { total: 1, pending: 0, success: 0, failure: 1, skipped: 0 },
  };
  const recoveredBatch = {
    id: "batch-recovered",
    state: "completed" as const,
    items: [{
      prompt_id: prompt.id,
      name: prompt.name,
      state: "success" as const,
      error: null,
    }],
    progress: { total: 1, pending: 0, success: 1, failure: 0, skipped: 0 },
  };
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
        readiness: { ready: true, connections: [] },
      },
    }),
  );
  await page.route("**/api/admin/prompt-mirror-batches/availability", (route) =>
    route.fulfill({ json: { available: true, reason: null, model_id: "relay/test" } }),
  );
  await page.route("**/api/admin/prompt-mirror-batches/batch-failed/retry", (route) => {
    prompt.chinese_mirror = {
      ...prompt.chinese_mirror,
      state: "ready",
      text: chineseText,
    };
    return route.fulfill({ status: 201, json: recoveredBatch });
  });
  await page.route("**/api/admin/prompt-mirror-batches", (route) =>
    route.fulfill({ status: 201, json: failedBatch }),
  );
  await page.route("**/api/admin/prompts", (route) =>
    route.fulfill({ json: { prompts: [prompt] } }),
  );
}

test("starts an explicit mirror batch and retries only its failed item", async ({ page }) => {
  await mockPromptMirrorBatchRequests(page);
  await page.goto("/");

  await page.getByRole("button", { name: "系统设置" }).click();
  await page.getByRole("navigation", { name: "系统设置分类" })
    .getByRole("button", { name: "Prompt 库" })
    .click();

  await expect(page.getByRole("heading", { name: "批量生成中文镜像" })).toBeVisible();
  await expect(page.getByRole("button", { name: "生成中文镜像" })).toBeEnabled();
  await page.getByRole("button", { name: "生成中文镜像" }).click();
  await expect(page.getByText("deterministic model outage")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试失败项" })).toBeEnabled();

  await page.getByRole("button", { name: "重试失败项" }).click();
  await expect(page.getByText("已生成", { exact: true })).toBeVisible();
  const language = page.getByRole("group", { name: "Missing Chinese Prompt 语言" });
  await language.getByRole("button", { name: "中文" }).click();
  await expect(page.getByRole("button", { name: "打开 Missing Chinese Prompt" })).toContainText(chineseText);
});
