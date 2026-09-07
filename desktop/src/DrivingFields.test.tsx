import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Field } from "./Fields";

describe("driving settings", () => {
  it("offers explicit display providers and explains external ownership", async () => {
    const change = vi.fn();
    render(<Field name="speedometer_provider" value="auto" change={change} />);
    const select = screen.getByRole("combobox", { name: "Speedometer Provider" });
    expect(screen.getAllByRole("option").map(o => o.textContent)).toEqual(["auto", "builtin", "rex", "lefix", "off"]);
    expect(select).toHaveAccessibleDescription(/installed separately/);
    await userEvent.selectOptions(select, "lefix");
    expect(change).toHaveBeenCalledWith("lefix");
  });
  it("offers units and a bounded telemetry mode", () => {
    render(<><Field name="speedometer_units" value="mph" change={vi.fn()} /><Field name="driving_telemetry" value="towing" change={vi.fn()} /></>);
    expect(screen.getByRole("combobox", { name: "Speedometer Units" })).toHaveValue("mph");
    expect(screen.getByRole("combobox", { name: "Driving Telemetry" })).toHaveValue("towing");
    expect(screen.getByText(/no uploads/)).toBeVisible();
  });
  it("disables shift settings while busy and explains opt-in", () => {
    render(<Field name="shift_controls_enabled" value={true} disabled change={vi.fn()} />);
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByText(/Starts automatic/)).toBeVisible();
  });
});
