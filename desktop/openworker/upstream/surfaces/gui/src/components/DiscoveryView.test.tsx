import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

  expect(await screen.findByRole("heading", { name: "Your first Preparation is empty" })).toBeTruthy();
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
