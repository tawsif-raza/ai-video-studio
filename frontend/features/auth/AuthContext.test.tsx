import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const storageMap = new Map<string, string>();
const localStorageMock = {
  getItem: vi.fn((key: string) => storageMap.get(key) ?? null),
  setItem: vi.fn((key: string, value: string) => {
    storageMap.set(key, value);
  }),
  removeItem: vi.fn((key: string) => {
    storageMap.delete(key);
  }),
  clear: vi.fn(() => {
    storageMap.clear();
  }),
  length: 0,
  key: vi.fn(),
};

Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
  writable: true,
  configurable: true,
});
if (typeof globalThis !== "undefined") {
  Object.defineProperty(globalThis, "localStorage", {
    value: localStorageMock,
    writable: true,
    configurable: true,
  });
}

const {
  loginUserMock,
  registerUserMock,
  getMeMock,
  logoutUserMock,
} = vi.hoisted(() => ({
  loginUserMock: vi.fn(),
  registerUserMock: vi.fn(),
  getMeMock: vi.fn(),
  logoutUserMock: vi.fn(),
}));

vi.mock("@/api/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/auth")>();
  return {
    ...actual,
    loginUser: loginUserMock,
    registerUser: registerUserMock,
    getMe: getMeMock,
    logoutUser: logoutUserMock,
  };
});

import { AUTH_TOKEN_STORAGE_KEY } from "@/api/auth";
import { AuthProvider, useAuth } from "./AuthContext";

const MOCK_USER = {
  id: "user-123",
  email: "creator@studio.ai",
  full_name: "Creative Director",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

describe("AuthContext and useAuth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
  });

  it("throws error when useAuth is consumed outside AuthProvider", () => {
    const originalConsoleError = console.error;
    console.error = vi.fn();

    expect(() => renderHook(() => useAuth())).toThrow(
      "useAuth must be used within an AuthProvider",
    );

    console.error = originalConsoleError;
  });

  it("provides unauthenticated state when no session exists", async () => {
    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
  });

  it("hydrates immediately when initialUser is provided", () => {
    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => (
        <AuthProvider initialUser={MOCK_USER} initialToken="init-token">
          {children}
        </AuthProvider>
      ),
    });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.user).toEqual(MOCK_USER);
    expect(result.current.token).toBe("init-token");
    expect(result.current.isAuthenticated).toBe(true);
    expect(getMeMock).not.toHaveBeenCalled();
  });

  it("initializes session from stored token if valid", async () => {
    localStorageMock.setItem(AUTH_TOKEN_STORAGE_KEY, "saved-token-abc");
    getMeMock.mockResolvedValueOnce(MOCK_USER);

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(getMeMock).toHaveBeenCalledWith("saved-token-abc");
    expect(result.current.user).toEqual(MOCK_USER);
    expect(result.current.token).toBe("saved-token-abc");
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("clears stored token when initialization fails", async () => {
    localStorageMock.setItem(AUTH_TOKEN_STORAGE_KEY, "expired-token");
    getMeMock.mockRejectedValueOnce(new Error("Token expired"));

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorageMock.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
  });

  it("updates state on successful login", async () => {
    loginUserMock.mockResolvedValueOnce({
      access_token: "jwt-token-123",
      token_type: "bearer",
      user: MOCK_USER,
    });

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    let returnedUser;
    await act(async () => {
      returnedUser = await result.current.login({
        email: "creator@studio.ai",
        password: "secretPassword",
      });
    });

    expect(returnedUser).toEqual(MOCK_USER);
    expect(result.current.user).toEqual(MOCK_USER);
    expect(result.current.token).toBe("jwt-token-123");
    expect(result.current.isAuthenticated).toBe(true);
    expect(localStorageMock.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("jwt-token-123");
  });

  it("updates state on successful signup", async () => {
    registerUserMock.mockResolvedValueOnce({
      access_token: "jwt-token-reg",
      token_type: "bearer",
      user: MOCK_USER,
    });

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => <AuthProvider>{children}</AuthProvider>,
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    let returnedUser;
    await act(async () => {
      returnedUser = await result.current.signup({
        email: "creator@studio.ai",
        password: "secretPassword",
        full_name: "Creative Director",
      });
    });

    expect(returnedUser).toEqual(MOCK_USER);
    expect(result.current.user).toEqual(MOCK_USER);
    expect(result.current.token).toBe("jwt-token-reg");
    expect(result.current.isAuthenticated).toBe(true);
    expect(localStorageMock.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("jwt-token-reg");
  });

  it("clears state and stored token on logout", async () => {
    logoutUserMock.mockResolvedValueOnce({
      status: "success",
      message: "Logged out",
    });

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => (
        <AuthProvider initialUser={MOCK_USER} initialToken="active-token">
          {children}
        </AuthProvider>
      ),
    });

    localStorageMock.setItem(AUTH_TOKEN_STORAGE_KEY, "active-token");

    await act(async () => {
      await result.current.logout();
    });

    expect(logoutUserMock).toHaveBeenCalledWith("active-token");
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorageMock.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull();
  });

  it("refreshes session when active token exists", async () => {
    const updatedUser = { ...MOCK_USER, full_name: "Updated Director" };
    getMeMock.mockResolvedValueOnce(updatedUser);

    const { result } = renderHook(() => useAuth(), {
      wrapper: ({ children }) => (
        <AuthProvider initialUser={MOCK_USER} initialToken="active-token">
          {children}
        </AuthProvider>
      ),
    });

    let refreshed;
    await act(async () => {
      refreshed = await result.current.refreshSession();
    });

    expect(refreshed).toEqual(updatedUser);
    expect(result.current.user).toEqual(updatedUser);
  });
});
