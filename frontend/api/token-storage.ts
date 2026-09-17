/**
 * Single source of truth for where the JWT access token lives client-side.
 * Split out from api/auth.ts so api/client.ts (the shared request layer)
 * can read it too without a circular import between the two modules.
 */
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
