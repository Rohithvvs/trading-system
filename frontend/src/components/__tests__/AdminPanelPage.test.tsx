import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AdminPanelPage } from "../admin/AdminPanelPage";
import { ToastProvider } from "../../design-system";

vi.mock("../admin/UsersAdminTab", () => ({
  UsersAdminTab: () => <div data-testid="users-tab-body">Users body</div>,
}));
vi.mock("../admin/FeaturesAdminTab", () => ({
  FeaturesAdminTab: () => <div data-testid="features-tab-body">Features body</div>,
}));

function renderPanel(initial = "/admin") {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/admin" element={<AdminPanelPage />} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  );
}

describe("AdminPanelPage", () => {
  it("renders Users and Features tabs", () => {
    renderPanel();
    expect(screen.getByTestId("admin-panel-page")).toBeTruthy();
    expect(screen.getByTestId("tab-users")).toBeTruthy();
    expect(screen.getByTestId("tab-features")).toBeTruthy();
    expect(screen.getByTestId("users-tab-body")).toBeTruthy();
  });

  it("switches to Features tab", () => {
    renderPanel();
    fireEvent.click(screen.getByTestId("tab-features"));
    expect(screen.getByTestId("features-tab-body")).toBeTruthy();
  });

  it("respects ?tab=features (AC-ACC-08)", () => {
    renderPanel("/admin?tab=features");
    expect(screen.getByTestId("features-tab-body")).toBeTruthy();
  });

  it("invalid tab defaults to Users (AC-ACC-08)", () => {
    renderPanel("/admin?tab=nope");
    expect(screen.getByTestId("users-tab-body")).toBeTruthy();
    expect(screen.queryByTestId("features-tab-body")).toBeNull();
  });
});


