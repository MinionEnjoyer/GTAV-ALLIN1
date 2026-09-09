import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import PackageDraft from "./PackageDraft";

afterEach(cleanup);
function draft(selected: string | null) {
  return {source: "both.zip", package: {
    name: "Test bundle", version: "1.0", description: "", editions: ["legacy", "enhanced"],
    type: "bundle", schema_version: 5, files: [], rpf_entry_count: 0,
    dependencies: [], conflicts: [], bundle_editions: ["legacy", "enhanced"],
    selected_edition: selected,
  }};
}
it("explains edition selection and allows reviewing the selected variant", () => {
  render(<PackageDraft draft={draft("enhanced")} locked={false} change={vi.fn()} review={vi.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent("enhanced selected automatically");
  expect(screen.getByRole("button", {name: "Review package installation"})).toBeEnabled();
});
it("requires a game selection for an edition bundle", () => {
  render(<PackageDraft draft={draft(null)} locked={false} change={vi.fn()} review={vi.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent("select a GTA installation");
  expect(screen.getByRole("button", {name: "Review package installation"})).toBeDisabled();
});
