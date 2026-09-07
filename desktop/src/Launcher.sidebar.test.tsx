import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import type { Client } from "./client";

function fixture(validGame = false): Client {
  return {
    request: vi.fn(async (operation, payload) => operation === "catalog"
      ? { desktop_version: "0.6.4" }
      : operation === "review" ? { action: payload?.action, request: payload, target: "test", game_write: true,
        ...(payload?.action === "download_previews" ? { preview_download: { count: 111, bytes: 16288588, version: "gbay-previews-2026-09-07", assets: [{ category: "weapons", count: 111 }] } } : {}),
        preview_counts: { weapons: { existing: 97, total: 106, status: "available" } } }
      : { module: payload?.module, status: { valid_game: validGame }, config: { general: { target_edition: "auto" } } }),
    selectPath: vi.fn(async () => null),
    onClose: vi.fn(async () => () => {}),
    onHandoff: vi.fn(async () => () => {}),
    onProgress: vi.fn(async () => () => {}),
    close: vi.fn(async () => {}),
  };
}

describe("SDK-style Launcher sidebar", () => {
  it("reviews a category preview download with size/counts before applying", async () => {
    const client = fixture(true);
    render(<App client={client} />);
    await screen.findByRole("heading", { name: "Setup", level: 1 });
    await userEvent.setup().click(screen.getByRole("button", { name: "Download weapons" }));
    const review = await screen.findByRole("region", { name: "Review changes" });
    expect(client.request).toHaveBeenCalledWith("review", expect.objectContaining({ action: "download_previews", categories: ["weapons"] }));
    expect(within(review).getByText(/111 vanilla images/)).toBeVisible();
    expect(within(review).getByText(/Generated artwork takes priority/)).toBeVisible();
    expect(within(review).getByRole("button", { name: "Apply reviewed changes" })).toBeDisabled();
    expect(client.request).not.toHaveBeenCalledWith("apply", expect.anything());
  });
  it("reviews Quick Launch without applying it or changing normal launch defaults", async () => {
    const client = fixture();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("heading", { name: "Select your game installation" });
    await user.click(screen.getByRole("button", { name: "Quick Launch" }));
    const review = await screen.findByRole("region", { name: "Review changes" });
    expect(client.request).toHaveBeenCalledWith("review", expect.objectContaining({ action: "launch", quick_launch: true }));
    expect(within(review).getByRole("radio", { name: "Quick Launch" })).toBeChecked();
    expect(within(review).getByRole("group", { name: "Preview categories" })).toBeVisible();
    expect(within(review).getByText("97/106")).toBeVisible();
    expect(within(review).queryByRole("checkbox", { name: "Weapons" })).not.toBeInTheDocument();
    expect(within(review).getByRole("button", { name: "Apply reviewed changes" })).toBeDisabled();
    expect(client.request).not.toHaveBeenCalledWith("apply", expect.anything());
    await user.click(within(review).getByRole("button", { name: "Back to draft" }));
    await user.click(screen.getByRole("button", { name: "Launch Story Mode" }));
    expect(await screen.findByRole("radio", { name: "Quick Launch" })).not.toBeChecked();
  });
  it("re-reviews positive category choices and preserves them across modes", async () => {
    const client = fixture();
    const user = userEvent.setup();
    render(<App client={client} />);
    await screen.findByRole("heading", { name: "Select your game installation" });
    await user.click(screen.getByRole("button", { name: "Launch Story Mode" }));
    const review = await screen.findByRole("region", { name: "Review changes" });
    await user.click(within(review).getByRole("checkbox", { name: "I reviewed these changes" }));
    expect(within(review).getByRole("radio", { name: "Update Previews" })).toBeChecked();
    for (const name of ["Weapons", "Vehicles", "Gear"]) expect(within(review).getByRole("checkbox", { name })).toBeChecked();
    expect(within(review).getByRole("checkbox", { name: "Missing previews only" })).toBeChecked();
    await user.click(within(review).getByRole("checkbox", { name: "Missing previews only" }));
    expect(client.request).toHaveBeenCalledWith("review", expect.objectContaining({ missing_previews_only: false }));
    await user.click(within(review).getByRole("checkbox", { name: "Missing previews only" }));
    expect(client.request).toHaveBeenCalledWith("review", expect.objectContaining({ missing_previews_only: true }));
    expect(within(review).getByRole("checkbox", { name: "I reviewed these changes" })).not.toBeChecked();
    await user.click(within(review).getByRole("checkbox", { name: "Vehicles" }));
    expect(client.request).toHaveBeenCalledWith("review", expect.objectContaining({ skip_preview_categories: ["vehicles"], skip_previews: false }));
    expect(within(review).getByRole("checkbox", { name: "I reviewed these changes" })).not.toBeChecked();
    await user.click(within(review).getByRole("radio", { name: "Quick Launch" }));
    expect(within(review).queryByRole("checkbox", { name: "Vehicles" })).not.toBeInTheDocument();
    await user.click(within(review).getByRole("radio", { name: "Update Previews" }));
    expect(within(review).getByRole("checkbox", { name: "Missing previews only" })).toBeChecked();
    expect(within(review).getByRole("checkbox", { name: "Vehicles" })).not.toBeChecked();
    await user.click(within(review).getByRole("checkbox", { name: "Gear" }));
    expect(client.request).toHaveBeenCalledWith("review", expect.objectContaining({ skip_preview_categories: ["vehicles", "gear"], skip_previews: false }));
    expect(within(review).getByRole("checkbox", { name: "Weapons" })).toBeChecked();
    expect(within(review).getByRole("checkbox", { name: "Weapons" })).toBeDisabled();
  });
  it("changing launch mode invalidates confirmation and leaves no redundant skip controls", async () => {
    const client = fixture();
    render(<App client={client} />);
    await screen.findByRole("heading", { name: "Select your game installation" });
    expect(screen.queryByRole("checkbox", { name: /Skip new previews/ })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Launch Story Mode" }));
    const review = await screen.findByRole("region", { name: "Review changes" });
    expect(within(review).queryByText(/Skip new previews/)).not.toBeInTheDocument();
    const toggle = within(review).getByRole("radio", { name: "Quick Launch" });
    expect(toggle).not.toBeChecked();
    await userEvent.setup().click(within(review).getByRole("checkbox", { name: "I reviewed these changes" }));
    await userEvent.setup().click(toggle);
    expect(client.request).toHaveBeenCalledWith("review", expect.objectContaining({ action: "launch", quick_launch: true, skip_previews: false }));
    expect(within(review).getByRole("checkbox", { name: "I reviewed these changes" })).not.toBeChecked();
    expect(within(review).getByRole("button", { name: "Apply reviewed changes" })).toBeDisabled();
  });
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
