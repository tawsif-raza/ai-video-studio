import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { pushMock, loginMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  loginMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    login: loginMock,
    signup: vi.fn(),
    logout: vi.fn(),
    user: null,
    token: null,
    isAuthenticated: false,
    isLoading: false,
    refreshSession: vi.fn(),
  }),
}));

import { LoginForm } from "./LoginForm";

describe("LoginForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders branding, inputs, placeholders, and buttons", () => {
    render(<LoginForm />);

    expect(screen.getByText("AI Video Studio")).toBeInTheDocument();
    expect(
      screen.getByText("AI-powered video creation and production platform"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in with google/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /forgot password\?/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(screen.getByRole("button", { name: /^sign in$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign up/i })).toHaveAttribute("href", "/signup");
  });

  it("displays validation errors when submitted with empty fields", () => {
    render(<LoginForm />);

    const submitBtn = screen.getByRole("button", { name: /^sign in$/i });
    fireEvent.click(submitBtn);

    expect(screen.getByText("Email address is required.")).toBeInTheDocument();
    expect(screen.getByText("Password is required.")).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("validates invalid email formatting", () => {
    render(<LoginForm />);

    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: "invalid-email" } });
    fireEvent.blur(emailInput);

    expect(
      screen.getByText("Please enter a valid email address (e.g. creator@studio.ai)."),
    ).toBeInTheDocument();
  });

  it("toggles password visibility between password and text type", () => {
    render(<LoginForm />);

    const passwordInput = screen.getByLabelText(/^password/i);
    expect(passwordInput).toHaveAttribute("type", "password");

    const toggleBtn = screen.getByRole("button", { name: "Show password" });
    fireEvent.click(toggleBtn);

    expect(passwordInput).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  it("shows informative notice for Google login and provides link to forgot password", () => {
    render(<LoginForm />);

    // Google placeholder
    fireEvent.click(screen.getByRole("button", { name: /sign in with google/i }));
    expect(
      screen.getByText(/google sign-in is a ui placeholder/i),
    ).toBeInTheDocument();

    // Forgot password link
    expect(screen.getByRole("link", { name: /forgot password\?/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });

  it("handles valid submission, calls login, and redirects to studio", async () => {
    loginMock.mockResolvedValueOnce({
      id: "user-1",
      email: "creator@studio.ai",
      full_name: "Test Creator",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    });

    render(<LoginForm />);

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password/i);
    const submitBtn = screen.getByRole("button", { name: /^sign in$/i });

    fireEvent.change(emailInput, { target: { value: "creator@studio.ai" } });
    fireEvent.change(passwordInput, { target: { value: "cinematicSecret123" } });

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith({
        email: "creator@studio.ai",
        password: "cinematicSecret123",
      });
      expect(pushMock).toHaveBeenCalledWith("/");
      expect(screen.getByText(/signed in successfully/i)).toBeInTheDocument();
    });
  });

  it("handles failed login submission and displays API error alert", async () => {
    loginMock.mockRejectedValueOnce(new Error("Invalid email or password."));

    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "creator@studio.ai" },
    });
    fireEvent.change(screen.getByLabelText(/^password/i), {
      target: { value: "wrongPassword" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith({
        email: "creator@studio.ai",
        password: "wrongPassword",
      });
      expect(screen.getByRole("alert")).toHaveTextContent("Invalid email or password.");
      expect(pushMock).not.toHaveBeenCalled();
    });
  });
});
