import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DiscoveryView } from "./DiscoveryView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("renders one empty Discovery shell with internal lifecycle navigation", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({
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

  expect(await screen.findByTestId("discovery-view")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Discovery" })).toBeTruthy();
  expect(screen.getByRole("tab", { name: "Preparation" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByRole("heading", { name: "Your first Preparation is empty" })).toBeTruthy();

  fireEvent.click(screen.getByRole("tab", { name: "History" }));
  expect(screen.getByRole("tab", { name: "History" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByRole("heading", { name: "No Launch history yet" })).toBeTruthy();
});
