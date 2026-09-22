import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import type { Client, RecordData } from "./client";
import { descriptions } from "./WorkspaceChrome";

const config = {
  general: { target_edition: "enhanced", gta_enhanced_path: "D:/Synthetic GTA V Enhanced" },
  traffic: { max_driven: 24 },
  vehicles: { replacement_chance: 0.25 },
  script: { hold_duration_ms: 500, reduced_motion: false },
};

function fixture(health: RecordData = { launch_safe: true, edition: "enhanced", issues: [] }): Client {
  return {
    request: vi.fn(async (operation, payload = {}) => {
      if (operation === "catalog") return { desktop_version: "0.6.6" };
      if (operation === "health") return health;
      if (operation === "review") return {
        action: payload.action, request: payload, target: "D:/Synthetic GTA V Enhanced", game_write: true,
        preview_counts: {
          weapons: { existing: 4, total: 4, status: "available" },
          vehicles: { existing: 4, total: 4, status: "available" },
          gear: { existing: 4, total: 4, status: "available" },
        },
      };
      if (operation === "inspect") return {
        config: payload.config ?? config,
        status: { valid_game: true, edition: "enhanced", mod_installed: true },
        content: [], packages: [], installed: [], builtin_packages: [], sdk_examples: [], help: [],
      };
      throw new Error(`Unexpected operation: ${operation}`);
    }),
    selectPath: vi.fn(async () => null),
    onClose: vi.fn(async () => () => {}),
    onHandoff: vi.fn(async () => () => {}),
    onProgress: vi.fn(async () => () => {}),
    close: vi.fn(async () => {}),
  };
}

async function openWorkspace(name: string) {
  await userEvent.setup().click(
    within(screen.getByRole("navigation", { name: "Primary" })).getByRole("button", { name }),
  );
  await screen.findByRole("heading", { name, level: 1 });
}

describe("Launcher page presentation contracts", () => {
  it("summarizes a health result instead of exposing raw response JSON", async () => {
    render(<App client={fixture({
      launch_safe: false,
      edition: "enhanced",
      issues: [{ severity: "error", message: "Required dependency is missing: ScriptHookV.dll" }],
    })} />);
    await screen.findByRole("button", { name: "Check health" });

    await userEvent.setup().click(screen.getByRole("button", { name: "Check health" }));

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent("Health check completed for enhanced installation.");
    expect(notice).toHaveTextContent("Found 1 blocking issue.");
    expect(notice).toHaveTextContent("ERROR: Required dependency is missing: ScriptHookV.dll");
    expect(notice).toHaveTextContent("Path: Not provided");
    expect(screen.queryByText(/"launch_safe"/)).not.toBeInTheDocument();
    expect(screen.queryByText(/"issues"/)).not.toBeInTheDocument();
  });

  it("retains every non-blocking health warning and its path", async () => {
    render(<App client={fixture({
      launch_safe: true,
      edition: "enhanced",
      issues: [
        { severity: "warning", message: "RageOpenV.asi is missing; previews may not load.", path: "D:/Synthetic GTA V Enhanced/RageOpenV.asi" },
        { severity: "warning", message: "Optional preview pack is outdated.", path: "D:/Synthetic GTA V Enhanced/mods" },
      ],
    })} />);
    await screen.findByRole("button", { name: "Check health" });

    await userEvent.setup().click(screen.getByRole("button", { name: "Check health" }));

    const notice = await screen.findByRole("status");
    expect(notice).toHaveTextContent("No blocking issues found.");
    expect(notice).toHaveTextContent("WARNING: RageOpenV.asi is missing; previews may not load.");
    expect(notice).toHaveTextContent("Path: D:/Synthetic GTA V Enhanced/RageOpenV.asi");
    expect(notice).toHaveTextContent("WARNING: Optional preview pack is outdated.");
    expect(notice).toHaveTextContent("Path: D:/Synthetic GTA V Enhanced/mods");
  });

  it("keeps page descriptions as the top-level orientation without duplicate intro headings", async () => {
    render(<App client={fixture()} />);
    await screen.findByRole("heading", { name: "Setup", level: 1 });

    const keys: Record<string, keyof typeof descriptions> = {
      Gameplay: "gameplay", Input: "input", "Help Center": "help",
    };
    for (const [name, duplicateHeading] of [
      ["Gameplay", "Gameplay preferences"],
      ["Input", "Controls and accessibility"],
      ["Help Center", "Guidance and safe workflows"],
    ]) {
      await openWorkspace(name);
      expect(screen.getByText(descriptions[keys[name]])).toBeVisible();
      expect(screen.queryByRole("heading", { name: duplicateHeading, level: 2 })).not.toBeInTheDocument();
    }
  });

  it("keeps launch request data in collapsed technical details", async () => {
    render(<App client={fixture()} />);
    await screen.findByRole("button", { name: "Quick Launch" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Quick Launch" }));

    const review = await screen.findByRole("region", { name: "Review changes" });
    const details = within(review).getByText("Technical details").closest("details");
    if (!details) throw new Error("Technical details container is missing");
    expect(details).not.toHaveAttribute("open");
    const request = details.querySelector("pre");
    if (!request) throw new Error("Technical request data is missing");
    expect(request).toHaveTextContent('"action": "launch"');
    expect(request).not.toBeVisible();
  });
});
