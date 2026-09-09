import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, within } from "@testing-library/react";
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

it("lists ordered components, preserves identities and blocks installed RPF ownership", () => {
  const review = vi.fn();
  const value = draft("legacy");
  Object.assign(value.package, { schema_version: 6, type: "collection", components: [
    { ...draft(null).package, bundle_editions: [], id: "legacy.base", name: "Legacy Base", version: "1.2",
      installed: true, installed_version: "1.2", enabled: true, rpf_entry_count: 420,
      install_blocked_reason: "Uninstall the existing package before reinstalling." },
    { ...draft(null).package, bundle_editions: [], id: "legacy.reshade", name: "Legacy ReShade", version: "1.2" },
  ] });
  render(<PackageDraft draft={value} locked={false} change={vi.fn()} review={review} />);
  const regions = screen.getAllByRole("region", { name: "Package inspection" });
  expect(regions).toHaveLength(3);
  expect(within(regions[1]).getByRole("button")).toBeDisabled();
  fireEvent.click(within(regions[2]).getByRole("button"));
  expect(review).toHaveBeenCalledWith(expect.objectContaining({ id: "legacy.reshade" }));
  expect(screen.getAllByRole("button", { name: "Review package installation" })).toHaveLength(2);
});

it("does not offer components or whole-bundle install without an edition selection", () => {
  const value = draft(null);
  Object.assign(value.package, { schema_version: 6, components: [] });
  render(<PackageDraft draft={value} locked={false} change={vi.fn()} review={vi.fn()} />);
  expect(screen.queryByRole("button", { name: "Review package installation" })).not.toBeInTheDocument();
});
