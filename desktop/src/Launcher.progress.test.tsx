import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "./App";
import type { Client, RecordData } from "./client";

afterEach(() => { cleanup(); vi.useRealTimers(); localStorage.clear(); });
function deferred() {
  let resolve!: (value: RecordData) => void, reject!: (reason: Error) => void;
  const promise = new Promise<RecordData>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function launch() {
  const apply = deferred(), poll = deferred();
  let progress!: (value: RecordData) => void;
  const request = vi.fn(async (operation: string, payload?: RecordData): Promise<RecordData> => {
    if (operation === "catalog") return { desktop_version: "0.6.4" };
    if (operation === "review") return { action: payload?.action, target: "test", review_id: "test" };
    if (operation === "apply") return apply.promise;
    if (operation === "startup_status") return poll.promise;
    return { config: { general: { target_edition: "enhanced" } } };
  });
  const client: Client = { request, selectPath: vi.fn(), close: vi.fn(),
    onClose: async () => () => {}, onHandoff: async () => () => {},
    onProgress: async (handler) => { progress = handler; return () => {}; } };
  render(<App client={client} />);
  await screen.findByRole("heading", { name: "Select your game installation" });
  await waitFor(() => expect(screen.getByRole("button", { name: "Launch Story Mode" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Launch Story Mode" }));
  const review = await screen.findByRole("region", { name: "Review changes" });
  fireEvent.click(within(review).getByRole("checkbox", { name: "I reviewed these changes" }));
  fireEvent.click(within(review).getByRole("button", { name: "Apply reviewed changes" }));
  return { apply, poll, progress: (value: RecordData) => act(() => progress(value)), request };
}
async function dispatched(apply: ReturnType<typeof deferred>) {
  await act(async () => { apply.resolve({ action: "launch", result: { startup_monitoring: true } }); });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(screen.getByRole("button", { name: "Launch Story Mode" })).toBeEnabled());
}
it("fills from measured preview progress and uses plain status for unknown game loading", async () => {
  const task = await launch();
  task.progress({ percentage: 25, message: "Weapon previews: 5 cached" });
  const bar = screen.getByRole("progressbar", { name: "Preparing GTA launch" });
  expect(bar).toHaveAttribute("aria-valuenow", "25");
  expect(bar.firstElementChild).toHaveStyle({ width: "25%" });
  expect(screen.getByText("Weapon previews: 5 cached")).toBeVisible();
  task.progress({ percentage: 15, message: "A delayed preview update" });
  expect(bar).toHaveAttribute("aria-valuenow", "25");
  task.progress({ percentage: 100, message: "Preview queue processed" });
  expect(bar.firstElementChild).toHaveStyle({ width: "100%" });
  task.progress({ percentage: null, message: "Checking map data" });
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  expect(screen.getByText("Checking map data")).toBeVisible();
  await dispatched(task.apply);
});
it("polls quietly, queues user clicks, and stops after Story Mode readiness", async () => {
  const task = await launch(); await dispatched(task.apply);
  await waitFor(() => expect(task.request).toHaveBeenCalledWith("startup_status", {}), { timeout: 2000 });
  expect(screen.queryByText("Working…")).not.toBeInTheDocument();
  const packages = within(screen.getByRole("navigation", { name: "Primary" })).getByRole("button", { name: "Packages" });
  expect(packages).toBeEnabled();
  fireEvent.click(packages);
  await act(async () => { task.poll.resolve({ active: false, ready: ["story"], milestones: [["story", "Story Mode"]] }); });
  expect(task.request).toHaveBeenCalledWith("inspect", expect.objectContaining({ module: "mods" }));
  const calls = task.request.mock.calls.filter(([op]) => op === "startup_status").length;
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 1100)); });
  expect(task.request.mock.calls.filter(([op]) => op === "startup_status")).toHaveLength(calls);
  expect(screen.queryByText("Working…")).not.toBeInTheDocument();
});
it("reports a poll failure once without toggling the foreground status", async () => {
  const task = await launch(); await dispatched(task.apply);
  await waitFor(() => expect(task.request).toHaveBeenCalledWith("startup_status", {}), { timeout: 2000 });
  await act(async () => { task.poll.reject(new Error("offline")); });
  expect(screen.getByRole("region", { name: "Startup needs attention" })).toHaveTextContent("offline");
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 1100)); });
  expect(task.request.mock.calls.filter(([op]) => op === "startup_status")).toHaveLength(1);
  expect(screen.queryByText("Working…")).not.toBeInTheDocument();
});

it("cancels the active launch without unlocking early or claiming GTA started", async () => {
  const task = await launch();
  expect(screen.getByRole("button", { name: "Cancel launch" })).toBeDisabled();
  task.progress({ percentage: 30, message: "Rendering previews", cancellable: true, launch_review_id: "test" });
  const button = screen.getByRole("button", { name: "Cancel launch" });
  expect(button).toBeEnabled();
  fireEvent.click(button);
  fireEvent.click(button);
  await waitFor(() => expect(task.request).toHaveBeenCalledWith("cancel_launch", { review_id: "test" }));
  expect(task.request.mock.calls.filter(([op]) => op === "cancel_launch")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Cancelling launch…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Back to draft" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Launch Story Mode" })).toBeDisabled();
  await act(async () => { task.apply.resolve({ action: "launch", result: { status: "cancelled", game_started: false } }); });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByText("Launch cancelled. GTA was not started; completed previews remain cached.")).toBeVisible();
  expect(screen.queryByText(/GTA started\./)).not.toBeInTheDocument();
  expect(task.request.mock.calls.some(([op]) => op === "startup_status")).toBe(false);
});

it("does not cancel stale progress or a dispatched game", async () => {
  const task = await launch();
  task.progress({ percentage: null, message: "Old progress", cancellable: true, launch_review_id: "old" });
  expect(screen.getByRole("button", { name: "Cancel launch" })).toBeDisabled();
  task.progress({ percentage: null, message: "Requesting GTA launch", cancellable: false, launch_review_id: "test" });
  fireEvent.click(screen.getByRole("button", { name: "Cancel launch" }));
  expect(task.request.mock.calls.some(([op]) => op === "cancel_launch")).toBe(false);
  await dispatched(task.apply);
});

it("shows a cancellation-channel failure without releasing the active launch", async () => {
  const task = await launch();
  task.progress({ percentage: null, message: "Validating", cancellable: true, launch_review_id: "test" });
  task.request.mockRejectedValueOnce(new Error("Control unavailable"));
  fireEvent.click(screen.getByRole("button", { name: "Cancel launch" }));
  await screen.findByText(/Control unavailable/);
  expect(screen.getByRole("button", { name: "Back to draft" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Cancel launch" })).toBeEnabled();
  await dispatched(task.apply);
});
