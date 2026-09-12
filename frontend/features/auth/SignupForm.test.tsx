import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { pushMock, signupMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  signupMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    login: vi.fn(),
    signup: signupMock,
    logout: vi.fn(),
    user: null,
    token: null,
    isAuthenticated: false,
    isLoading: false,
    refreshSession: vi.fn(),
  }),
}));

import { SignupForm } from "./SignupForm";

describe("SignupForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders form elements, checklist, terms checkbox, and navigation link", () => {
    render(<SignupForm />);

    expect(screen.getByText("Create your studio account")).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/terms of service/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign up with google/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });

  it("validates empty submission", () => {
    render(<SignupForm />);

    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(screen.getByText("Full name is required.")).toBeInTheDocument();
    expect(screen.getByText("Email address is required.")).toBeInTheDocument();
    expect(screen.getByText("Password is required.")).toBeInTheDocument();
    expect(screen.getByText("Please confirm your password.")).toBeInTheDocument();
    expect(
      screen.getByText("You must agree to the Terms of Service to create an account."),
    ).toBeInTheDocument();
    expect(signupMock).not.toHaveBeenCalled();
  });

  it("validates password mismatch", () => {
    render(<SignupForm />);

    const passwordInput = screen.getByLabelText(/^password/i);
    const confirmInput = screen.getByLabelText(/confirm password/i);

    fireEvent.change(passwordInput, { target: { value: "SuperSecret123!" } });
    fireEvent.change(confirmInput, { target: { value: "DifferentPassword456!" } });
    fireEvent.blur(confirmInput);

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
  });

  it("updates password criteria checklist dynamically", () => {
    render(<SignupForm />);

    const passwordInput = screen.getByLabelText(/^password/i);

    // Initial state: not matching
    expect(screen.getByText("8+ characters")).toBeInTheDocument();

    // Type a compliant password
    fireEvent.change(passwordInput, { target: { value: "ValidPassword123!" } });

    // The checklist items are rendered with emerald/success checkmarks
    expect(screen.getByText("8+ characters").parentElement).toHaveClass("text-emerald-400");
    expect(screen.getByText("Uppercase letter").parentElement).toHaveClass("text-emerald-400");
    expect(screen.getByText("One number").parentElement).toHaveClass("text-emerald-400");
    expect(screen.getByText("Special symbol").parentElement).toHaveClass("text-emerald-400");
  });

  it("toggles password visibility", () => {
    render(<SignupForm />);

    const passwordInput = screen.getByLabelText(/^password/i);
    const toggleBtn = screen.getByRole("button", { name: "Show password" });

    expect(passwordInput).toHaveAttribute("type", "password");
    fireEvent.click(toggleBtn);
    expect(passwordInput).toHaveAttribute("type", "text");
  });

  it("shows Google signup placeholder notice", () => {
    render(<SignupForm />);

    fireEvent.click(screen.getByRole("button", { name: /sign up with google/i }));
    expect(
      screen.getByText(/google sign-up is a ui placeholder/i),
    ).toBeInTheDocument();
  });

  it("submits valid registration, calls signup, and redirects to studio", async () => {
    signupMock.mockResolvedValueOnce({
      id: "user-new",
      email: "elena@cinematic.studio",
      full_name: "Elena Rostova",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
    });

    render(<SignupForm />);

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Elena Rostova" },
    });
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "elena@cinematic.studio" },
    });
    fireEvent.change(screen.getByLabelText(/^password/i), {
      target: { value: "CinemaMaster2026!" },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: "CinemaMaster2026!" },
    });
    fireEvent.click(screen.getByLabelText(/terms of service/i));

    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(signupMock).toHaveBeenCalledWith({
        full_name: "Elena Rostova",
        email: "elena@cinematic.studio",
        password: "CinemaMaster2026!",
      });
      expect(pushMock).toHaveBeenCalledWith("/");
      expect(screen.getByText(/account created successfully/i)).toBeInTheDocument();
    });
  });

  it("handles failed registration and displays API error alert", async () => {
    signupMock.mockRejectedValueOnce(new Error("User with this email already exists."));

    render(<SignupForm />);

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Elena Rostova" },
    });
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "elena@cinematic.studio" },
    });
    fireEvent.change(screen.getByLabelText(/^password/i), {
      target: { value: "CinemaMaster2026!" },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: "CinemaMaster2026!" },
    });
    fireEvent.click(screen.getByLabelText(/terms of service/i));

    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(signupMock).toHaveBeenCalledWith({
        full_name: "Elena Rostova",
        email: "elena@cinematic.studio",
        password: "CinemaMaster2026!",
      });
      expect(screen.getByRole("alert")).toHaveTextContent("User with this email already exists.");
      expect(pushMock).not.toHaveBeenCalled();
    });
  });
});
