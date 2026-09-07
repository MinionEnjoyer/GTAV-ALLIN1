import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import StartupStatus from "./StartupStatus";
afterEach(cleanup);

it("does not acknowledge while a startup monitor remains active", () => {
  const acknowledge = vi.fn();
  render(<StartupStatus startup={{ active: true, failure: "Still checking" }} acknowledged={false} onAcknowledge={acknowledge} />);
  const button = screen.getByRole("button", { name: "Acknowledge warning" });
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(acknowledge).not.toHaveBeenCalled();
});

it("does not show incomplete stopped milestones as still loading", () => {
  render(<StartupStatus startup={{ active: false, failure: "Stopped", ready: ["native"], milestones: [["native", "Native"], ["story", "Story"]] }} acknowledged onAcknowledge={vi.fn()} />);
  expect(screen.getByText("✓ Native")).toBeInTheDocument();
  expect(screen.getByText("— Story")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Acknowledge warning" })).not.toBeInTheDocument();
});
