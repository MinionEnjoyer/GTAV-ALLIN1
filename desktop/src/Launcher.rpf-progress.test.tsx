import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "./App";
import type { Client, RecordData } from "./client";

afterEach(() => { cleanup(); localStorage.clear(); });

async function packageTask() {
  let resolve!: (value: RecordData) => void, reject!: (reason: Error) => void;
  const pending = new Promise<RecordData>((yes, no) => { resolve = yes; reject = no; });
  let onProgress!: (value: RecordData) => void, installed = false;
  const config = { general: { target_edition: "legacy" } };
  const request = vi.fn(async (operation: string, payload?: RecordData): Promise<RecordData> => {
    if (operation === "catalog") return { desktop_version: "0.6.5" };
    if (operation === "review") return { action: payload?.action, target: "Synthetic game", review_id: "rpf-test" };
    if (operation === "apply") return pending;
    if (operation === "reconnect_service") return { reconnected: true, replayed: false };
    if (operation === "inspect" && payload?.module === "package") return {
      source: "synthetic-base.zip", state_sha256: "synthetic", package: {
        name: "Synthetic Base", version: "1.2", editions: ["legacy"], type: "rpf", schema_version: 1,
        files: [], rpf_entry_count: 420, dependencies: [], conflicts: [], settings: {},
      },
    };
    return { config, installed: installed ? [{ mod_id: "synthetic-base", name: "Synthetic Base", version: "1.2", enabled: true }] : [] };
  });
  const client: Client = { request, selectPath: vi.fn(async () => "synthetic-base.zip"), close: vi.fn(),
    onClose: async () => () => {}, onHandoff: async () => () => {},
    onProgress: async (handler) => { onProgress = handler; return () => {}; } };
  render(<App client={client} />);
  await screen.findByRole("heading", { name: "Select your game installation" });
  await waitFor(() => expect(screen.getByRole("button", { name: "Packages" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Packages" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Review package import" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Review package import" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Review package installation" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Review package installation" }));
  const review = await screen.findByRole("region", { name: "Review changes" });
  fireEvent.click(within(review).getByRole("checkbox", { name: "I reviewed these changes" }));
  fireEvent.click(within(review).getByRole("button", { name: "Apply reviewed changes" }));
  return { request, resolve, reject, markInstalled: () => { installed = true; },
    progress: (value: RecordData) => act(() => onProgress(value)) };
}

const work = { estimated_actions: 1260, completed_actions: 315, entries: 420,
  elapsed_seconds: 1443, budget_seconds: 6420, active_seconds: 0, slow_action: false, budget_exceeded: false };

it("keeps a large install locked and connected across advisory overruns until its real result", async () => {
  const task = await packageTask();
  task.progress({ percentage: 25, message: "Verifying RPF: common/test.xml", rpf_work: work });
  expect(screen.getByRole("region", { name: "RPF workload" })).toHaveTextContent("315 of approximately 1260");
  expect(screen.getByRole("region", { name: "RPF workload" })).toHaveTextContent("24m 3s");
  task.progress({ percentage: 25, message: "Verifying RPF: common/test.xml", heartbeat: true,
    rpf_work: { ...work, elapsed_seconds: 6500, active_seconds: 121, slow_action: true, budget_exceeded: true } });
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
  expect(screen.getByText(/service is connected, but the action has not finished/)).toBeVisible();
  expect(screen.getByText(/has not been stopped or retried/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Back to draft" })).toBeDisabled();
  expect(task.request.mock.calls.filter(([op]) => op === "apply")).toHaveLength(1);
  task.markInstalled();
  await act(async () => { task.resolve({ action: "package_install", result: {} }); });
  await screen.findByText("Package Install completed");
  await waitFor(() => expect(screen.getByRole("button", { name: "Disable Synthetic Base" })).toBeEnabled());
  expect(screen.queryByRole("region", { name: "Package inspection" })).not.toBeInTheDocument();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Activity" }));
  const log = await screen.findByLabelText("Activity log");
  expect(log.textContent?.match(/Verifying RPF: common\/test.xml/g)).toHaveLength(1);
});

it("refreshes installed state after explicit reconnect without replaying or discarding a package draft", async () => {
  const task = await packageTask();
  await act(async () => { task.reject(new Error("Launcher service response timed out")); });
  await screen.findByText("Error: Launcher service response timed out");
  task.markInstalled();
  fireEvent.click(screen.getByRole("button", { name: "Reconnect service" }));
  await screen.findByRole("button", { name: "Disable Synthetic Base" });
  expect(screen.getByRole("region", { name: "Package inspection" })).toBeVisible();
  expect(screen.getByText(/No action was replayed/)).toBeVisible();
  expect(task.request.mock.calls.filter(([op]) => op === "apply")).toHaveLength(1);
});

it("clears an old completion notice before the next package mutation can fail", async () => {
  const task = await packageTask();
  task.markInstalled();
  await act(async () => { task.resolve({ action: "package_install", result: {} }); });
  await screen.findByText("Package Install completed");
  await waitFor(() => expect(screen.getByRole("button", { name: "Uninstall Synthetic Base" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Uninstall Synthetic Base" }));
  const review = await screen.findByRole("region", { name: "Review changes" });
  fireEvent.click(within(review).getByRole("checkbox", { name: "I reviewed these changes" }));
  task.request.mockRejectedValueOnce(new Error("Synthetic uninstall failure"));
  fireEvent.click(within(review).getByRole("button", { name: "Apply reviewed changes" }));
  await screen.findByText("Error: Synthetic uninstall failure");
  expect(screen.queryByText("Package Install completed")).not.toBeInTheDocument();
});
