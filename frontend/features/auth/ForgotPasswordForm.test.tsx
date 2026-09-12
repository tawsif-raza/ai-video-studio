import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { requestPasswordResetMock } = vi.hoisted(() => ({
  requestPasswordResetMock: vi.fn(),
}));

vi.mock("@/api/auth", () => ({
  requestPasswordReset: requestPasswordResetMock,
}));

import { ForgotPasswordForm } from "./ForgotPasswordForm";

describe("ForgotPasswordForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders branding header, input field, and navigation links", () => {
    render(<ForgotPasswordForm />);

    expect(screen.getByText("AI Video Studio")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /reset your password/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send reset link/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /return to sign in/i })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: /sign up/i })).toHaveAttribute("href", "/signup");
  });

  it("validates empty email submission", () => {
    render(<ForgotPasswordForm />);

    const submitBtn = screen.getByRole("button", { name: /send reset link/i });
    fireEvent.click(submitBtn);

    expect(screen.getByText("Email address is required.")).toBeInTheDocument();
    expect(requestPasswordResetMock).not.toHaveBeenCalled();
  });

  it("validates malformed email addresses", () => {
    render(<ForgotPasswordForm />);

    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: "invalid-email" } });
    fireEvent.blur(emailInput);

    expect(
      screen.getByText("Please enter a valid email address (e.g. creator@studio.ai)."),
    ).toBeInTheDocument();
  });

  it("successfully submits email and renders neutral success notice", async () => {
    requestPasswordResetMock.mockResolvedValueOnce({
      status: "ok",
      message: "If an account exists with that email, a password reset link has been sent.",
      reset_token: null,
    });

    render(<ForgotPasswordForm />);

    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: "creator@studio.ai" } });

    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(requestPasswordResetMock).toHaveBeenCalledWith("creator@studio.ai");
      expect(
        screen.getByText(/if an account exists with that email, a password reset link has been sent/i),
      ).toBeInTheDocument();
    });
  });

  it("renders development helper link when API returns reset_token in non-production", async () => {
    requestPasswordResetMock.mockResolvedValueOnce({
      status: "ok",
      message: "If an account exists with that email, a password reset link has been sent.",
      reset_token: "test-dev-token-abc-123",
    });

    render(<ForgotPasswordForm />);

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "developer@studio.ai" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/dev \/ test mode token/i)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /proceed to reset password/i })).toHaveAttribute(
        "href",
        "/reset-password?token=test-dev-token-abc-123",
      );
    });
  });

  it("displays error banner when request fails", async () => {
    requestPasswordResetMock.mockRejectedValueOnce(new Error("Network connection error"));

    render(<ForgotPasswordForm />);

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "creator@studio.ai" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Network connection error");
    });
  });

  it("allows dismissing notification banner", async () => {
    requestPasswordResetMock.mockRejectedValueOnce(new Error("Server unavailable"));

    render(<ForgotPasswordForm />);

    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "creator@studio.ai" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /dismiss message/i }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
