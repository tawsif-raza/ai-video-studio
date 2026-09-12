import { API_BASE_URL, ApiError } from "@/api/client";

export { ApiError };

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  full_name: string;
}

export interface LogoutResponse {
  status: string;
  message: string;
}

export interface ForgotPasswordResponse {
  status: string;
  message: string;
  reset_token?: string | null;
}

export interface ResetPasswordResponse {
  status: string;
  message: string;
}

export const AUTH_TOKEN_STORAGE_KEY = "studio_access_token";

function getStorage(): Storage | null {
  if (typeof window !== "undefined" && window.localStorage) {
    return window.localStorage;
  }
  try {
    if (typeof localStorage !== "undefined" && localStorage && typeof localStorage.getItem === "function") {
      return localStorage;
    }
  } catch {
    return null;
  }
  return null;
}

export function getStoredToken(): string | null {
  try {
    const storage = getStorage();
    return storage ? storage.getItem(AUTH_TOKEN_STORAGE_KEY) : null;
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  try {
    const storage = getStorage();
    if (!storage) return;
    if (token) {
      storage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
    } else {
      storage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    }
  } catch {
    // Gracefully handle storage errors in restricted contexts
  }
}

export function removeStoredToken(): void {
  setStoredToken(null);
}

function parseErrorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (typeof d === "object" && d && "msg" in d ? String(d.msg) : String(d)))
        .join("; ");
    }
  }
  return `Request failed with status ${status}`;
}

export async function loginUser(credentials: LoginCredentials): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    cache: "no-store",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(credentials),
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError(response.status, parseErrorMessage(response.status, body), body);
  }

  return body as AuthResponse;
}

export async function registerUser(data: RegisterData): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: "POST",
    cache: "no-store",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(data),
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError(response.status, parseErrorMessage(response.status, body), body);
  }

  return body as AuthResponse;
}

export async function getMe(token?: string): Promise<User> {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  const effectiveToken = token ?? getStoredToken();
  if (effectiveToken) {
    headers["Authorization"] = `Bearer ${effectiveToken}`;
  }

  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    method: "GET",
    cache: "no-store",
    credentials: "include",
    headers,
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError(response.status, parseErrorMessage(response.status, body), body);
  }

  return body as User;
}

export async function logoutUser(token?: string): Promise<LogoutResponse> {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  const effectiveToken = token ?? getStoredToken();
  if (effectiveToken) {
    headers["Authorization"] = `Bearer ${effectiveToken}`;
  }

  const response = await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    cache: "no-store",
    credentials: "include",
    headers,
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError(response.status, parseErrorMessage(response.status, body), body);
  }

  return body as LogoutResponse;
}

export async function requestPasswordReset(email: string): Promise<ForgotPasswordResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/forgot-password`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ email }),
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError(response.status, parseErrorMessage(response.status, body), body);
  }

  return body as ForgotPasswordResponse;
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<ResetPasswordResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/reset-password`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ token, new_password: newPassword }),
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    throw new ApiError(response.status, parseErrorMessage(response.status, body), body);
  }

  return body as ResetPasswordResponse;
}

