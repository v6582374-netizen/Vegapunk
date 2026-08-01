import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { DiscoveryView } from "./DiscoveryView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("renders one empty Discovery shell with internal lifecycle navigation", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      module: "discovery",
      schema_version: 1,
      contexts: [
        { id: "preparation", label: "Preparation", description: "Prepare inputs." },
        { id: "launch", label: "Current Launch", description: "Observe a launch." },
        { id: "history", label: "History", description: "Review history." },
      ],
      active_context: "preparation",
      preparation: { status: "empty" },
      current_launch: null,
      history: [],
    }),
  })));

  render(<DiscoveryView />);

  expect(await screen.findByRole("heading", { name: "Gather context" })).toBeTruthy();
  expect(screen.getByText(/Empty Preparation/)).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Discovery" })).toBeTruthy();
  const preparationTab = screen.getByRole("tab", { name: "Preparation" });
  expect(preparationTab.getAttribute("aria-selected")).toBe("true");
  expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe(preparationTab.id);

  fireEvent.click(screen.getByRole("tab", { name: "History" }));
  expect(screen.getByRole("tab", { name: "History" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByRole("heading", { name: "No Launch history yet" })).toBeTruthy();
});

it("does not present an empty Preparation when the sidecar is unavailable", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: false,
    status: 401,
    json: async () => ({ error: "missing token" }),
  })));

  render(<DiscoveryView />);

  expect(await screen.findByRole("heading", { name: "Discovery is unavailable" })).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Your first Preparation is empty" })).toBeNull();
});

it("accepts text and files into a draft and saves the whole Preparation explicitly", async () => {
  const source = {
    source_id: "source-1",
    filename: "notes.md",
    extension: ".md",
    size: 5,
    sha256: "hash-1",
  };
  const base = {
    module: "discovery",
    schema_version: 1,
    contexts: [
      { id: "preparation", label: "Preparation", description: "Prepare inputs." },
      { id: "launch", label: "Current Launch", description: "Observe a launch." },
      { id: "history", label: "History", description: "Review history." },
    ],
    active_context: "preparation",
    current_launch: null,
    history: [],
  } as const;
  const empty = {
    ...base,
    preparation: {
      status: "empty",
      dirty: false,
      draft: { text: "", sources: [] },
      saved: { text: "", sources: [] },
    },
  };
  const draft = {
    ...base,
    preparation: {
      status: "draft",
      dirty: true,
      draft: { text: "Research salinity.", sources: [source] },
      saved: { text: "", sources: [] },
    },
  };
  const saved = {
    ...base,
    preparation: {
      status: "saved",
      dirty: false,
      draft: { text: "Research salinity.", sources: [source] },
      saved: { text: "Research salinity.", sources: [source] },
    },
  };
  const request = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/v1/discovery/preparation/intake")) {
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body)).text).toBe("Research salinity.");
      return { ok: true, status: 200, json: async () => draft } as Response;
    }
    if (url.endsWith("/v1/discovery/preparation/save")) {
      expect(JSON.parse(String(init?.body))).toEqual({ text: "Research salinity." });
      return { ok: true, status: 200, json: async () => saved } as Response;
    }
    return { ok: true, status: 200, json: async () => empty } as Response;
  });
  vi.stubGlobal("fetch", request);

  render(<DiscoveryView />);
  expect(await screen.findByRole("heading", { name: "Gather context" })).toBeTruthy();

  fireEvent.change(screen.getByRole("textbox", { name: "Research text" }), {
    target: { value: "Research salinity." },
  });
  const file = new File(["hello"], "notes.md", { type: "text/markdown" });
  fireEvent.change(screen.getByLabelText("Source files"), { target: { files: [file] } });

  expect(await screen.findByText("notes.md")).toBeTruthy();
  expect(screen.getByText("Draft changes not saved")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Convert" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Save Preparation" }));

  await waitFor(() => expect(screen.getAllByText("Preparation saved").length).toBeGreaterThan(0));
  expect((screen.getByRole("button", { name: "Convert" }) as HTMLButtonElement).disabled).toBe(false);
  expect(request).toHaveBeenCalled();
});

it("converts a saved Preparation, edits the formatted draft, and appends immutable revisions", async () => {
  const base = {
    module: "discovery" as const,
    schema_version: 1,
    contexts: [
      { id: "preparation" as const, label: "Preparation", description: "Prepare inputs." },
      { id: "launch" as const, label: "Current Launch", description: "Observe a launch." },
      { id: "history" as const, label: "History", description: "Review history." },
    ],
    active_context: "preparation" as const,
    current_launch: null,
    history: [],
  };
  const source = {
    source_id: "source-1",
    filename: "brief.md",
    extension: ".md",
    size: 5,
    sha256: "hash-1",
  };
  const pending = {
    ...base,
    preparation: {
      status: "saved" as const,
      dirty: false,
      draft: { text: "Research salinity.", sources: [source] },
      saved: { text: "Research salinity.", sources: [source] },
      revisions: [],
      conversion: {
        status: "pending" as const,
        draft: "",
        model_id: null,
        error: null,
        saved_revision_id: null,
        base_fingerprint: null,
        current_fingerprint: "fingerprint-1",
      },
    },
  };
  const editing = {
    ...pending,
    preparation: {
      ...pending.preparation,
      conversion: {
        ...pending.preparation.conversion,
        status: "editing" as const,
        draft: "# Converted input",
        model_id: "gpt-test",
        base_fingerprint: "fingerprint-1",
      },
    },
  };
  const saved = {
    ...editing,
    preparation: {
      ...editing.preparation,
      revisions: [
        {
          revision_id: "revision-1",
          created_at: "2026-08-01T00:00:00.000Z",
          formatted_input: "# Reviewed input",
          model_id: "gpt-test",
          eligible: true,
        },
      ],
      conversion: {
        ...editing.preparation.conversion,
        status: "saved" as const,
        draft: "# Reviewed input",
        saved_revision_id: "revision-1",
      },
    },
  };
  const request = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/v1/discovery/preparation/convert")) {
      expect(init?.method).toBe("POST");
      return { ok: true, status: 200, json: async () => editing } as Response;
    }
    if (url.endsWith("/v1/discovery/preparation/revisions")) {
      expect(JSON.parse(String(init?.body))).toEqual({ formatted_input: "# Reviewed input" });
      return { ok: true, status: 200, json: async () => saved } as Response;
    }
    return { ok: true, status: 200, json: async () => pending } as Response;
  });
  vi.stubGlobal("fetch", request);

  render(<DiscoveryView />);
  expect(await screen.findByRole("button", { name: "Convert" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Convert" }));

  expect(await screen.findByRole("textbox", { name: "Formatted Discovery Input" })).toBeTruthy();
  fireEvent.change(screen.getByRole("textbox", { name: "Formatted Discovery Input" }), {
    target: { value: "# Reviewed input" },
  });
  expect(screen.getByText("Unsaved review changes")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Save revision" }));

  await waitFor(() => expect(screen.getByText("Revision saved")).toBeTruthy());
  expect(screen.getByText("1 saved revision")).toBeTruthy();
  expect(screen.getByText("Eligible")).toBeTruthy();
  expect(request).toHaveBeenCalledWith(
    expect.stringContaining("/v1/discovery/preparation/revisions"),
    expect.anything(),
  );
});

it("deletes one draft Source Entry without changing the saved state", async () => {
  const source = {
    source_id: "source-1",
    filename: "notes.md",
    extension: ".md",
    size: 5,
    sha256: "hash-1",
  };
  const snapshot = (draftSources: typeof source[], dirty: boolean) => ({
    module: "discovery" as const,
    schema_version: 1,
    contexts: [
      { id: "preparation" as const, label: "Preparation", description: "Prepare inputs." },
      { id: "launch" as const, label: "Current Launch", description: "Observe a launch." },
      { id: "history" as const, label: "History", description: "Review history." },
    ],
    active_context: "preparation" as const,
    preparation: {
      status: dirty ? "draft" as const : "saved" as const,
      dirty,
      draft: { text: "Saved text.", sources: draftSources },
      saved: { text: "Saved text.", sources: [source] },
    },
    current_launch: null,
    history: [],
  });
  const request = vi.fn(async (url: string) => {
    if (url.includes("/sources/source-1")) {
      return { ok: true, status: 200, json: async () => snapshot([], true) } as Response;
    }
    return { ok: true, status: 200, json: async () => snapshot([source], false) } as Response;
  });
  vi.stubGlobal("fetch", request);

  render(<DiscoveryView />);
  expect(await screen.findByText("notes.md")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Remove notes.md" }));

  await waitFor(() => expect(screen.queryByText("notes.md")).toBeNull());
  expect(screen.getByText(/Saved Preparation remains unchanged until Save/)).toBeTruthy();
});
