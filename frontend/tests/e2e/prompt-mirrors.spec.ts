import { expect, test, type Page } from "@playwright/test";

const englishText = "The runtime English prompt body.";
const chineseText = "这是已持久化的中文提示词镜像。";

function promptFixture(
  id: string,
  name: string,
  mirror: { state: "ready" | "missing" | "stale"; text: string | null },
) {
  return {
    id,
    name,
    description: "Prompt mirror browser fixture",
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
      ...mirror,
      file: `prompt_localizations/zh-CN/${id.replaceAll(".", "/")}.yaml`,
    },
  };
}

async function mockPromptMirrorRequests(page: Page) {
  const prompts = [
    promptFixture("test.ready", "Ready Chinese Prompt", { state: "ready", text: chineseText }),
    promptFixture("test.missing", "Missing Chinese Prompt", { state: "missing", text: null }),
    promptFixture("test.stale", "Stale Chinese Prompt", { state: "stale", text: null }),
  ];
  await page.route("**/api/admin/provider-connections", (route) =>
    route.fulfill({ json: { connections: [] } }),
  );
  await page.route("**/api/admin/prompt-translation-instruction", (route) =>
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
  await page.route("**/api/admin/prompts**", async (route) => {
    const promptId = route.request().url().split("/api/admin/prompts/")[1];
    if (route.request().method() === "PUT" && promptId) {
      const prompt = prompts.find((item) => item.id === promptId)!;
      prompt.text = (route.request().postDataJSON() as { text: string }).text;
      prompt.chinese_mirror = {
        ...prompt.chinese_mirror,
        state: "stale",
        text: null,
      };
      await route.fulfill({ json: prompt });
      return;
    }
    await route.fulfill({ json: { prompts } });
  });
}

test("switches each Prompt Card between English and its persistent Chinese mirror", async ({ page }) => {
  await mockPromptMirrorRequests(page);
  await page.goto("/");

  await page.getByRole("button", { name: "系统设置" }).click();
  await page.getByRole("navigation", { name: "系统设置分类" })
    .getByRole("button", { name: "Prompt 库" })
    .click();

  const readyLanguage = page.getByRole("group", { name: "Ready Chinese Prompt 语言" });
  await expect(readyLanguage.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
  await readyLanguage.getByRole("button", { name: "中文" }).click();
  const readyCard = page.getByRole("button", { name: "打开 Ready Chinese Prompt" });
  await expect(readyCard).toContainText(chineseText);
  await expect(readyCard).toContainText("中文镜像已就绪");
  await expect(readyCard).not.toContainText(englishText);

  await readyCard.click();
  const dialog = page.getByRole("dialog");
  const chineseEditor = dialog.getByRole("textbox");
  await expect(chineseEditor).toHaveValue(chineseText);
  await expect(chineseEditor).toHaveJSProperty("readOnly", true);
  await dialog.getByRole("button", { name: "关闭 Prompt 编辑器" }).click();

  const missingLanguage = page.getByRole("group", { name: "Missing Chinese Prompt 语言" });
  await missingLanguage.getByRole("button", { name: "中文" }).click();
  const missingCard = page.getByRole("button", { name: "打开 Missing Chinese Prompt" });
  await expect(missingCard).toContainText("中文镜像缺失，尚未生成。");
  await expect(missingCard).not.toContainText(englishText);

  const staleLanguage = page.getByRole("group", { name: "Stale Chinese Prompt 语言" });
  await staleLanguage.getByRole("button", { name: "中文" }).click();
  const staleCard = page.getByRole("button", { name: "打开 Stale Chinese Prompt" });
  await expect(staleCard).toContainText("中文镜像已过期，需要重新生成。");
  await expect(staleCard).not.toContainText(englishText);

  await readyLanguage.getByRole("button", { name: "English" }).click();
  await readyCard.click();
  const englishEditor = page.getByRole("dialog").getByRole("textbox");
  await englishEditor.fill("Updated runtime English prompt body.");
  await page.getByRole("button", { name: "保存 Prompt" }).click();
  await expect(readyCard).toContainText("中文镜像已过期");
});
