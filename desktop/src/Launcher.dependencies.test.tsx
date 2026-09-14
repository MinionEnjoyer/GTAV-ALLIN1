import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import type { Client, RecordData } from "./client";

const config = {
  general: {
    target_edition: "enhanced",
    gta_legacy_path: "",
    gta_enhanced_path: "D:/Synthetic GTA V Enhanced",
  },
};

function setupInspection(
  status: RecordData,
  reactor?: RecordData,
  responseFor?: (payload: RecordData) => RecordData,
) {
  const client: Client = {
    request: vi.fn(async (operation, payload = {}) => {
      if (operation === "catalog") return { desktop_version: "0.6.5" };
      if (operation === "inspect") {
        expect(payload).toMatchObject({ module: "setup" });
        return responseFor
          ? responseFor(payload)
          : {
              config: payload.config ?? config,
              status,
              ...(reactor === undefined ? {} : { reactor }),
            };
      }
      throw new Error(`Setup dependency view must not call ${operation}`);
    }),
    selectPath: vi.fn(async () => null),
    onClose: vi.fn(async () => () => {}),
    onHandoff: vi.fn(async () => () => {}),
    onProgress: vi.fn(async () => () => {}),
    close: vi.fn(async () => {}),
  };
  render(<App client={client} />);
  return client;
}

async function dependencies() {
  return screen.findByRole("region", { name: "Installation dependencies" });
}

function pill(group: HTMLElement, label: string) {
  const card = within(group).getByText(label).parentElement;
  if (!card) throw new Error(`Dependency card not found for ${label}`);
  const value = card.querySelector("strong");
  if (!value) throw new Error(`Dependency status not found for ${label}`);
  return value;
}

describe("Setup installation dependency preflight", () => {
  it("does not claim a Reactor installation before a valid game is inspected", async () => {
    const client = setupInspection(
      { valid_game: false, edition: "enhanced", openrpf_installed: false },
      { available: true, reason: "This stale result must not become Installed." },
    );
    const group = await dependencies();

    for (const label of ["Reactor V", "ALLIN1 client", "ScriptHookV", "ScriptHookVDotNet", "OpenRPF"]) {
      expect(pill(group, label)).toHaveTextContent("Not checked");
      expect(pill(group, label)).toHaveClass("neutral");
    }
    expect(screen.queryByText("This stale result must not become Installed.")).not.toBeInTheDocument();
    expect(vi.mocked(client.request).mock.calls.map(([operation]) => operation)).toEqual(["catalog", "inspect"]);
  });

  it("shows Reactor alongside ordinary dependencies when the selected game is installed and inspected", async () => {
    const client = setupInspection(
      {
        valid_game: true,
        edition: "enhanced",
        mod_installed: true,
        scripthookv_installed: true,
        shvdn_installed: true,
        openrpf_installed: true,
      },
      { available: true },
    );
    const group = await dependencies();

    expect(pill(group, "Reactor V")).toHaveTextContent("Installed");
    expect(pill(group, "Reactor V")).toHaveClass("status-pill", "success");
    expect(pill(group, "OpenRPF")).toHaveTextContent("Installed");
    expect(pill(group, "OpenRPF")).toHaveClass("status-pill", "success");
    expect(vi.mocked(client.request).mock.calls.map(([operation]) => operation)).toEqual(["catalog", "inspect"]);
  });

  it("keeps an explicit missing Reactor reason actionable without presenting it as runtime state", async () => {
    const client = setupInspection(
      {
        valid_game: true,
        edition: "enhanced",
        mod_installed: true,
        scripthookv_installed: true,
        shvdn_installed: true,
        openrpf_installed: false,
      },
      { available: false, reason: "Reactor V files are incomplete." },
    );
    const group = await dependencies();

    expect(pill(group, "Reactor V")).toHaveTextContent("Missing");
    expect(pill(group, "Reactor V")).toHaveClass("warning");
    expect(pill(group, "OpenRPF")).toHaveTextContent("Missing");
    expect(pill(group, "OpenRPF")).toHaveClass("warning");
    expect(screen.getByText(/Reactor V files are incomplete\. GBAY requires Reactor V; use Install \/ Repair below\./)).toBeInTheDocument();
    expect(screen.getByText(/This is not an in-game runtime check\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review Install / Repair" })).toBeEnabled();
    expect(vi.mocked(client.request).mock.calls.map(([operation]) => operation)).toEqual(["catalog", "inspect"]);
  });

  it("treats unavailable dependency evidence as not checked rather than missing", async () => {
    const client = setupInspection(
      { valid_game: true, edition: "enhanced", mod_installed: "unknown", openrpf_installed: 1 },
      { available: "unavailable" },
    );
    const group = await dependencies();

    for (const label of ["Reactor V", "ALLIN1 client", "ScriptHookV", "ScriptHookVDotNet", "OpenRPF"]) {
      expect(pill(group, label)).toHaveTextContent("Not checked");
      expect(pill(group, label)).toHaveClass("neutral");
    }
    expect(vi.mocked(client.request).mock.calls.map(([operation]) => operation)).toEqual(["catalog", "inspect"]);
  });

  it("does not retain an Installed result while the selected game changes before Refresh", async () => {
    const client = setupInspection(
      {
        valid_game: true,
        edition: "enhanced",
        mod_installed: true,
        scripthookv_installed: true,
        shvdn_installed: true,
        openrpf_installed: true,
      },
      { available: true },
    );
    const group = await dependencies();
    expect(pill(group, "Reactor V")).toHaveTextContent("Installed");

    await userEvent.setup().selectOptions(
      screen.getByRole("combobox", { name: "Target Edition" }),
      "legacy",
    );
    await waitFor(() => expect(pill(group, "Reactor V")).toHaveTextContent("Not checked"));
    expect(pill(group, "OpenRPF")).toHaveTextContent("Not checked");
    expect(vi.mocked(client.request).mock.calls.map(([operation]) => operation)).toEqual(["catalog", "inspect"]);
  });

  it("clears a same-edition folder's stale result until Refresh adopts its inspected evidence", async () => {
    const installed = {
      valid_game: true,
      edition: "enhanced",
      mod_installed: true,
      scripthookv_installed: true,
      shvdn_installed: true,
      openrpf_installed: true,
    };
    const client = setupInspection(installed, { available: true }, (payload) => {
      const inspectedConfig = payload.config ?? config;
      const changedFolder = inspectedConfig.general.gta_enhanced_path === "D:/Other GTA V Enhanced";
      return {
        config: inspectedConfig,
        status: changedFolder
          ? { ...installed, openrpf_installed: false }
          : installed,
        reactor: changedFolder
          ? { available: false, reason: "Reactor V is absent from this folder." }
          : { available: true },
      };
    });
    vi.mocked(client.selectPath).mockResolvedValue("D:/Other GTA V Enhanced");
    const group = await dependencies();
    expect(pill(group, "Reactor V")).toHaveTextContent("Installed");

    await userEvent.setup().click(
      screen.getByRole("button", { name: "Choose Enhanced folder" }),
    );
    await waitFor(() => expect(pill(group, "Reactor V")).toHaveTextContent("Not checked"));
    expect(pill(group, "OpenRPF")).toHaveTextContent("Not checked");

    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(pill(group, "Reactor V")).toHaveTextContent("Missing"));
    expect(pill(group, "OpenRPF")).toHaveTextContent("Missing");
    expect(screen.getByText(/Reactor V is absent from this folder\./)).toBeInTheDocument();
    expect(vi.mocked(client.request).mock.calls.map(([operation]) => operation)).toEqual([
      "catalog",
      "inspect",
      "inspect",
    ]);
  });
});
