import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { pushMock, logoutMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  logoutMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

import type { AuthContextType } from "@/features/auth/AuthContext";

const mockAuthState: AuthContextType = {
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  login: vi.fn(),
  signup: vi.fn(),
  logout: logoutMock,
  refreshSession: vi.fn(),
};

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => mockAuthState,
}));

import { Header } from "@/components/layout/Header";

describe("Header auth integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.user = null;
    mockAuthState.token = null;
    mockAuthState.isAuthenticated = false;
    mockAuthState.isLoading = false;
  });

  it("renders title, subtitle, and Sign In link when unauthenticated", () => {
    render(<Header title="Dashboard" subtitle="Overview of projects" />);

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Overview of projects")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("button", { name: /sign out/i })).not.toBeInTheDocument();
  });

  it("renders user avatar badge and Sign Out button when authenticated", () => {
    mockAuthState.user = {
      id: "user-999",
      email: "director@studio.ai",
      full_name: "Stanley Kubrick",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    };
    mockAuthState.isAuthenticated = true;

    render(<Header title="Studio" />);

    expect(screen.getByText("Stanley Kubrick")).toBeInTheDocument();
    expect(screen.getByText("director@studio.ai")).toBeInTheDocument();
    expect(screen.getByLabelText(/user avatar for stanley kubrick/i)).toHaveTextContent("S");
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /sign in/i })).not.toBeInTheDocument();
  });

  it("calls logout and redirects to /login when Sign Out is clicked", async () => {
    mockAuthState.user = {
      id: "user-999",
      email: "director@studio.ai",
      full_name: "Stanley Kubrick",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    };
    mockAuthState.isAuthenticated = true;
    logoutMock.mockResolvedValueOnce(undefined);

    render(<Header title="Studio" />);

    const signOutBtn = screen.getByRole("button", { name: /sign out/i });
    fireEvent.click(signOutBtn);

    await waitFor(() => {
      expect(logoutMock).toHaveBeenCalledTimes(1);
      expect(pushMock).toHaveBeenCalledWith("/login");
    });
  });
});
