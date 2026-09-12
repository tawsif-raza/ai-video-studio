import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { replaceMock, pathnameMock } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  pathnameMock: { current: "/" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
  }),
  usePathname: () => pathnameMock.current,
}));

import type { AuthContextType } from "@/features/auth/AuthContext";

const mockAuthState: AuthContextType = {
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  login: vi.fn(),
  signup: vi.fn(),
  logout: vi.fn(),
  refreshSession: vi.fn(),
};

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => mockAuthState,
}));

import {
  ProtectedRoute,
  isAuthRoute,
  sanitizeDestination,
} from "./ProtectedRoute";

describe("ProtectedRoute and Navigation Guard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    pathnameMock.current = "/";
    mockAuthState.user = null;
    mockAuthState.token = null;
    mockAuthState.isAuthenticated = false;
    mockAuthState.isLoading = false;
    // Reset window.location
    window.history.pushState({}, "Test", "/");
  });

  describe("Helper utilities", () => {
    it("identifies auth routes correctly", () => {
      expect(isAuthRoute("/login")).toBe(true);
      expect(isAuthRoute("/login/reset")).toBe(true);
      expect(isAuthRoute("/signup")).toBe(true);
      expect(isAuthRoute("/signup/verify")).toBe(true);
      expect(isAuthRoute("/forgot-password")).toBe(true);
      expect(isAuthRoute("/forgot-password/confirm")).toBe(true);
      expect(isAuthRoute("/reset-password")).toBe(true);
      expect(isAuthRoute("/reset-password/done")).toBe(true);
      expect(isAuthRoute("/")).toBe(false);
      expect(isAuthRoute("/projects")).toBe(false);
      expect(isAuthRoute("/settings")).toBe(false);
    });

    it("sanitizes destination URLs preventing open redirects and auth loops", () => {
      expect(sanitizeDestination(null)).toBe("/");
      expect(sanitizeDestination(undefined)).toBe("/");
      expect(sanitizeDestination("")).toBe("/");
      expect(sanitizeDestination("https://malicious.site")).toBe("/");
      expect(sanitizeDestination("http://evil.com/phish")).toBe("/");
      expect(sanitizeDestination("//evil.com")).toBe("/");
      expect(sanitizeDestination("/login")).toBe("/");
      expect(sanitizeDestination("/signup")).toBe("/");
      expect(sanitizeDestination("/forgot-password")).toBe("/");
      expect(sanitizeDestination("/reset-password")).toBe("/");
      expect(sanitizeDestination("/login?next=/projects")).toBe("/");
      expect(sanitizeDestination("/projects")).toBe("/projects");
      expect(sanitizeDestination("/projects/123?tab=render")).toBe("/projects/123?tab=render");
      expect(sanitizeDestination("/settings")).toBe("/settings");
    });
  });

  describe("Loading State", () => {
    it("renders loading screen and does not redirect while isLoading is true", () => {
      mockAuthState.isLoading = true;
      pathnameMock.current = "/projects";

      render(
        <ProtectedRoute>
          <div data-testid="protected-content">Studio Dashboard</div>
        </ProtectedRoute>,
      );

      expect(screen.getByRole("status", { name: /loading studio session/i })).toBeInTheDocument();
      expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
      expect(replaceMock).not.toHaveBeenCalled();
    });
  });

  describe("Unauthenticated User Access", () => {
    it("redirects unauthenticated user accessing protected route to /login with next param", async () => {
      mockAuthState.isAuthenticated = false;
      mockAuthState.isLoading = false;
      pathnameMock.current = "/projects";
      window.history.pushState({}, "Projects", "/projects");

      render(
        <ProtectedRoute>
          <div data-testid="protected-content">Studio Dashboard</div>
        </ProtectedRoute>,
      );

      await waitFor(() => {
        expect(replaceMock).toHaveBeenCalledWith("/login?next=%2Fprojects");
      });
      expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
    });

    it("preserves query string when redirecting to /login", async () => {
      mockAuthState.isAuthenticated = false;
      mockAuthState.isLoading = false;
      pathnameMock.current = "/projects/proj-123";
      window.history.pushState({}, "Workspace", "/projects/proj-123?tab=timeline");

      render(
        <ProtectedRoute>
          <div data-testid="protected-content">Workspace Content</div>
        </ProtectedRoute>,
      );

      await waitFor(() => {
        expect(replaceMock).toHaveBeenCalledWith(
          "/login?next=" + encodeURIComponent("/projects/proj-123?tab=timeline"),
        );
      });
      expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
    });

    it("renders login page directly when unauthenticated user visits /login", () => {
      mockAuthState.isAuthenticated = false;
      mockAuthState.isLoading = false;
      pathnameMock.current = "/login";
      window.history.pushState({}, "Login", "/login");

      render(
        <ProtectedRoute>
          <div data-testid="login-form">Login Form Component</div>
        </ProtectedRoute>,
      );

      expect(screen.getByTestId("login-form")).toBeInTheDocument();
      expect(replaceMock).not.toHaveBeenCalled();
    });

    it("renders signup page directly when unauthenticated user visits /signup", () => {
      mockAuthState.isAuthenticated = false;
      mockAuthState.isLoading = false;
      pathnameMock.current = "/signup";
      window.history.pushState({}, "Signup", "/signup");

      render(
        <ProtectedRoute>
          <div data-testid="signup-form">Signup Form Component</div>
        </ProtectedRoute>,
      );

      expect(screen.getByTestId("signup-form")).toBeInTheDocument();
      expect(replaceMock).not.toHaveBeenCalled();
    });

    it("allows access to routes designated as public", () => {
      mockAuthState.isAuthenticated = false;
      mockAuthState.isLoading = false;
      pathnameMock.current = "/public-gallery";
      window.history.pushState({}, "Public", "/public-gallery");

      render(
        <ProtectedRoute publicRoutes={["/public-gallery"]}>
          <div data-testid="gallery-content">Public Video Gallery</div>
        </ProtectedRoute>,
      );

      expect(screen.getByTestId("gallery-content")).toBeInTheDocument();
      expect(replaceMock).not.toHaveBeenCalled();
    });
  });

  describe("Authenticated User Access", () => {
    beforeEach(() => {
      mockAuthState.user = {
        id: "usr-1",
        email: "creator@studio.ai",
        full_name: "Creative Director",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
      };
      mockAuthState.isAuthenticated = true;
      mockAuthState.isLoading = false;
    });

    it("allows authenticated user to view protected application routes", () => {
      pathnameMock.current = "/projects";
      window.history.pushState({}, "Projects", "/projects");

      render(
        <ProtectedRoute>
          <div data-testid="protected-content">Active Projects</div>
        </ProtectedRoute>,
      );

      expect(screen.getByTestId("protected-content")).toBeInTheDocument();
      expect(replaceMock).not.toHaveBeenCalled();
    });

    it("redirects authenticated user visiting /login away to /", async () => {
      pathnameMock.current = "/login";
      window.history.pushState({}, "Login", "/login");

      render(
        <ProtectedRoute>
          <div data-testid="login-form">Login Form</div>
        </ProtectedRoute>,
      );

      await waitFor(() => {
        expect(replaceMock).toHaveBeenCalledWith("/");
      });
      expect(screen.queryByTestId("login-form")).not.toBeInTheDocument();
    });

    it("redirects authenticated user visiting /signup away to /", async () => {
      pathnameMock.current = "/signup";
      window.history.pushState({}, "Signup", "/signup");

      render(
        <ProtectedRoute>
          <div data-testid="signup-form">Signup Form</div>
        </ProtectedRoute>,
      );

      await waitFor(() => {
        expect(replaceMock).toHaveBeenCalledWith("/");
      });
      expect(screen.queryByTestId("signup-form")).not.toBeInTheDocument();
    });

    it("redirects authenticated user on /login to preserved next destination", async () => {
      pathnameMock.current = "/login";
      window.history.pushState({}, "Login", "/login?next=%2Fprojects%2Fspecial-123");

      render(
        <ProtectedRoute>
          <div data-testid="login-form">Login Form</div>
        </ProtectedRoute>,
      );

      await waitFor(() => {
        expect(replaceMock).toHaveBeenCalledWith("/projects/special-123");
      });
    });

    it("redirects authenticated user on /login to preserved redirect destination", async () => {
      pathnameMock.current = "/login";
      window.history.pushState({}, "Login", "/login?redirect=%2Fsettings");

      render(
        <ProtectedRoute>
          <div data-testid="login-form">Login Form</div>
        </ProtectedRoute>,
      );

      await waitFor(() => {
        expect(replaceMock).toHaveBeenCalledWith("/settings");
      });
    });

    it("sanitizes recursive or malicious next params on authenticated login visit", async () => {
      pathnameMock.current = "/login";
      window.history.pushState({}, "Login", "/login?next=https://evil.site");

      render(
        <ProtectedRoute>
          <div data-testid="login-form">Login Form</div>
        </ProtectedRoute>,
      );

      await waitFor(() => {
        expect(replaceMock).toHaveBeenCalledWith("/");
      });
    });
  });
});
