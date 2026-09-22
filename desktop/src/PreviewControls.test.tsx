import { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PreviewControls from "./PreviewControls";

describe("compact preview controls", () => {
  it("keeps launch modes accessible and shows update choices only in update mode", () => {
    const view = render(<PreviewControls busy={false} skipped={[]} quick onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "Quick Launch" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Update Previews" })).not.toBeChecked();
    expect(screen.queryByRole("checkbox", { name: "Missing previews only" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Weapons" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Coverage Existing \/ total/ })).toBeVisible();

    view.rerender(<PreviewControls busy={false} skipped={[]} quick={false} onChange={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "Update Previews" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Missing previews only" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Preview categories" })).toBeVisible();
    expect(screen.getByRole("checkbox", { name: "Weapons" })).toBeChecked();
  });
  it("offers missing-only and preserves it when categories or launch mode change", async () => {
    const change = vi.fn(), user = userEvent.setup();
    const view = render(<PreviewControls busy={false} skipped={[]} quick={false} onChange={change} />);
    await user.click(screen.getByRole("checkbox", { name: "Missing previews only" }));
    expect(change).toHaveBeenLastCalledWith([], false, true);
    view.rerender(<PreviewControls busy={false} skipped={[]} quick={false} missingOnly onChange={change} />);
    await user.click(screen.getByRole("checkbox", { name: "Vehicles" }));
    expect(change).toHaveBeenLastCalledWith(["vehicles"], false, true);
    await user.click(screen.getByRole("radio", { name: "Quick Launch" }));
    expect(change).toHaveBeenLastCalledWith([], true, true);
  });
  it.each([true, false])("shows coverage in both launch modes (quick=%s)", quick => {
    render(<PreviewControls busy={false} skipped={[]} quick={quick} counts={{
      weapons: { existing: 107, total: 107, status: "available" },
      vehicles: { existing: 700, total: 716, status: "available" },
      gear: { existing: null, total: null, status: "unavailable", reason: "Index unreadable" },
    }} onChange={vi.fn()} />);
    expect(screen.getByText("107/107")).toBeVisible();
    expect(screen.getByText("700/716")).toBeVisible();
    expect(screen.getByText("Unavailable")).toHaveAttribute("title", "Index unreadable");
    if (!quick) expect(screen.getByRole("checkbox", { name: "Weapons" })).toBeChecked();
  });
  it("locks mode and category choices while busy", () => {
    const change = vi.fn();
    render(<PreviewControls busy skipped={[]} quick={false} onChange={change} />);
    for (const input of [...screen.getAllByRole("radio"), ...screen.getAllByRole("checkbox")]) expect(input).toBeDisabled();
    expect(change).not.toHaveBeenCalled();
  });
  it("supports keyboard mode selection and restores hidden categories", async () => {
    function Harness() {
      const [quick, setQuick] = useState(false);
      const [skipped, setSkipped] = useState<string[]>(["vehicles"]);
      return <PreviewControls busy={false} skipped={skipped} quick={quick} onChange={(s, q) => {setSkipped(s); setQuick(q);}} />;
    }
    render(<Harness />);
    const user = userEvent.setup();
    screen.getByRole("radio", { name: "Update Previews" }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "Quick Launch" })).toBeChecked();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("checkbox", { name: "Vehicles" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Weapons" })).toBeChecked();
  });
});
