import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { useState } from "react";
import RuntimeInjectors from "./RuntimeInjectors";
import type { Client, RecordData } from "./client";

const hash = (letter: string) => letter.repeat(64);
const document: RecordData = { schema_version: 1, enabled: false, replacement_chance: 0,
  entries: [{ package_id: "v", model: "demo_car", enabled: false, weight: .1 }] };
const snapshot = () => ({ state_sha256: hash("a"), traffic_population: {
  document_sha256: hash("b"), document: structuredClone(document),
  models: [{ package_id: "v", model: "demo_car", name: "traffic demo", category: "Sports" }], warnings: [],
} });
function client() {
  return { request: vi.fn(async (operation: string) => operation === "inspect" ? snapshot() : {}), selectPath: vi.fn(), onClose: vi.fn(), onHandoff: vi.fn(), onProgress: vi.fn(), close: vi.fn() } as unknown as Client;
}
function Harness({ injectedClient = client(), reviewed = vi.fn(), locked = false }: { injectedClient?: Client; reviewed?: ReturnType<typeof vi.fn>; locked?: boolean }) {
  const [draft, setDraft] = useState<RecordData | null>(null);
  return <RuntimeInjectors client={injectedClient} config={null} draft={draft} change={setDraft} locked={locked} review={reviewed} />;
}

it("reviews exact document digests without applying, and rejects invalid traffic weights", async () => {
  const service = client(), review = vi.fn(), user = userEvent.setup();
  render(<Harness injectedClient={service} reviewed={review} />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  await user.click(screen.getByRole("checkbox", { name: "Enable traffic injector" }));
  await user.click(screen.getByRole("checkbox", { name: "Include" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "traffic demo weight" }), { target: { value: "20.1" } });
  expect(screen.getByRole("button", { name: "Review Traffic policy" })).toBeDisabled();
  fireEvent.change(screen.getByRole("spinbutton", { name: "traffic demo weight" }), { target: { value: "3.5" } });
  await user.click(screen.getByRole("button", { name: "Review Traffic policy" }));
  expect(review).toHaveBeenCalledWith("traffic_population_save", expect.objectContaining({ expected_document_sha256: hash("b"), document: expect.objectContaining({ entries: [expect.objectContaining({ weight: 3.5 })] }) }));
});

it("exposes replacement chance through both controls and reloads the saved policy", async () => {
  const user = userEvent.setup(), review = vi.fn();
  const persisted: RecordData = snapshot();
  const service = { ...client(), request: vi.fn(async () => structuredClone(persisted)) } as unknown as Client;
  const view = render(<Harness injectedClient={service} reviewed={review} />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  await user.click(screen.getByRole("checkbox", { name: "Enable traffic injector" }));
  await user.click(screen.getByRole("checkbox", { name: "Include" }));
  fireEvent.change(screen.getAllByRole("slider")[0], { target: { value: "0.5" } });
  expect(screen.getByRole("spinbutton", { name: "Traffic replacement chance percent" })).toHaveValue(50);
  fireEvent.change(screen.getByRole("spinbutton", { name: "Traffic replacement chance percent" }), { target: { value: "25" } });
  expect(screen.getAllByRole("slider")[0]).toHaveValue("0.25");
  await user.click(screen.getByRole("button", { name: "Review Traffic policy" }));
  persisted.traffic_population.document = review.mock.calls[0][1].document;
  persisted.traffic_population.document_sha256 = hash("c");
  view.unmount(); render(<Harness injectedClient={service} />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  expect(screen.getByRole("checkbox", { name: "Enable traffic injector" })).toBeChecked();
  expect(screen.getByRole("spinbutton", { name: "Traffic replacement chance percent" })).toHaveValue(25);
});

it("drops a stale inspection response and does not update after unmount", async () => {
  let resolve!: (value: RecordData) => void;
  const service = { ...client(), request: vi.fn(() => new Promise<RecordData>(done => { resolve = done; })) } as unknown as Client;
  const change = vi.fn();
  const view = render(<RuntimeInjectors client={service} config={null} draft={null} change={change} locked={false} review={vi.fn()} />);
  change.mockClear();
  await userEvent.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  view.unmount(); resolve(snapshot());
  await waitFor(() => expect(change).not.toHaveBeenCalled());
});
