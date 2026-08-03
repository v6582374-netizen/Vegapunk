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
  expect(screen.queryByText("Native module", { exact: true })).toBeNull();
  expect(screen.queryByText("Free-form text", { exact: true })).toBeNull();
  expect(screen.getByRole("textbox", { name: "Research text" }).className).toContain("min-h-[172px]");
  expect(screen.getByText(/Empty Preparation/)).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Discovery" })).toBeTruthy();
  expect(screen.getByText("Preparation in progress").closest(".discovery-context-nav-row")).toBeTruthy();
  expect(screen.queryByText("Preparation / stage canvas", { exact: false })).toBeNull();
  expect(screen.queryByText("Move one Preparation through four deliberate stages.", { exact: true })).toBeNull();
  expect(screen.queryByTestId("discovery-artifacts")).toBeNull();
  expect(screen.getByRole("button", { name: "Refresh Preparation" })).toBeTruthy();
  const preparationTab = screen.getByRole("tab", { name: "Preparation" });
  expect(preparationTab.getAttribute("aria-selected")).toBe("true");
  expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe(preparationTab.id);

  fireEvent.click(screen.getByRole("tab", { name: "Current Launch" }));
  expect(screen.queryByRole("button", { name: "Refresh Preparation" })).toBeNull();
  expect(screen.getByRole("heading", { name: "No current Launch" })).toBeTruthy();

  fireEvent.click(screen.getByRole("tab", { name: "History" }));
  expect(screen.getByRole("tab", { name: "History" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.queryByRole("button", { name: "Refresh Preparation" })).toBeNull();
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

it("confirms and atomically resets Preparation without affecting Launch navigation", async () => {
  const source = {
    source_id: "source-1",
    filename: "brief.md",
    extension: ".md",
    size: 5,
    sha256: "hash-1",
  };
  const revision = {
    revision_id: "revision-1",
    created_at: "2026-08-01T00:00:00.000Z",
    execution_input: {
      task_description: "Reviewed input",
      domain: "Scientific ML",
      background: "",
      constraints: [],
    },
    model_id: "gpt-test",
    eligible: true,
  };
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
  const populated = {
    ...base,
    preparation: {
      status: "saved" as const,
      dirty: false,
      draft: { text: "Reset this input.", sources: [source] },
      saved: { text: "Reset this input.", sources: [source] },
      revisions: [revision],
      conversion: {
        status: "saved" as const,
        execution_input: revision.execution_input,
        model_id: "gpt-test",
        error: null,
        saved_revision_id: revision.revision_id,
        base_fingerprint: "fingerprint-1",
        current_fingerprint: "fingerprint-1",
      },
    },
  };
  const empty = {
    ...base,
    preparation: {
      status: "empty" as const,
      dirty: false,
      draft: { text: "", sources: [] },
      saved: { text: "", sources: [] },
      revisions: [],
      conversion: {
        status: "pending" as const,
        draft: "",
        model_id: null,
        error: null,
        saved_revision_id: null,
        base_fingerprint: null,
        current_fingerprint: "fingerprint-empty",
      },
    },
  };
  const request = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/v1/discovery/preparation/reset")) {
      expect(init?.method).toBe("POST");
      return { ok: true, status: 200, json: async () => empty } as Response;
    }
    return { ok: true, status: 200, json: async () => populated } as Response;
  });
  vi.stubGlobal("fetch", request);

  render(<DiscoveryView />);
  expect(await screen.findByText("brief.md")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Refresh Preparation" }));
  expect(screen.getByRole("dialog").getAttribute("aria-modal")).toBe("true");
  expect(screen.getByRole("dialog").className).toContain("discovery-reset-dialog");
  expect(request).not.toHaveBeenCalledWith(
    expect.stringContaining("/v1/discovery/preparation/reset"),
    expect.anything(),
  );

  fireEvent.click(screen.getByRole("button", { name: "Reset Preparation" }));
  await waitFor(() => expect(screen.getByText("Preparation reset")).toBeTruthy());
  expect(screen.queryByText("brief.md")).toBeNull();
  expect(screen.queryByRole("textbox", { name: "Formatted Discovery Input" })).toBeNull();
  expect(request).toHaveBeenCalledWith(
    expect.stringContaining("/v1/discovery/preparation/reset"),
    expect.objectContaining({ method: "POST" }),
  );

  fireEvent.click(screen.getByRole("tab", { name: "Current Launch" }));
  expect(screen.queryByRole("button", { name: "Refresh Preparation" })).toBeNull();
});

it("converts a saved Preparation into structured inputs and saves an editor revision", async () => {
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
  const executionInput = {
    task_description: "Compare calibrated and uncalibrated surrogates.",
    domain: "Scientific ML",
    background: "baseline notes",
    constraints: ["No synthetic labels."],
  };
  const editing = {
    ...pending,
    preparation: {
      ...pending.preparation,
      conversion: {
        ...pending.preparation.conversion,
        status: "editing" as const,
        execution_input: executionInput,
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
          execution_input: { ...executionInput, task_description: "Reviewed objective." },
          model_id: "gpt-test",
          eligible: true,
        },
      ],
      conversion: {
        ...editing.preparation.conversion,
        status: "saved" as const,
        execution_input: { ...executionInput, task_description: "Reviewed objective." },
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
      const body = JSON.parse(String(init?.body));
      expect(body.execution_input.task_description).toBe("Reviewed objective.");
      return { ok: true, status: 200, json: async () => saved } as Response;
    }
    return { ok: true, status: 200, json: async () => pending } as Response;
  });
  vi.stubGlobal("fetch", request);

  render(<DiscoveryView />);
  expect(await screen.findByRole("button", { name: "Convert" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Convert" }));

  expect(await screen.findByTestId("execution-input-row")).toBeTruthy();
  fireEvent.click(screen.getByTestId("execution-input-row"));
  expect(await screen.findByRole("textbox", { name: "Task description" })).toBeTruthy();
  fireEvent.change(screen.getByRole("textbox", { name: "Task description" }), {
    target: { value: "Reviewed objective." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(screen.queryByRole("textbox", { name: "Formatted Discovery Input" })).toBeNull();
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

it("requires confirmation before admitting an eligible Discovery Launch", async () => {
  const base = {
    module: "discovery" as const,
    schema_version: 1,
    contexts: [
      { id: "preparation" as const, label: "Preparation", description: "Prepare inputs." },
      { id: "launch" as const, label: "Current Launch", description: "Observe a launch." },
      { id: "history" as const, label: "History", description: "Review history." },
    ],
    active_context: "preparation" as const,
    history: [],
  };
  const revision = {
    revision_id: "revision-1",
    created_at: "2026-08-01T00:00:00.000Z",
    execution_input: {
      task_description: "Reviewed input",
      domain: "Scientific ML",
      background: "",
      constraints: [],
    },
    model_id: "gpt-test",
    eligible: true,
  };
  const preparation = {
    status: "saved" as const,
    dirty: false,
    draft: { text: "Research question.", sources: [] },
    saved: { text: "Research question.", sources: [] },
    revisions: [revision],
    conversion: {
      status: "saved" as const,
      execution_input: revision.execution_input,
      model_id: "gpt-test",
      error: null,
      saved_revision_id: revision.revision_id,
      base_fingerprint: "fingerprint-1",
      current_fingerprint: "fingerprint-1",
    },
  };
  const launch = {
    launch_id: "launch-1",
    preparation_id: "preparation",
    revision_id: revision.revision_id,
    created_at: "2026-08-01T00:00:00.000Z",
    started_at: null,
    completed_at: null,
    state: "starting" as const,
    stage: "admission",
    round: 0,
    attempts: [],
    runner_pid: null,
    outcome: null,
    error: null,
  };
  const initial = { ...base, preparation, current_launch: null };
  const admitted = { ...base, preparation, active_context: "launch" as const, current_launch: launch };
  let launchStarted = false;
  const request = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/v1/discovery/launches")) {
      launchStarted = true;
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body))).toEqual({
        preparation_id: "preparation",
        revision_id: revision.revision_id,
      });
      expect(new Headers(init?.headers).get("Idempotency-Key")).toBeTruthy();
      return {
        ok: true,
        status: 201,
        json: async () => ({ launch_id: launch.launch_id, state: "starting", snapshot: admitted }),
      } as Response;
    }
    return { ok: true, status: 200, json: async () => (launchStarted ? admitted : initial) } as Response;
  });
  vi.stubGlobal("fetch", request);

  render(<DiscoveryView />);
  expect(await screen.findByRole("button", { name: "Run" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  expect(screen.getByRole("dialog")).toBeTruthy();
  expect(request).not.toHaveBeenCalledWith(
    expect.stringContaining("/v1/discovery/launches"),
    expect.anything(),
  );

  fireEvent.click(screen.getByRole("button", { name: "Start Launch" }));
  await waitFor(() =>
    expect(screen.getByRole("tab", { name: "Current Launch" }).getAttribute("aria-selected")).toBe("true"),
  );
  expect(screen.getByText(/Launch launch-1/)).toBeTruthy();
  expect(request).toHaveBeenCalledWith(
    expect.stringContaining("/v1/discovery/launches"),
    expect.anything(),
  );
});

it("shows Launch-owned artifacts for active and selected history contexts only", async () => {
  const launch = {
    launch_id: "launch-artifacts",
    preparation_id: "preparation",
    revision_id: "revision-1",
    created_at: "2026-08-01T00:00:00.000Z",
    started_at: "2026-08-01T00:00:01.000Z",
    completed_at: null,
    state: "running" as const,
    stage: "research",
    round: 1,
    attempts: [],
    runner_pid: 42,
    outcome: null,
    error: null,
  };
  const base = {
    module: "discovery" as const,
    schema_version: 1,
    contexts: [
      { id: "preparation" as const, label: "Preparation", description: "Prepare inputs." },
      { id: "launch" as const, label: "Current Launch", description: "Observe a launch." },
      { id: "history" as const, label: "History", description: "Review history." },
    ],
    preparation: {
      status: "empty" as const,
      dirty: false,
      draft: { text: "", sources: [] },
      saved: { text: "", sources: [] },
      revisions: [],
      conversion: {
        status: "pending" as const,
        draft: "",
        model_id: null,
        error: null,
        saved_revision_id: null,
        base_fingerprint: null,
        current_fingerprint: "",
      },
    },
    current_launch: launch,
    history: [launch],
  };
  const status = {
    launch,
    state: "running" as const,
    stage: "research",
    round: 1,
    checkpoint: null,
    timeline: { revision: 1, percent: 33, current_milestone_id: "research", milestones: [] },
    activity: { oldest_sequence: null, newest_sequence: null, truncated_before_sequence: 0, items: [] },
    allowed_actions: ["stop"],
    produced_outputs: [],
    latest_event_sequence: 0,
  };
  const request = vi.fn(async (url: string) => {
    if (url.endsWith("/v1/discovery")) {
      return { ok: true, status: 200, json: async () => ({ ...base, active_context: "launch" }) } as Response;
    }
    if (url.includes("/artifacts") && !url.includes("/read") && !url.includes("/reveal")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          launch_id: launch.launch_id,
          artifacts: [{ path: "report.md", name: "report.md", kind: "markdown", size: 12, modified_at: 1, previewable: true }],
        }),
      } as Response;
    }
    if (url.includes("/status")) return { ok: true, status: 200, json: async () => status } as Response;
    if (url.includes("/events")) return { ok: true, status: 200, json: async () => ({ events: [], latest_sequence: 0 }) } as Response;
    return { ok: true, status: 200, json: async () => ({}) } as Response;
  });
  vi.stubGlobal("fetch", request);

  render(<DiscoveryView />);
  expect(await screen.findByTestId("discovery-artifacts")).toBeTruthy();
  expect(await screen.findByText("report.md")).toBeTruthy();
  expect(screen.queryByText("Access")).toBeNull();

  fireEvent.click(screen.getByRole("tab", { name: "History" }));
  expect(await screen.findByTestId("discovery-artifacts")).toBeTruthy();
  expect(screen.getByText("report.md")).toBeTruthy();
});
