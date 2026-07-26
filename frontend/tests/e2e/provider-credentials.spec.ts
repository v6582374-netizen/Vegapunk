import { expect, test } from "@playwright/test";

const relayConnection = {
  provider: "relay" as const,
  name: "Relay",
  base_url: "https://relay.example/v1",
  base_url_configurable: true,
  credential_configured: true,
  credential_source: "vault" as const,
  environment_variable: "OPENAI_API_KEY",
  verification_status: "unverified" as const,
  model_count: 1,
};

test("keeps configured API keys masked until the user explicitly reveals them", async ({ page }) => {
  let revealCalls = 0;
  let savedPayload: { api_key?: string; base_url?: string } | null = null;

  await page.route("**/api/admin/provider-connections/relay/credential/reveal", (route) => {
    revealCalls += 1;
    return route.fulfill({ json: { api_key: "stored-for-test" } });
  });
  await page.route("**/api/admin/provider-connections/relay", (route) => {
    savedPayload = route.request().postDataJSON() as { api_key?: string; base_url?: string };
    return route.fulfill({ json: relayConnection });
  });
  await page.route("**/api/admin/provider-connections", (route) =>
    route.fulfill({ json: { connections: [relayConnection] } }),
  );
  await page.route("**/api/admin/prompts", (route) => route.fulfill({ json: { prompts: [] } }));
  await page.route("**/api/admin/prompt-mirror-batches/availability", (route) =>
    route.fulfill({ json: { available: false, reason: null, model_id: null } }),
  );
  await page.route("**/api/admin/prompt-translation-instruction", (route) =>
    route.fulfill({ json: { instruction: "", configured: false } }),
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

  await page.goto("/");
  await page.getByRole("button", { name: "系统设置" }).click();

  const apiKey = page.getByRole("textbox", { name: /API Key 系统凭据库/ });
  await expect(apiKey).toHaveValue("******");
  await expect(apiKey).toHaveAttribute("type", "password");
  expect(revealCalls).toBe(0);

  await page.getByRole("button", { name: "显示 Relay API Key" }).click();
  await expect.poll(() => revealCalls).toBe(1);
  await expect(apiKey).toHaveValue("stored-for-test");
  await expect(apiKey).toHaveAttribute("type", "text");

  await page.getByRole("button", { name: "隐藏 Relay API Key" }).click();
  await expect(apiKey).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "显示 Relay API Key" }).click();
  expect(revealCalls).toBe(1);

  await apiKey.fill("replacement-for-test");
  await page.getByRole("button", { name: "保存" }).click();
  await expect.poll(() => savedPayload).toEqual({
    api_key: "replacement-for-test",
    base_url: relayConnection.base_url,
  });
  await expect(apiKey).toHaveValue("******");
});
