// The run desk, exercised against a fully mocked ../api: the whole point of the surface is that
// every pixel traces back to a real endpoint, so these tests drive it exactly as the server does —
// register, start, feed the cursor-polled event log, finish, cancel, fail.

import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { TranslationView } from "./TranslationView";
import type { TranslationDocument, TranslationRun } from "../api";

const mocks = vi.hoisted(() => ({
  getTranslationSettings: vi.fn(),
  listTranslationDocuments: vi.fn(),
  listTranslationRuns: vi.fn(),
  registerTranslationDocuments: vi.fn(),
  startTranslationRuns: vi.fn(),
  getTranslationRun: vi.fn(),
  getTranslationRunEvents: vi.fn(),
  cancelTranslationRun: vi.fn(),
  forgetTranslationDocument: vi.fn(),
  streamTranslationRunLog: vi.fn(),
  translationArtifactUrl: vi.fn(),
  fetchTranslationArtifactBlobUrl: vi.fn(),
}));

vi.mock("../api", () => mocks);

const {
  getTranslationSettings,
  listTranslationDocuments,
  listTranslationRuns,
  registerTranslationDocuments,
  startTranslationRuns,
  getTranslationRun,
  getTranslationRunEvents,
  cancelTranslationRun,
  forgetTranslationDocument,
  streamTranslationRunLog,
  translationArtifactUrl,
} = mocks;

const DOC: TranslationDocument = {
  document_id: "doc-1",
  filename: "attention-is-all-you-need.pdf",
  source_path: "/home/loongge/papers/attention-is-all-you-need.pdf",
  size: 2_411_724,
  sha256: "a".repeat(64),
  pages: 15,
  bundle_dir: "/home/loongge/papers/attention-is-all-you-need",
};

const STAGES = [
  { name: "Parse PDF and Create Intermediate Representation", weight: 14.12 },
  { name: "Translate Paragraphs", weight: 46.96 },
  { name: "Save PDF", weight: 6.34 },
];

function run(overrides: Partial<TranslationRun> = {}): TranslationRun {
  return {
    run_id: "run-1",
    document_id: DOC.document_id,
    filename: DOC.filename,
    source_path: DOC.source_path,
    bundle_dir: DOC.bundle_dir,
    state: "running",
    stage: null,
    stage_index: 0,
    stage_total_count: STAGES.length,
    stage_current: 0,
    stage_total: 0,
    stage_progress: 0,
    overall_progress: 0,
    created_at: 1_760_000_000,
    started_at: 1_760_000_001,
    finished_at: null,
    elapsed_seconds: 3.4,
    error: null,
    lang_in: "en",
    lang_out: "zh",
    stages: STAGES,
    artifacts: [],
    result: null,
    ...overrides,
  };
}

const noEvents = { run_id: "run-1", events: [], oldest_sequence: null, latest_sequence: 0, truncated_before_sequence: 0 };

beforeEach(() => {
  getTranslationSettings.mockResolvedValue({ values: { lang_in: "en", lang_out: "zh" } });
  listTranslationDocuments.mockResolvedValue({ documents: [] });
  listTranslationRuns.mockResolvedValue({ runs: [] });
  registerTranslationDocuments.mockResolvedValue({ documents: [] });
  startTranslationRuns.mockResolvedValue({ runs: [] });
  getTranslationRun.mockResolvedValue(run());
  getTranslationRunEvents.mockResolvedValue(noEvents);
  cancelTranslationRun.mockResolvedValue(run({ state: "cancelled" }));
  forgetTranslationDocument.mockResolvedValue({
    document_id: DOC.document_id,
    filename: DOC.filename,
    removed_runs: 1,
    cancelled_runs: [],
    source_deleted: false,
    bundle_dir: "",
  });
  streamTranslationRunLog.mockResolvedValue(undefined);
  translationArtifactUrl.mockImplementation((runId: string, name: string) => `http://local/${runId}/${name}`);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const queue = () => screen.getByRole("region", { name: "Document queue" });
const runPanel = () => screen.getByRole("region", { name: "Current run" });
const artifactPanel = () => screen.getByRole("region", { name: "Artifacts" });

it("states plainly that the queue is empty, and offers both ways in", async () => {
  render(<TranslationView />);

  await waitFor(() => expect(screen.getByText(/No documents yet/i)).toBeTruthy());
  expect(within(queue()).getByLabelText(/Add PDF documents/i)).toBeTruthy();
  expect(within(queue()).getByLabelText(/Register a local document by absolute path/i)).toBeTruthy();
  expect(within(runPanel()).getByText(/Add a document to start a translation run/i)).toBeTruthy();
  expect(startTranslationRuns).not.toHaveBeenCalled();
});

it("registers a local absolute path and shows the document in the queue", async () => {
  registerTranslationDocuments.mockResolvedValue({ documents: [DOC] });
  render(<TranslationView />);
  await waitFor(() => expect(screen.getByText(/No documents yet/i)).toBeTruthy());

  fireEvent.change(within(queue()).getByLabelText(/Register a local document by absolute path/i), {
    target: { value: DOC.source_path },
  });
  fireEvent.click(within(queue()).getByRole("button", { name: "Add path" }));

  await waitFor(() => expect(registerTranslationDocuments).toHaveBeenCalledWith({ paths: [DOC.source_path] }));
  expect(within(queue()).getByTitle(DOC.filename)).toBeTruthy();
  expect(screen.getByRole("progressbar", { name: new RegExp(`Overall translation progress for ${DOC.filename}`) })).toBeTruthy();
});

it("registers dropped PDF bytes as base64 and ignores everything that is not a PDF", async () => {
  registerTranslationDocuments.mockResolvedValue({ documents: [DOC] });
  render(<TranslationView />);
  await waitFor(() => expect(screen.getByText(/No documents yet/i)).toBeTruthy());

  const pdf = new File(["%PDF-1.7 body"], DOC.filename, { type: "application/pdf" });
  const notes = new File(["nope"], "notes.txt", { type: "text/plain" });
  fireEvent.drop(within(queue()).getByLabelText(/Add PDF documents/i), { dataTransfer: { files: [pdf, notes] } });

  await waitFor(() => expect(registerTranslationDocuments).toHaveBeenCalledTimes(1));
  const payload = registerTranslationDocuments.mock.calls[0][0];
  expect(payload.files).toHaveLength(1);
  expect(payload.files[0].filename).toBe(DOC.filename);
  expect(payload.files[0].content_base64.length).toBeGreaterThan(0);
  expect(payload.files[0].content_base64).not.toContain("data:");
});

it("starts a run for the queued document and advances progress from the event log", async () => {
  listTranslationDocuments.mockResolvedValue({ documents: [DOC] });
  startTranslationRuns.mockResolvedValue({ runs: [run()] });
  render(<TranslationView />);
  await waitFor(() => expect(within(queue()).getByTitle(DOC.filename)).toBeTruthy());

  fireEvent.click(within(queue()).getByRole("button", { name: /^Translate$/ }));
  await waitFor(() => expect(startTranslationRuns).toHaveBeenCalledWith([DOC.document_id]));

  const overall = () => screen.getByRole("progressbar", { name: new RegExp(`Overall translation progress`) });
  await waitFor(() => expect(overall().getAttribute("aria-valuenow")).toBe("0"));

  getTranslationRunEvents.mockResolvedValue({
    ...noEvents,
    latest_sequence: 2,
    events: [
      { sequence: 1, at: 1_760_000_002, type: "progress_start", stage: "Translate Paragraphs", stage_current: 0, stage_total: 240, overall_progress: 30.6 },
      { sequence: 2, at: 1_760_000_003, type: "progress_update", stage: "Translate Paragraphs", stage_current: 120, stage_total: 240, stage_progress: 50, overall_progress: 54.2 },
    ],
  });

  await waitFor(() => expect(overall().getAttribute("aria-valuenow")).toBe("54"), { timeout: 3000 });
  expect(overall().getAttribute("aria-valuetext")).toContain("Translate");
  // The count shows twice on purpose: once in the hero line, once on the active stage row.
  expect(within(runPanel()).getAllByText("120/240").length).toBe(2);
  expect(within(runPanel()).getByRole("progressbar", { name: /Translate progress/i }).getAttribute("aria-valuetext")).toBe("120 of 240");
  expect(getTranslationRunEvents.mock.calls[0][0]).toBe("run-1");
  expect(getTranslationRunEvents.mock.calls[0][1]).toBe(0);
});

it("shows the artifacts and the bundle directory once the run finishes", async () => {
  listTranslationDocuments.mockResolvedValue({ documents: [DOC] });
  listTranslationRuns.mockResolvedValue({ runs: [run()] });
  const finished = run({
    state: "done",
    finished_at: 1_760_000_120,
    elapsed_seconds: 118.4,
    overall_progress: 100,
    artifacts: [
      { name: "attention-is-all-you-need.pdf", role: "source", size: 2_411_724, path: `${DOC.bundle_dir}/attention-is-all-you-need.pdf` },
      { name: "attention.zh.mono.pdf", role: "mono", size: 2_610_881, path: `${DOC.bundle_dir}/attention.zh.mono.pdf` },
      { name: "attention.zh.dual.pdf", role: "dual", size: 5_018_112, path: `${DOC.bundle_dir}/attention.zh.dual.pdf` },
      { name: "glossary.csv", role: "glossary", size: 2_048, path: `${DOC.bundle_dir}/glossary.csv` },
    ],
  });
  getTranslationRun.mockResolvedValue(finished);
  getTranslationRunEvents.mockResolvedValue({
    ...noEvents,
    latest_sequence: 9,
    events: [{ sequence: 9, at: 1_760_000_120, type: "finish", overall_progress: 100, message: "bundle written" }],
  });

  render(<TranslationView />);

  await waitFor(() => expect(within(artifactPanel()).getByText("attention.zh.dual.pdf")).toBeTruthy(), { timeout: 3000 });
  const panel = artifactPanel();
  const row = (role: string) => within(panel).getByTestId(`translation-artifact-${role}`);
  expect(row("dual").textContent).toContain("Side-by-side bilingual");
  expect(row("mono").textContent).toContain("Translated only");
  expect(row("glossary").textContent).toContain("Auto-extracted terms");
  expect(row("source").textContent).toContain("Original document");
  expect(within(panel).getByText(/Bundled beside the original/i)).toBeTruthy();
  expect(screen.getByTestId("translation-bundle-dir").textContent).toContain(DOC.bundle_dir);
  expect(within(panel).getAllByRole("link", { name: "Download" }).length).toBe(4);
  expect(screen.getByRole("progressbar", { name: /Overall translation progress/ }).getAttribute("aria-valuenow")).toBe("100");
});

it("cancels the active run and reflects the cancelled state", async () => {
  listTranslationDocuments.mockResolvedValue({ documents: [DOC] });
  listTranslationRuns.mockResolvedValue({ runs: [run({ state: "running", overall_progress: 22 })] });
  cancelTranslationRun.mockResolvedValue(run({ state: "cancelled", overall_progress: 22, finished_at: 1_760_000_050 }));

  render(<TranslationView />);
  const cancelButton = await waitFor(() => within(runPanel()).getByRole("button", { name: /Cancel run/i }));
  fireEvent.click(cancelButton);

  await waitFor(() => expect(cancelTranslationRun).toHaveBeenCalledWith("run-1"));
  await waitFor(() => expect(screen.getByTestId("translation-run-phase").textContent).toBe("Cancelled"));
  expect(within(artifactPanel()).getByText(/Cancelled before any artifact was written/i)).toBeTruthy();
  expect(within(runPanel()).getByRole("button", { name: /Run again/i })).toBeTruthy();
});

it("surfaces a failed run's message, and a dead service as one dismissible alert", async () => {
  listTranslationDocuments.mockResolvedValue({ documents: [DOC] });
  listTranslationRuns.mockResolvedValue({
    runs: [run({ state: "error", error: "BabelDOC exited with code 1: no OpenAI credentials", finished_at: 1_760_000_030 })],
  });

  render(<TranslationView />);
  await waitFor(() => expect(screen.getByTestId("translation-run-phase").textContent).toBe("Failed"));
  expect(within(runPanel()).getByText(/no OpenAI credentials/i)).toBeTruthy();
  expect(within(artifactPanel()).getByText(/failed before writing artifacts/i)).toBeTruthy();

  cleanup();
  listTranslationDocuments.mockRejectedValue(new Error("translation service is not running"));
  render(<TranslationView />);

  const alert = await waitFor(() => screen.getByRole("alert"));
  expect(alert.textContent).toContain("translation service is not running");
  fireEvent.click(within(alert).getByRole("button", { name: "Dismiss" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
});

it("removes a queue entry, dropping its runs and telling the user the file stayed put", async () => {
  listTranslationDocuments.mockResolvedValue({ documents: [DOC] });
  listTranslationRuns.mockResolvedValue({ runs: [run({ state: "done" })] });

  render(<TranslationView />);
  await waitFor(() => expect(within(queue()).getByTitle(DOC.filename)).toBeTruthy());

  fireEvent.click(within(queue()).getByRole("button", { name: `Remove ${DOC.filename} from the queue` }));

  await waitFor(() => expect(forgetTranslationDocument).toHaveBeenCalledWith(DOC.document_id));
  // The row goes, and so does the run that belonged to it.
  await waitFor(() => expect(within(queue()).queryByTitle(DOC.filename)).toBeNull());
  expect(await screen.findByText(/left in place/i)).toBeTruthy();
});

it("says so plainly when removing also deleted the staged upload", async () => {
  listTranslationDocuments.mockResolvedValue({ documents: [DOC] });
  forgetTranslationDocument.mockResolvedValue({
    document_id: DOC.document_id,
    filename: DOC.filename,
    removed_runs: 0,
    cancelled_runs: [],
    source_deleted: true,
    bundle_dir: "",
  });

  render(<TranslationView />);
  await waitFor(() => expect(within(queue()).getByTitle(DOC.filename)).toBeTruthy());
  fireEvent.click(within(queue()).getByRole("button", { name: `Remove ${DOC.filename} from the queue` }));

  await waitFor(() => expect(within(queue()).queryByTitle(DOC.filename)).toBeNull());
  expect(screen.queryByText(/left in place/i)).toBeNull();
});

it("keeps the row and reports why when removal fails", async () => {
  listTranslationDocuments.mockResolvedValue({ documents: [DOC] });
  forgetTranslationDocument.mockRejectedValue(new Error("document is still being written"));

  render(<TranslationView />);
  await waitFor(() => expect(within(queue()).getByTitle(DOC.filename)).toBeTruthy());
  fireEvent.click(within(queue()).getByRole("button", { name: `Remove ${DOC.filename} from the queue` }));

  const alert = await waitFor(() => screen.getByRole("alert"));
  expect(alert.textContent).toContain("document is still being written");
  expect(within(queue()).getByTitle(DOC.filename)).toBeTruthy();
});
