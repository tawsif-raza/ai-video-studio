"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  ApiError,
  getMe,
  getStoredToken,
  loginUser,
  logoutUser,
  registerUser,
  removeStoredToken,
  setStoredToken,
  type AuthResponse,
  type LoginCredentials,
  type RegisterData,
  type User,
} from "@/api/auth";

export interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: LoginCredentials) => Promise<User>;
  signup: (data: RegisterData) => Promise<User>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<User | null>;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export interface AuthProviderProps {
  children: ReactNode;
  initialUser?: User | null;
  initialToken?: string | null;
}

export function AuthProvider({
  children,
  initialUser = null,
  initialToken = null,
}: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(initialUser);
  const [token, setToken] = useState<string | null>(initialToken);
  const [isLoading, setIsLoading] = useState<boolean>(!initialUser);

  // Initialize session on client mount
  useEffect(() => {
    let isMounted = true;

    async function initSession() {
      // If an initial user was provided (e.g. testing or server hydration), don't fetch
      if (initialUser) {
        setIsLoading(false);
        return;
      }

      const storedToken = initialToken ?? getStoredToken();
      if (!storedToken) {
        if (isMounted) {
          setUser(null);
          setToken(null);
          setIsLoading(false);
        }
        return;
      }

      if (isMounted) {
        setToken(storedToken);
      }

      try {
        const currentUser = await getMe(storedToken);
        if (isMounted) {
          setUser(currentUser);
        }
      } catch (err: unknown) {
        // Distinguish authentication rejection from temporary network errors
        const isAuthRejection =
          (err instanceof ApiError && (err.status === 401 || err.status === 403)) ||
          (err instanceof Error && /expired|invalid|unauthorized|forbidden/i.test(err.message));

        if (isAuthRejection) {
          removeStoredToken();
          if (isMounted) {
            setUser(null);
            setToken(null);
          }
        } else if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
          removeStoredToken();
          if (isMounted) {
            setUser(null);
            setToken(null);
          }
        } else {
          // Transient network error or 5xx: preserve stored token, leave user unconfirmed
          if (isMounted) {
            setUser(null);
          }
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    initSession();

    return () => {
      isMounted = false;
    };
  }, [initialUser, initialToken]);

  const login = useCallback(async (credentials: LoginCredentials): Promise<User> => {
    const authResp: AuthResponse = await loginUser(credentials);
    setStoredToken(authResp.access_token);
    setToken(authResp.access_token);
    setUser(authResp.user);
    return authResp.user;
  }, []);

  const signup = useCallback(async (data: RegisterData): Promise<User> => {
    const authResp: AuthResponse = await registerUser(data);
    setStoredToken(authResp.access_token);
    setToken(authResp.access_token);
    setUser(authResp.user);
    return authResp.user;
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    try {
      await logoutUser(token ?? undefined);
    } catch {
      // Always wipe local credentials regardless of network status
    } finally {
      removeStoredToken();
      setToken(null);
      setUser(null);
    }
  }, [token]);

  const refreshSession = useCallback(async (): Promise<User | null> => {
    const activeToken = token || getStoredToken();
    if (!activeToken) {
      setUser(null);
      setToken(null);
      return null;
    }
    try {
      const refreshedUser = await getMe(activeToken);
      setUser(refreshedUser);
      return refreshedUser;
    } catch (err: unknown) {
      const isAuthRejection =
        (err instanceof ApiError && (err.status === 401 || err.status === 403)) ||
        (err instanceof Error && /expired|invalid|unauthorized|forbidden/i.test(err.message));

      if (isAuthRejection) {
        removeStoredToken();
        setUser(null);
        setToken(null);
      }
      return null;
    }
  }, [token]);

  const value = useMemo<AuthContextType>(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(user),
      isLoading,
      login,
      signup,
      logout,
      refreshSession,
    }),
    [user, token, isLoading, login, signup, logout, refreshSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
