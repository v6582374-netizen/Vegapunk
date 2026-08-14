// Document Translation ▸ provider reuse. The behaviour under test is the contract between this
// settings surface and Settings ▸ Models: the Provider dropdown offers exactly the providers the
// user already configured AND that BabelDOC can actually drive (the OpenAI-compatible ones), and
// the chosen name is what gets saved — no key ever travels through this form.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TranslationSettingsSection, usableProviders } from "./TranslationSettingsSection";
import type { ProviderInfo, TranslationSettingsValues } from "../api";

const mocks = vi.hoisted(() => ({
  getProviders: vi.fn(),
  getTranslationSettings: vi.fn(),
  setTranslationSettings: vi.fn(),
}));

vi.mock("../api", () => ({
  getProviders: mocks.getProviders,
  getTranslationSettings: mocks.getTranslationSettings,
  setTranslationSettings: mocks.setTranslationSettings,
}));

const { getProviders, getTranslationSettings, setTranslationSettings } = mocks;

const DEFAULTS = {
  provider: "",
  lang_in: "en",
  lang_out: "zh",
  openai_model: "gpt-4o-mini",
  openai_base_url: "",
  qps: 4,
  pool_max_workers: 0,
  ignore_cache: false,
  pages: "",
  primary_font_family: "auto",
  watermark_output_mode: "watermarked",
  custom_system_prompt: "",
} as unknown as TranslationSettingsValues;

const provider = (over: Partial<ProviderInfo>): ProviderInfo =>
  ({
    name: "x",
    title: "X",
    needs_key: true,
    fields: [],
    configured: true,
    values: {},
    suggested_models: [],
    recommended_model: null,
    openai_compatible: true,
    ...over,
  }) as ProviderInfo;

const doc = (values: Partial<TranslationSettingsValues> = {}) => ({
  schema_version: 1,
  values: { ...DEFAULTS, ...values },
  defaults: DEFAULTS,
  parameters: {},
});

const dropdown = () => screen.getByLabelText("Provider") as HTMLSelectElement;

beforeEach(() => {
  vi.clearAllMocks();
  getTranslationSettings.mockResolvedValue(doc());
  getProviders.mockResolvedValue([
    provider({ name: "openai", title: "OpenAI" }),
    provider({ name: "deepseek", title: "DeepSeek" }),
  ]);
});

afterEach(cleanup);

describe("usableProviders", () => {
  it("keeps only providers that are configured AND OpenAI-compatible", () => {
    const list = usableProviders([
      provider({ name: "openai", title: "OpenAI" }),
      provider({ name: "deepseek", title: "DeepSeek", configured: false }),
      provider({ name: "anthropic", title: "Claude (Anthropic)", openai_compatible: false }),
      provider({ name: "ollama", title: "Ollama (local models)", needs_key: false }),
    ]);

    expect(list).toEqual([
      { name: "openai", title: "OpenAI" },
      { name: "ollama", title: "Ollama (local models)" },
    ]);
  });

  it("treats a sidecar that does not report compatibility as not offerable", () => {
    const legacy = provider({ name: "openai", title: "OpenAI" });
    delete (legacy as { openai_compatible?: boolean }).openai_compatible;

    expect(usableProviders([legacy])).toEqual([]);
  });
});

describe("Provider field", () => {
  it("offers the configured providers plus the default OpenAI slot", async () => {
    render(<TranslationSettingsSection />);

    const options = await waitFor(() => Array.from(dropdown().options).map((o) => o.value));
    expect(options).toEqual(["", "openai", "deepseek"]);
    expect(dropdown().value).toBe("");
  });

  it("saves the chosen provider by name, and never a credential", async () => {
    setTranslationSettings.mockImplementation((values: Partial<TranslationSettingsValues>) =>
      Promise.resolve(doc(values)),
    );
    render(<TranslationSettingsSection />);
    await waitFor(() => dropdown());

    fireEvent.change(dropdown(), { target: { value: "deepseek" } });
    fireEvent.click(await screen.findByRole("button", { name: /Save 1 change/ }));

    await waitFor(() => expect(setTranslationSettings).toHaveBeenCalled());
    const sent = setTranslationSettings.mock.calls[0][0] as Record<string, unknown>;
    expect(sent.provider).toBe("deepseek");
    expect(Object.keys(sent)).not.toContain("api_key");
  });

  it("keeps a stored provider visible after its key is removed", async () => {
    getTranslationSettings.mockResolvedValue(doc({ provider: "kimi" }));
    getProviders.mockResolvedValue([provider({ name: "openai", title: "OpenAI" })]);
    render(<TranslationSettingsSection />);

    await waitFor(() => expect(dropdown().value).toBe("kimi"));
    expect(screen.getByRole("option", { name: /kimi \(not configured\)/ })).toBeTruthy();
  });

  it("still renders the form when the provider list cannot be fetched", async () => {
    getProviders.mockRejectedValue(new Error("sidecar down"));
    render(<TranslationSettingsSection />);

    const options = await waitFor(() => Array.from(dropdown().options).map((o) => o.value));
    expect(options).toEqual([""]);
    expect(screen.getByLabelText("Target language")).toBeTruthy();
  });
});
