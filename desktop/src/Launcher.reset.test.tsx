import { describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import type { Client, RecordData } from "./client";

function fixture(edition = "legacy") {
  const config = { general: {
    target_edition: edition,
    gta_legacy_path: "D:/Legacy",
    gta_enhanced_path: "D:/Enhanced",
  } };
  const snapshot = (values: RecordData, module: string) => {
    const selectedEdition = values.general.target_edition;
    return {
      config: values, module, status: { edition: selectedEdition },
      installed: [{ mod_id: selectedEdition, name: `${selectedEdition} package`, version: "1", enabled: true }],
      packages: [{ mod_id: selectedEdition, name: `${selectedEdition} library`, manifest_path: `${selectedEdition}/mod.toml` }],
      content: [{ id: selectedEdition, name: `${selectedEdition} content`, installed: true,
        enabled: true, managed_package: true, source: "managed package", settings: { enabled: true },
        systems: [{ id: "package", name: "Package configuration", settings: [{ key: "enabled", label: "Enabled", default: true }] }],
      }],
    };
  };
  let nextInspect: Promise<RecordData> | undefined;
  const client: Client = {
    request: vi.fn(async (operation, payload = {}) => {
      if (operation === "catalog") return { desktop_version: "0.6.5" };
      if (operation !== "inspect") throw new Error(`Unexpected operation: ${operation}`);
      if (nextInspect) {
        const result = nextInspect;
        nextInspect = undefined;
        return result;
      }
      return snapshot(payload.config ?? config, payload.module);
    }),
    selectPath: vi.fn(async () => null),
    onClose: vi.fn(async () => () => {}),
    onHandoff: vi.fn(async () => () => {}),
    onProgress: vi.fn(async () => () => {}),
    close: vi.fn(async () => {}),
  };
  return { client, config, snapshot, holdInspect: (result: Promise<RecordData>) => { nextInspect = result; } };
}

const workspaces = [{ name: "Packages", module: "mods" }, { name: "Content", module: "content" }];
const idle = () => waitFor(() => expect(screen.queryByText("Working…")).not.toBeInTheDocument());
const entry = (module: string, edition: string) => screen.queryByRole("button", {
  name: module === "mods" ? `Uninstall ${edition} package` : `${edition} content Installed`,
});

describe("Reset draft inspection", () => {
  for (const { name, module } of workspaces) {
    for (const edition of ["legacy", "enhanced"]) {
      it(`restores ${edition} ${name} without exposing the previous edition while inspecting`, async () => {
        const test = fixture(edition);
        const other = edition === "legacy" ? "enhanced" : "legacy";
        const user = userEvent.setup();
        render(<App client={test.client} />);
        await screen.findByRole("combobox", { name: "Target Edition" });
        await idle();
        await user.selectOptions(screen.getByRole("combobox", { name: "Target Edition" }), other);
        await user.click(screen.getByRole("button", { name }));
        await waitFor(() => expect(entry(module, other)).toBeEnabled());

        let resolve!: (value: RecordData) => void;
        test.holdInspect(new Promise((done) => { resolve = done; }));
        await user.click(screen.getByRole("button", { name: "Reset draft" }));
        expect(test.client.request).toHaveBeenLastCalledWith("inspect", { module, config: test.config });
        expect(entry(module, other)).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: `Install ${other} library` })).not.toBeInTheDocument();
        expect(screen.getByText("Working…")).toBeVisible();
        expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
        expect(screen.queryByRole("checkbox", { name: "Enabled" })).not.toBeInTheDocument();

        await act(async () => resolve(test.snapshot(test.config, module)));
        await waitFor(() => expect(entry(module, edition)).toBeEnabled());
        expect(entry(module, other)).not.toBeInTheDocument();
        expect(screen.getByText(`ALLIN1 / ${edition}`)).toBeVisible();
        expect(screen.getByText("Ready")).toBeVisible();
        if (module === "content") expect(screen.getByRole("checkbox", { name: "Enabled" })).toBeChecked();
        expect(vi.mocked(test.client.request).mock.calls.every(([operation]) => ["catalog", "inspect"].includes(operation))).toBe(true);
      });
    }

    it(`keeps stale ${name} actions hidden if reset inspection fails and supports Refresh`, async () => {
      const test = fixture();
      const user = userEvent.setup();
      render(<App client={test.client} />);
      await screen.findByRole("combobox", { name: "Target Edition" });
      await idle();
      await user.selectOptions(screen.getByRole("combobox", { name: "Target Edition" }), "enhanced");
      await user.click(screen.getByRole("button", { name }));
      await waitFor(() => expect(entry(module, "enhanced")).toBeEnabled());

      let reject!: (reason: Error) => void;
      test.holdInspect(new Promise((_resolve, fail) => { reject = fail; }));
      await user.click(screen.getByRole("button", { name: "Reset draft" }));
      expect(entry(module, "enhanced")).not.toBeInTheDocument();
      await act(async () => reject(new Error("Inspection unavailable")));
      await screen.findByRole("alert");
      await idle();
      expect(screen.getByRole("alert")).toHaveTextContent("Inspection unavailable");
      expect(entry(module, "enhanced")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Install enhanced library" })).not.toBeInTheDocument();
      expect(screen.queryByRole("checkbox", { name: "Enabled" })).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Refresh" }));
      await waitFor(() => expect(entry(module, "legacy")).toBeEnabled());
      expect(test.client.request).toHaveBeenLastCalledWith("inspect", { module, config: test.config });
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(vi.mocked(test.client.request).mock.calls.every(([operation]) => ["catalog", "inspect"].includes(operation))).toBe(true);
    });
  }
});
