import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  render,
  screen,
  waitFor,
  within,
  cleanup,
  act,
  fireEvent,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";
import { mkdtemp, readFile, rm, access, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import App from "./App";
import type { Client, RecordData } from "./client";

let root: string,
  child: ChildProcessWithoutNullStreams,
  client: Client,
  serial = 0;
let closeHandler: () => void,
  progressHandler: (event: RecordData) => void,
  handoffHandler: (event: RecordData) => void;
const pending = new Map<
  string,
  { resolve: (value: RecordData) => void; reject: (reason: unknown) => void }
>();
const user = () => userEvent.setup();
const idle = () =>
  waitFor(() => expect(screen.queryByText("Working…")).not.toBeInTheDocument());
async function navigate(name: string) {
  await user().click(
    within(screen.getByRole("navigation", { name: "Primary" })).getByRole(
      "button",
      { name: new RegExp(name) },
    ),
  );
  await screen.findByRole("heading", { name, level: 1 });
  await idle();
}
async function approve() {
  const review = await screen.findByRole("region", { name: "Review changes" });
  await user().click(
    within(review).getByRole("checkbox", { name: "I reviewed these changes" }),
  );
  await user().click(
    within(review).getByRole("button", { name: "Apply reviewed changes" }),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("region", { name: "Review changes" }),
    ).not.toBeInTheDocument(),
  );
  await idle();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
}
beforeEach(async () => {
  localStorage.clear();
  root = await mkdtemp(path.join(tmpdir(), "allin1-react-test-"));
  const project = path.resolve("..");
  const python =
    process.env.ALLIN1_TEST_PYTHON ||
    path.join(
      project,
      ".venv",
      process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
    );
  child = spawn(
    python,
    ["-u", path.join(project, "tests/desktop_fixture_host.py"), root],
    {
      windowsHide: true,
      stdio: "pipe",
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    },
  );
  let stderr = "";
  child.stderr.on("data", (value) => {
    stderr = (stderr + value.toString()).slice(-8192);
  });
  child.on("exit", () => {
    for (const item of pending.values())
      item.reject(new Error(`Fixture exited: ${stderr}`));
    pending.clear();
  });
  createInterface({ input: child.stdout }).on("line", (line) => {
    const response = JSON.parse(line);
    const item = pending.get(response.request_id);
    if (response.kind === "progress") {
      progressHandler?.(response.payload);
      return;
    }
    pending.delete(response.request_id);
    if (response.kind === "error")
      item?.reject(new Error(response.payload.message));
    else item?.resolve(response.payload);
  });
  client = {
    request: (operation, payload = {}) =>
      new Promise((resolve, reject) => {
        const id = `react-${++serial}`;
        pending.set(id, { resolve, reject });
        child.stdin.write(
          JSON.stringify({
            schema_version: 1,
            request_id: id,
            operation,
            payload,
          }) + "\n",
        );
      }),
    selectPath: vi.fn(async () => null),
    close: vi.fn(async () => {}),
    onClose: async (handler) => {
      closeHandler = handler;
      return () => {};
    },
    onHandoff: async (handler) => {
      handoffHandler = handler;
      return () => {};
    },
    onProgress: async (handler) => {
      progressHandler = handler;
      return () => {};
    },
  };
  render(<App client={client} />);
  await screen.findByRole(
    "textbox",
    { name: "GTA Enhanced Path" },
    { timeout: 15000 },
  );
  await idle();
});
afterEach(async () => {
  cleanup();
  child.stdin.end();
  await new Promise<void>((resolve) => {
    if (child.exitCode !== null) resolve();
    else child.once("exit", () => resolve());
  });
  await rm(root, { recursive: true, force: true });
});

describe("Launcher React workspaces use the real Python boundary", () => {
  it("requires Reactor and hides retired backend and preview controls", async () => {
    await screen.findByRole("heading", { name: "Setup", level: 1 });
    await idle();
    expect(screen.getByText("Reactor V · Required")).toBeInTheDocument();
    expect(screen.queryByLabelText("Enable RPF Previews")).not.toBeInTheDocument();
    await navigate("Gameplay");
    expect(screen.queryByLabelText("GBAY Ui Backend")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("GBAY Menu Enabled")).not.toBeInTheDocument();
  });
  it("reviews client removal and preserves character garage and preference files", async () => {
    const scripts = path.join(root, "Synthetic game with spaces/scripts");
    // Structural status fixture only; never load this nonfunctional PE file.
    const binary = Buffer.alloc(4096);
    binary.write("MZ"); binary.writeUInt32LE(128, 60); binary.write("PE\0\0", 128); binary.writeUInt16LE(0x8664, 132);
    const dll = path.join(scripts, "ALLIN1.dll"); await writeFile(dll, binary);
    const saves = {
      "ALLIN1_characters.json": '{"michael":{"user_note":"keep"}}',
      "ALLIN1_garage.json": '{"michael":[],"franklin":[],"trevor":[]}',
      "ALLIN1_gbay_preferences.json": '{"sort":"name"}',
      "ALLIN1.toml": "# saved preferences\n",
    };
    for (const [name, content] of Object.entries(saves)) await writeFile(path.join(scripts, name), content);
    await user().click(screen.getByRole("button", { name: "Refresh" })); await idle();
    await user().click(screen.getByRole("button", { name: "Review uninstall" }));
    const review = await screen.findByRole("region", { name: "Review changes" });
    expect(review).toHaveTextContent("not a data purge");
    expect(await readFile(dll)).toEqual(binary);
    await approve();
    await expect(access(dll)).rejects.toThrow();
    for (const [name, content] of Object.entries(saves)) expect(await readFile(path.join(scripts, name), "utf8")).toBe(content);
  });
  it("reconnects without replaying an interrupted save or discarding its draft", async () => {
    const field = screen.getByRole("textbox", { name: "GTA Enhanced Path" });
    await user().clear(field);
    await user().type(field, "C:\\my unsaved game");
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    const review = await screen.findByRole("region", { name: "Review changes" });
    const request = client.request;
    let applies = 0;
    client.request = async (operation, payload) => {
      if (operation === "apply") { applies++; throw new Error("Service connection interrupted"); }
      if (operation === "reconnect_service") return { reconnected: true, replayed: false };
      return request(operation, payload);
    };
    await user().click(within(review).getByRole("checkbox", { name: "I reviewed these changes" }));
    await user().click(within(review).getByRole("button", { name: "Apply reviewed changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Service connection interrupted");
    await user().click(screen.getByRole("button", { name: "Reconnect service" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Review changes" })).not.toBeInTheDocument());
    await idle();
    expect(field).toHaveValue("C:\\my unsaved game");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("No action was replayed");
    expect(applies).toBe(1);
    await expect(access(path.join(root, "state/config.toml"))).rejects.toThrow();
  });
  it("preserves the draft without retrying when reconnect refuses an uncertain writer", async () => {
    await user().type(screen.getByRole("combobox", { name: "Profile name" }), "Recovery test");
    await user().click(screen.getByRole("button", { name: "Save profile" }));
    const review = await screen.findByRole("region", { name: "Review changes" });
    const request = client.request;
    client.request = async (operation, payload) => {
      if (operation === "apply") throw new Error("Service connection interrupted");
      if (operation === "reconnect_service") throw new Error("Cannot terminate an uncertain writer");
      return request(operation, payload);
    };
    await user().click(within(review).getByRole("checkbox", { name: "I reviewed these changes" }));
    await user().click(within(review).getByRole("button", { name: "Apply reviewed changes" }));
    await screen.findByRole("alert");
    await user().click(screen.getByRole("button", { name: "Reconnect service" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot terminate an uncertain writer");
    expect(screen.queryByRole("region", { name: "Review changes" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Profile name" })).toHaveValue("Recovery test");
    await expect(access(path.join(root, "state/profiles"))).rejects.toThrow();
  });
  it("supports legacy application shortcuts without bypassing review or draft guards", async () => {
    fireEvent.keyDown(window, { key: "b", ctrlKey: true });
    expect(screen.getByRole("button", { name: "Expand navigation" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "b", ctrlKey: true });
    fireEvent.keyDown(window, { key: "Tab", ctrlKey: true });
    await screen.findByRole("heading", { name: "Gameplay", level: 1 }); await idle();
    fireEvent.keyDown(window, { key: "Tab", ctrlKey: true, shiftKey: true });
    await screen.findByRole("heading", { name: "Setup", level: 1 }); await idle();
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await screen.findByRole("region", { name: "Review changes" });
    await expect(access(path.join(root, "state/config.toml"))).rejects.toThrow();
    await approve();
    fireEvent.keyDown(window, { key: "l", ctrlKey: true });
    expect(await screen.findByRole("alert")).toHaveTextContent("launch authority");
    await navigate("Characters");
    await user().type(screen.getByRole("spinbutton", { name: "Money" }), "9");
    fireEvent.keyDown(window, { key: "F5" });
    expect(screen.getByRole("alert")).toHaveTextContent("workspace draft");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });
  it("shows a readable manual-download release result without installing anything", async () => {
    await navigate("Activity");
    await user().click(screen.getByRole("button", { name: "Check for updates" }));
    const release = await screen.findByRole("region", { name: "Launcher release information" });
    expect(release).toHaveTextContent("Current 0.6.4 · Latest 0.6.5");
    expect(release).toHaveTextContent("unsigned manual downloads");
    expect(within(release).getByRole("button", { name: "Open official release page" })).toBeEnabled();
    await expect(access(path.join(root, "state"))).rejects.toThrow();
  });
  it("does not rebase a garage draft when another save refreshes changed files", async () => {
    await navigate("Characters");
    await user().click(screen.getByRole("button", { name: "Garages" }));
    await user().click(screen.getByRole("button", { name: "Add garage vehicle" }));
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
    await user().click(screen.getByRole("button", { name: "Progress" }));
    await user().type(screen.getByRole("spinbutton", { name: "Money" }), "8");
    await user().click(screen.getByRole("button", { name: "Review character save" }));
    const request = client.request;
    const target = path.join(root, "Synthetic game with spaces/scripts/ALLIN1_garage.json");
    const external = '{"michael":[],"franklin":[],"trevor":[],"external_note":"preserve"}';
    client.request = async (operation, payload) => {
      if (operation === "inspect" && payload?.module === "characters") await writeFile(target, external);
      return request(operation, payload);
    };
    await approve();
    await user().click(screen.getByRole("button", { name: "Garages" }));
    await user().click(screen.getByRole("button", { name: "Review garage save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Character files changed");
    expect(await readFile(target, "utf8")).toBe(external);
    expect(screen.getByRole("button", { name: "Remove garage slot 0" })).toBeInTheDocument();
  });
  it("copies visible activity and clearing the view preserves the structured journal", async () => {
    await user().type(screen.getByRole("combobox", { name: "Profile name" }), "Activity test");
    await user().click(screen.getByRole("button", { name: "Save profile" }));
    await approve();
    await navigate("Activity");
    const interaction = user();
    const clipboard = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const journalPath = path.join(root, "state/logs/activity.json");
    const before = await readFile(journalPath, "utf8");
    expect(JSON.parse(before).events[0].action).toBe("save_profile");
    await interaction.click(screen.getByRole("button", { name: "Copy activity" }));
    expect(clipboard).toHaveBeenCalledWith(expect.stringContaining("Save Profile completed"));
    await user().click(screen.getByRole("button", { name: "Clear visible activity" }));
    expect(screen.getByLabelText("Activity log")).toHaveTextContent("No activity in this session");
    expect(await readFile(journalPath, "utf8")).toBe(before);
    clipboard.mockRestore();
  });
  it("configures and manages a local assistant pack independently of the SDK", async () => {
    await navigate("SDK Manager");
    const panel = within(screen.getByRole("region", { name: "Optional assistant" }));
    await user().click(panel.getByRole("button", { name: "Check assistant hardware" }));
    expect(await panel.findByLabelText("Assistant hardware assessment")).toHaveTextContent("Hardware check passed");
    vi.mocked(client.selectPath).mockResolvedValue(path.join(root, "project/assistant-fixture.zip"));
    await user().click(panel.getByRole("button", { name: "Import assistant pack" }));
    await approve();
    expect(panel.getByText(/ALLIN1 Test Model .* is ready/)).toBeInTheDocument();
    await user().selectOptions(panel.getByRole("combobox", { name: "Assistant mode" }), "managed_local");
    await user().click(panel.getByRole("button", { name: "Review assistant settings" }));
    await approve();
    expect(JSON.parse(await readFile(path.join(root, "state/Assistant/config.json"), "utf8")).mode).toBe("managed_local");
    await user().click(panel.getByRole("button", { name: "Remove managed assistant pack" }));
    await approve();
    expect(JSON.parse(await readFile(path.join(root, "state/Assistant/config.json"), "utf8")).mode).toBe("disabled");
    await expect(access(path.join(root, "state/Assistant/component"))).rejects.toThrow();
    await expect(access(path.join(root, "state/SDK"))).rejects.toThrow();
  });
  it("edits initial package settings and manages installed third-party content", async () => {
    await navigate("Packages");
    expect(screen.getByText("ALLIN1 Colored Smoke Grenades")).toBeInTheDocument();
    await user().click(screen.getByRole("button", { name: "Install Test acme.react-content" }));
    const strength = await screen.findByRole("spinbutton", { name: "Strength" });
    expect(strength).toHaveAttribute("max", "5");
    await user().clear(strength);
    await user().type(strength, "4");
    await expect(access(path.join(root, "Synthetic game with spaces/scripts/acme.react-content/content.json"))).rejects.toThrow();
    await user().click(screen.getByRole("button", { name: "Review package installation" }));
    await approve();
    await navigate("Content");
    await user().click(screen.getByRole("button", { name: /Test acme.react-content/ }));
    expect(screen.getByRole("spinbutton", { name: "Strength" })).toHaveValue(4);
    await user().click(screen.getByRole("button", { name: "Review disable" }));
    await approve();
    await expect(access(path.join(root, "Synthetic game with spaces/scripts/acme.react-content/content.json"))).rejects.toThrow();
    await user().click(screen.getByRole("button", { name: "Review enable" }));
    await approve();
    await access(path.join(root, "Synthetic game with spaces/scripts/acme.react-content/content.json"));
  });
  it("saves preinstall content preferences without installing a package", async () => {
    await navigate("Content");
    await user().click(screen.getByRole("button", { name: /ALLIN1 Online Content/ }));
    const setting = screen.getByRole("checkbox", { name: "Free GBAY purchases" });
    const before = (setting as HTMLInputElement).checked;
    await user().click(setting);
    await user().click(screen.getByRole("button", { name: "Review preinstall preferences" }));
    await approve();
    expect(await readFile(path.join(root, "state/config.toml"), "utf8")).toContain(`gbay_free_mode = ${!before}`);
    await expect(access(path.join(root, "Synthetic game with spaces/scripts/ALLIN1.toml"))).rejects.toThrow();
    expect(screen.getByRole("button", { name: "Review enable" })).toBeDisabled();
  });
  it("imports previous preferences only after review and preserves the old folder", async () => {
    const previous = path.join(root, "previous launcher");
    await mkdir(path.join(previous, "profiles"), { recursive: true });
    const config = '[script]\nui_scale = 1.3\n';
    await writeFile(path.join(previous, "config.toml"), config);
    await writeFile(path.join(previous, "profiles/Weekend.toml"), config);
    vi.mocked(client.selectPath).mockResolvedValue(previous);
    await user().click(screen.getByRole("button", { name: "Import previous Launcher preferences" }));
    expect(await screen.findByLabelText("Preference import plan")).toHaveTextContent("Copy 2");
    await expect(access(path.join(root, "state/config.toml"))).rejects.toThrow();
    await user().click(screen.getByRole("button", { name: "Back to draft" }));
    await expect(access(path.join(root, "state/config.toml"))).rejects.toThrow();
    await user().click(screen.getByRole("button", { name: "Import previous Launcher preferences" }));
    await approve();
    expect(await readFile(path.join(root, "state/config.toml"), "utf8")).toBe(config);
    expect(await readFile(path.join(previous, "config.toml"), "utf8")).toBe(config);
    await navigate("Input");
    expect(screen.getByRole("spinbutton", { name: "Ui Scale" })).toHaveValue(1.3);
  });
  it("keeps the selected content draft and error visible after failed application", async () => {
    await navigate("Content");
    await user().click(screen.getByRole("button", { name: /ALLIN1 Experimental Gameplay/ }));
    await user().click(screen.getByRole("checkbox", { name: "GTA IV-style NPC physics" }));
    await user().click(screen.getByRole("button", { name: "Review content settings" }));
    const review = await screen.findByRole("region", { name: "Review changes" });
    await writeFile(path.join(root, "Synthetic game with spaces/scripts/ALLIN1.toml"), "# changed after review\n");
    await user().click(within(review).getByRole("checkbox", { name: "I reviewed these changes" }));
    await user().click(within(review).getByRole("button", { name: "Apply reviewed changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Files changed");
    expect(screen.getByRole("checkbox", { name: "GTA IV-style NPC physics" })).toBeChecked();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await expect(access(path.join(root, "state/config.toml"))).rejects.toThrow();
  });
  for (const name of [
    "Setup",
    "Gameplay",
    "Content",
    "Input",
    "Packages",
    "Characters",
    "SDK Manager",
    "Activity",
    "Help Center",
  ]) {
    it(`opens ${name} without an error or a write`, async () => {
      await navigate(name);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      await expect(access(path.join(root, "state"))).rejects.toThrow();
    });
  }
  it("saves settings and named profiles after explicit review", async () => {
    await navigate("Input");
    const field = screen.getByRole("spinbutton", { name: "Ui Scale" });
    await user().clear(field);
    await user().type(field, "1.25");
    await user().click(
      screen.getByRole("button", { name: "Review save settings" }),
    );
    await approve();
    expect(
      await readFile(path.join(root, "state/config.toml"), "utf8"),
    ).toContain("ui_scale = 1.25");
    await navigate("Setup");
    await user().type(
      screen.getByRole("combobox", { name: "Profile name" }),
      "React QA",
    );
    await user().click(screen.getByRole("button", { name: "Save profile" }));
    await approve();
    expect(
      await readFile(path.join(root, "state/profiles/React QA.toml"), "utf8"),
    ).toContain("ui_scale = 1.25");
  });
  it("saves character money and garage vehicles to the synthetic game", async () => {
    await navigate("Characters");
    const money = screen.getByRole("spinbutton", { name: "Money" });
    await user().clear(money);
    await user().type(money, "12345");
    await user().click(
      screen.getByRole("button", { name: "Review character save" }),
    );
    await approve();
    const saved = JSON.parse(
      await readFile(
        path.join(
          root,
          "Synthetic game with spaces/scripts/ALLIN1_characters.json",
        ),
        "utf8",
      ),
    );
    expect(saved.michael.progress.money).toBe(12345);
    await user().click(screen.getByRole("button", { name: "Garages" }));
    await user().click(
      screen.getByRole("button", { name: "Add garage vehicle" }),
    );
    await user().click(
      screen.getByRole("button", { name: "Review garage save" }),
    );
    await approve();
    const garages = JSON.parse(
      await readFile(
        path.join(
          root,
          "Synthetic game with spaces/scripts/ALLIN1_garage.json",
        ),
        "utf8",
      ),
    );
    expect(garages.michael).toHaveLength(1);
  });
  it("imports, disables, enables and uninstalls an actual fixture package", async () => {
    await navigate("Packages");
    vi.mocked(client.selectPath).mockResolvedValue(
      path.join(root, "project/mods/catalog/react-fixture/mod.toml"),
    );
    await user().click(
      screen.getByRole("button", { name: "Review package import" }),
    );
    await user().click(await screen.findByRole("button", { name: "Review package installation" }));
    await approve();
    const target = path.join(
      root,
      "Synthetic game with spaces/scripts/react-fixture.ini",
    );
    expect(await readFile(target, "utf8")).toContain("fixture = true");
    await user().click(
      screen.getByRole("button", { name: "Disable React fixture" }),
    );
    await approve();
    await expect(access(target)).rejects.toThrow();
    await user().click(
      screen.getByRole("button", { name: "Enable React fixture" }),
    );
    await approve();
    await access(target);
    await user().click(
      screen.getByRole("button", { name: "Uninstall React fixture" }),
    );
    await approve();
    await expect(access(target)).rejects.toThrow();
  });
  it("guards dirty native close and flips collapsed navigation", async () => {
    await user().click(
      screen.getByRole("button", { name: "Collapse navigation" }),
    );
    expect(
      screen.getByRole("button", { name: "Expand navigation" }),
    ).toHaveTextContent("›");
    await user().click(
      screen.getByRole("button", { name: "Expand navigation" }),
    );
    await navigate("Characters");
    await user().type(screen.getByRole("spinbutton", { name: "Money" }), "5");
    closeHandler();
    await screen.findByRole("alert");
    expect(client.close).not.toHaveBeenCalled();
    await user().click(screen.getByRole("button", { name: "Reset draft" }));
    closeHandler();
    await waitFor(() => expect(client.close).toHaveBeenCalledOnce());
  });
  it("keeps an unsaved garage draft when character changes are saved", async () => {
    await navigate("Characters");
    await user().click(screen.getByRole("button", { name: "Garages" }));
    await user().click(
      screen.getByRole("button", { name: "Add garage vehicle" }),
    );
    await user().click(
      screen.getByRole("button", { name: "Progress" }),
    );
    await user().type(screen.getByRole("spinbutton", { name: "Money" }), "6");
    await user().click(
      screen.getByRole("button", { name: "Review character save" }),
    );
    await approve();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await user().click(screen.getByRole("button", { name: "Garages" }));
    expect(
      screen.getByRole("button", { name: "Review garage save" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Remove garage slot 0" }),
    ).toBeInTheDocument();
    await user().click(
      screen.getByRole("button", { name: "Review garage save" }),
    );
    await approve();
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
  });
  it("saves content-owned settings and adopts their persisted configuration bindings", async () => {
    await navigate("Content");
    await user().click(
      screen.getByRole("button", { name: /ALLIN1 Experimental Gameplay/ }),
    );
    await user().click(
      screen.getByRole("checkbox", { name: "GTA IV-style NPC physics" }),
    );
    await user().click(
      screen.getByRole("button", { name: "Review content settings" }),
    );
    await approve();
    const saved = await readFile(path.join(root, "state/config.toml"), "utf8");
    expect(saved).toContain("gta_iv_npc_physics = true");
    await navigate("Gameplay");
    expect(
      screen.getByRole("checkbox", { name: "GTA Iv Npc Physics" }),
    ).toBeChecked();
    await navigate("Content");
    for (const action of ["disable", "enable"]) {
      await user().click(
        screen.getByRole("button", { name: /ALLIN1 Experimental Gameplay/ }),
      );
      await user().click(
        screen.getByRole("button", { name: `Review ${action}` }),
      );
      await approve();
    }
  });
  it("installs and removes a validated SDK archive without launching its synthetic binaries", async () => {
    await navigate("SDK Manager");
    vi.mocked(client.selectPath).mockResolvedValue(
      path.join(root, "project/SDK-fixture.zip"),
    );
    await user().click(
      screen.getByRole("button", { name: "Install SDK archive" }),
    );
    await approve();
    await access(path.join(root, "state/SDK/allin1-sdk-desktop.exe"));
    expect(
      screen.getByRole("button", { name: "Open SDK" }),
    ).toBeEnabled();
    await user().click(screen.getByRole("button", { name: "Uninstall SDK" }));
    await approve();
    await expect(
      access(path.join(root, "state/SDK/allin1-sdk-desktop.exe")),
    ).rejects.toThrow();
  });
  it("exports diagnostics to a new archive and filters the real help catalog", async () => {
    await navigate("Activity");
    const output = path.join(root, "diagnostics.zip");
    vi.mocked(client.selectPath).mockResolvedValue(output);
    await user().click(
      screen.getByRole("button", { name: "Export diagnostics" }),
    );
    await approve();
    expect((await readFile(output)).subarray(0, 2).toString()).toBe("PK");
    await navigate("Help Center");
    await user().type(
      screen.getByRole("textbox", { name: "Search help" }),
      "Backups and recovery",
    );
    expect(
      within(
        screen.getByRole("navigation", { name: "Help topics" }),
      ).getAllByRole("button"),
    ).toHaveLength(1);
    expect(
      screen.getByRole("heading", { name: "Backups and recovery" }),
    ).toBeInTheDocument();
  });
  it("requires deliberate navigation for an SDK handoff and never applies its traffic request", async () => {
    await act(async () =>
      handoffHandler({ package_id: "kriss-vector", traffic: true }),
    );
    expect(
      screen.getByRole("heading", { name: "Setup", level: 1 }),
    ).toBeInTheDocument();
    await user().click(
      screen.getByRole("button", { name: "Open requested package" }),
    );
    await idle();
    expect(
      screen.getByRole("heading", { name: "Packages", level: 1 }),
    ).toBeInTheDocument();
    await expect(
      access(path.join(root, "state/config.toml")),
    ).rejects.toThrow();
    expect(
      screen.queryByRole("region", { name: "Review changes" }),
    ).not.toBeInTheDocument();
  });
});
