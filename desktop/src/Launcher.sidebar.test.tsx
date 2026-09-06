import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import type { Client } from "./client";

function fixture(): Client {
  return {
    request: vi.fn(async (operation, payload) => operation === "catalog"
      ? { desktop_version: "0.6.4" }
      : { module: payload?.module, config: { general: { target_edition: "auto" } } }),
    selectPath: vi.fn(async () => null),
    onClose: vi.fn(async () => () => {}),
    onHandoff: vi.fn(async () => () => {}),
    onProgress: vi.fn(async () => () => {}),
    close: vi.fn(async () => {}),
  };
}

describe("SDK-style Launcher sidebar", () => {
  it("uses the divider arrow to collapse and restore the navigation", async () => {
    const { container } = render(<App client={fixture()} />);
    await screen.findByRole("heading", { name: "Select your game installation" });
    const user = userEvent.setup();
    const collapse = screen.getByRole("button", { name: "Collapse navigation" });
    expect(collapse).toHaveClass("sidebar-toggle");
    expect(collapse).toHaveAttribute("aria-expanded", "true");
    expect(collapse).toHaveAttribute("aria-controls", "launcher-navigation");
    expect(collapse).toHaveTextContent("‹");
    expect(collapse.parentElement).toBe(screen.getByRole("complementary", { name: "Workspace navigation" }));
    await user.click(collapse);
    expect(container.querySelector(".launcher")).toHaveClass("collapsed");
    expect(localStorage.getItem("launcher.sidebar")).toBe("collapsed");
    const expand = screen.getByRole("button", { name: "Expand navigation" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    expect(expand).toHaveTextContent("›");
    expect(within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("button")).toHaveLength(9);
    await user.click(expand);
    expect(container.querySelector(".launcher")).not.toHaveClass("collapsed");
    expect(localStorage.getItem("launcher.sidebar")).toBe("expanded");
  });

  it("restores the saved collapsed state and keeps icon navigation usable", async () => {
    localStorage.setItem("launcher.sidebar", "collapsed");
    const client = fixture();
    render(<App client={client} />);
    await screen.findByRole("heading", { name: "Select your game installation" });
    expect(screen.getByRole("button", { name: "Expand navigation" })).toHaveAttribute("aria-expanded", "false");
    await userEvent.setup().click(screen.getByRole("button", { name: "Packages" }));
    await screen.findByRole("heading", { name: "Packages", level: 1 });
    expect(client.request).toHaveBeenCalledWith("inspect", expect.objectContaining({ module: "mods" }));
  });

  it("supports both Ctrl+B and keyboard activation without losing the current workspace", async () => {
    render(<App client={fixture()} />);
    await screen.findByRole("heading", { name: "Select your game installation" });
    fireEvent.keyDown(window, { key: "b", ctrlKey: true });
    const expand = screen.getByRole("button", { name: "Expand navigation" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    expand.focus();
    await userEvent.setup().keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Collapse navigation" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("heading", { name: "Setup", level: 1 })).toBeInTheDocument();
  });
});
