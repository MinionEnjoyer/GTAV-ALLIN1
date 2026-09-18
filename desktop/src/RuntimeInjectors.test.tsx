import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { useState } from "react";
import RuntimeInjectors from "./RuntimeInjectors";
import type { Client, RecordData } from "./client";

const hash = (letter: string) => letter.repeat(64);
const documents: Record<string, RecordData> = {
  ped: { schema_version: 1, enabled: false, replacement_chance: 0, max_added: 0, entries: [{ package_id: "p", model: "ig_demo", mode: "disabled" }] },
  weapon: { schema_version: 1, enabled: false, replacement_chance: 0, entries: [{ package_id: "w", weapon: "WEAPON_DEMO", enabled: false, weight: 1 }] },
  traffic: { schema_version: 1, enabled: false, replacement_chance: 0, entries: [{ package_id: "v", model: "demo_car", enabled: false, weight: .1 }] },
};
function snapshot(kind: string) {
  const key = kind === "ped_manager" ? "ped" : kind === "weapon_manager" ? "weapon" : "traffic";
  const population = key === "ped" ? "ped_population" : key === "weapon" ? "weapon_population" : "traffic_population";
  const field = key === "weapon" ? "weapon" : "model";
  return { state_sha256: hash("a"), [population]: { document_sha256: hash("b"), document: structuredClone(documents[key]), models: [{ package_id: documents[key].entries[0].package_id, [field]: documents[key].entries[0][field], name: `${key} demo`, category: "pistol" }], warnings: [], ...(key === "ped" ? { targets: ["a_m_m_business_01"] } : {}) } };
}
function client() {
  return { request: vi.fn(async (operation: string, payload: RecordData = {}) => operation === "inspect" ? snapshot(payload.module) : {}), selectPath: vi.fn(), onClose: vi.fn(), onHandoff: vi.fn(), onProgress: vi.fn(), close: vi.fn() } as unknown as Client;
}
function Harness({ kind = "weapon", injectedClient = client(), reviewed = vi.fn(), locked = false }: { kind?: "ped" | "weapon" | "traffic"; injectedClient?: Client; reviewed?: ReturnType<typeof vi.fn>; locked?: boolean }) {
  const [draft, setDraft] = useState<RecordData | null>(null);
  return <RuntimeInjectors client={injectedClient} kind={kind} config={null} draft={draft} change={setDraft} locked={locked} review={reviewed} />;
}

it("reviews exact document digests without applying, and rejects invalid weapon weights", async () => {
  const service = client(), review = vi.fn(), user = userEvent.setup();
  render(<Harness injectedClient={service} reviewed={review} />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  await user.click(screen.getByRole("checkbox", { name: "Enable same-tier weapon replacement" }));
  await user.click(screen.getByRole("checkbox", { name: "Include" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "weapon demo weight" }), { target: { value: "1.5" } });
  expect(screen.getByRole("button", { name: "Review Weapons policy" })).toBeDisabled();
  fireEvent.change(screen.getByRole("spinbutton", { name: "weapon demo weight" }), { target: { value: "101" } });
  expect(screen.getByRole("button", { name: "Review Weapons policy" })).toBeDisabled();
  expect(review).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole("spinbutton", { name: "weapon demo weight" }), { target: { value: "7" } });
  await user.click(screen.getByRole("button", { name: "Review Weapons policy" }));
  expect(review).toHaveBeenCalledWith("weapon_population_save", expect.objectContaining({ expected_document_sha256: hash("b"), document: expect.objectContaining({ entries: [expect.objectContaining({ weight: 7 })] }) }));
});

it("supports pedestrian replace targets and bounded add caps, while traffic accepts decimal weights", async () => {
  const user = userEvent.setup(), pedReview = vi.fn();
  const { unmount } = render(<Harness kind="ped" reviewed={pedReview} />);
  expect(screen.getByText("Ambient NPCs only; does not replace Franklin, Michael, Trevor, or mission/story characters. Player, mission, and scripted pedestrians are never edited.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  await user.click(screen.getByRole("checkbox", { name: "Enable optional ambient pedestrians" }));
  await user.selectOptions(screen.getByRole("combobox", { name: "ped demo mode" }), "replace");
  expect(screen.getByRole("button", { name: "Review Pedestrians policy" })).toBeDisabled();
  await user.selectOptions(screen.getByRole("combobox", { name: "ped demo target" }), "a_m_m_business_01");
  fireEvent.change(screen.getByRole("spinbutton", { name: "Maximum added pedestrians" }), { target: { value: "2.5" } });
  expect(screen.getByRole("button", { name: "Review Pedestrians policy" })).toBeDisabled();
  fireEvent.change(screen.getByRole("spinbutton", { name: "Maximum added pedestrians" }), { target: { value: "21" } });
  expect(screen.getByRole("button", { name: "Review Pedestrians policy" })).toBeDisabled();
  fireEvent.change(screen.getByRole("spinbutton", { name: "Maximum added pedestrians" }), { target: { value: "3" } });
  await user.click(screen.getByRole("button", { name: "Review Pedestrians policy" }));
  expect(pedReview).toHaveBeenCalledWith("ped_population_save", expect.objectContaining({ document: expect.objectContaining({ max_added: 3, entries: [expect.objectContaining({ mode: "replace", target_model: "a_m_m_business_01" })] }) }));
  unmount(); render(<Harness kind="traffic" />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" })); await user.click(screen.getByRole("checkbox", { name: "Enable traffic injector" })); await user.click(screen.getByRole("checkbox", { name: "Include" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "traffic demo weight" }), { target: { value: "20.1" } }); expect(screen.getByRole("button", { name: "Review Traffic policy" })).toBeDisabled();
  fireEvent.change(screen.getByRole("spinbutton", { name: "traffic demo weight" }), { target: { value: "3.5" } }); expect(screen.getByRole("button", { name: "Review Traffic policy" })).toBeEnabled();
});

it("drops a stale inspection response and discards a local draft without review", async () => {
  let resolve!: (value: RecordData) => void;
  const service = { ...client(), request: vi.fn(() => new Promise<RecordData>(done => { resolve = done; })) } as unknown as Client;
  const { rerender } = render(<Harness kind="ped" injectedClient={service} />);
  await userEvent.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  rerender(<Harness kind="weapon" injectedClient={service} />);
  resolve(snapshot("ped_manager"));
  await waitFor(() => expect(screen.queryByText("ped demo")).not.toBeInTheDocument());
  const normal = client(); rerender(<Harness kind="weapon" injectedClient={normal} />);
  await userEvent.click(screen.getByRole("button", { name: "Load authorized catalog" })); await userEvent.click(screen.getByRole("checkbox", { name: "Enable same-tier weapon replacement" }));
  await userEvent.click(screen.getByRole("button", { name: "Discard draft" }));
  expect(screen.getByRole("button", { name: "Review Weapons policy" })).toBeDisabled();
});

it("does not change a draft after an injector unmounts during inspection", async () => {
  let resolve!: (value: RecordData) => void;
  const service = { ...client(), request: vi.fn(() => new Promise<RecordData>(done => { resolve = done; })) } as unknown as Client;
  const change = vi.fn();
  const view = render(<RuntimeInjectors client={service} kind="ped" config={null} draft={null} change={change} locked={false} review={vi.fn()} />);
  change.mockClear();
  await userEvent.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  view.unmount(); resolve(snapshot("ped_manager"));
  await Promise.resolve(); await Promise.resolve();
  expect(change).not.toHaveBeenCalled();
});

it("exposes 50 percent through both weapon chance controls and reloads the saved policy", async () => {
  const user = userEvent.setup(), review = vi.fn();
  const persisted: RecordData = snapshot("weapon_manager");
  const service = { ...client(), request: vi.fn(async () => structuredClone(persisted)) } as unknown as Client;
  const view = render(<Harness injectedClient={service} reviewed={review} />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  await user.click(screen.getByRole("checkbox", { name: "Enable same-tier weapon replacement" }));
  await user.click(screen.getByRole("checkbox", { name: "Include" }));
  fireEvent.change(screen.getAllByRole("slider")[0], { target: { value: "0.5" } });
  expect(screen.getByRole("spinbutton", { name: "Weapons replacement chance percent" })).toHaveValue(50);
  fireEvent.change(screen.getByRole("spinbutton", { name: "Weapons replacement chance percent" }), { target: { value: "25" } });
  expect(screen.getAllByRole("slider")[0]).toHaveValue("0.25");
  fireEvent.change(screen.getByRole("spinbutton", { name: "Weapons replacement chance percent" }), { target: { value: "50" } });
  await user.click(screen.getByRole("button", { name: "Review Weapons policy" }));
  expect(review).toHaveBeenCalledWith("weapon_population_save", expect.objectContaining({
    document: expect.objectContaining({ enabled: true, replacement_chance: 0.5,
      entries: [expect.objectContaining({ enabled: true, weight: 1 })] }),
    expected_document_sha256: hash("b"),
  }));
  // The parent owns confirmation/apply; model its successful fresh inspection.
  persisted.weapon_population.document = review.mock.calls[0][1].document;
  persisted.weapon_population.document_sha256 = hash("c");
  view.unmount();
  render(<Harness injectedClient={service} />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  expect(screen.getByRole("checkbox", { name: "Enable same-tier weapon replacement" })).toBeChecked();
  expect(screen.getByRole("spinbutton", { name: "Weapons replacement chance percent" })).toHaveValue(50);
  expect(screen.getAllByRole("slider")[0]).toHaveValue("0.5");
  expect(screen.getByRole("button", { name: "Review Weapons policy" })).toBeDisabled();
});

it("normalizes legacy weapon policies and preserves the mission choice through master toggles and review", async () => {
  const user = userEvent.setup(), review = vi.fn();
  const legacy = snapshot("weapon_manager") as RecordData;
  delete ((legacy.weapon_population as RecordData).document as RecordData).active_during_missions;
  const service = { ...client(), request: vi.fn(async () => structuredClone(legacy)) } as unknown as Client;
  render(<Harness injectedClient={service} reviewed={review} />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  const missionToggle = screen.getByRole("checkbox", { name: "Active during story missions" });
  expect(missionToggle).not.toBeChecked();
  expect(missionToggle).toBeDisabled();
  await user.click(screen.getByRole("checkbox", { name: "Enable same-tier weapon replacement" }));
  await user.click(missionToggle);
  await user.click(missionToggle);
  await user.click(screen.getByRole("button", { name: "Review Weapons policy" }));
  expect(review).toHaveBeenLastCalledWith("weapon_population_save", expect.objectContaining({
    document: expect.objectContaining({ enabled: true, active_during_missions: false }),
  }));
  await user.click(missionToggle);
  await user.click(screen.getByRole("checkbox", { name: "Enable same-tier weapon replacement" }));
  expect(missionToggle).toBeDisabled();
  expect(missionToggle).toBeChecked();
  await user.click(screen.getByRole("checkbox", { name: "Enable same-tier weapon replacement" }));
  await user.click(screen.getByRole("button", { name: "Review Weapons policy" }));
  expect(review).toHaveBeenLastCalledWith("weapon_population_save", expect.objectContaining({
    document: expect.objectContaining({ enabled: true, active_during_missions: true }),
  }));
  expect(screen.getByText("When enabled, weapon replacement can continue during story missions. This does not alter protected story characters; wanted levels do not pause weapon replacement.")).toBeInTheDocument();
});

it("keeps the mission toggle weapon-only and locks it with the rest of the policy", async () => {
  const user = userEvent.setup();
  const { unmount } = render(<Harness kind="ped" />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  expect(screen.queryByRole("checkbox", { name: "Active during story missions" })).not.toBeInTheDocument();
  unmount();
  render(<Harness kind="traffic" />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  expect(screen.queryByRole("checkbox", { name: "Active during story missions" })).not.toBeInTheDocument();
  unmount();
  const view = render(<Harness injectedClient={client()} />);
  await user.click(screen.getByRole("button", { name: "Load authorized catalog" }));
  await user.click(screen.getByRole("checkbox", { name: "Enable same-tier weapon replacement" }));
  view.rerender(<Harness injectedClient={client()} locked />);
  expect(screen.getByRole("checkbox", { name: "Active during story missions" })).toBeDisabled();
});
