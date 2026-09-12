import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { pushMock, resetPasswordMock, searchParamsMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  resetPasswordMock: vi.fn(),
  searchParamsMock: { current: new URLSearchParams("token=valid-test-token") },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
  }),
  useSearchParams: () => searchParamsMock.current,
}));

vi.mock("@/api/auth", () => ({
  resetPassword: resetPasswordMock,
}));

import { ResetPasswordForm } from "./ResetPasswordForm";

describe("ResetPasswordForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchParamsMock.current = new URLSearchParams("token=valid-test-token");
  });

  it("renders invalid link notice when no token is present", () => {
    searchParamsMock.current = new URLSearchParams("");

    render(<ResetPasswordForm />);

    expect(screen.getByText("Invalid Reset Link")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /request new reset link/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(screen.getByRole("link", { name: /return to sign in/i })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  it("renders form elements when token is present in search parameters", () => {
    render(<ResetPasswordForm />);

    expect(screen.getByRole("heading", { name: /set new password/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/^new password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument();
    expect(screen.getByText("At least 6 characters")).toBeInTheDocument();
    expect(screen.getByText("Passwords match")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /update password/i })).toBeInTheDocument();
  });

  it("toggles password visibility", () => {
    render(<ResetPasswordForm />);

    const passwordInput = screen.getByLabelText(/^new password/i);
    expect(passwordInput).toHaveAttribute("type", "password");

    const showPasswordBtn = screen.getByRole("button", { name: "Show password" });
    fireEvent.click(showPasswordBtn);
    expect(passwordInput).toHaveAttribute("type", "text");

    const hidePasswordBtn = screen.getByRole("button", { name: "Hide password" });
    fireEvent.click(hidePasswordBtn);
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  it("validates password length and password matching", () => {
    render(<ResetPasswordForm />);

    const passwordInput = screen.getByLabelText(/^new password/i);
    const confirmInput = screen.getByLabelText(/confirm new password/i);
    const submitBtn = screen.getByRole("button", { name: /update password/i });

    // Too short
    fireEvent.change(passwordInput, { target: { value: "123" } });
    fireEvent.change(confirmInput, { target: { value: "123" } });
    fireEvent.click(submitBtn);

    expect(screen.getByText("Password must be at least 6 characters.")).toBeInTheDocument();
    expect(resetPasswordMock).not.toHaveBeenCalled();

    // Mismatched
    fireEvent.change(passwordInput, { target: { value: "validpassword123" } });
    fireEvent.change(confirmInput, { target: { value: "differentpassword456" } });
    fireEvent.click(submitBtn);

    expect(screen.getByText("Passwords do not match.")).toBeInTheDocument();
    expect(resetPasswordMock).not.toHaveBeenCalled();
  });

  it("successfully resets password and navigates to login", async () => {
    const setTimeoutSpy = vi.spyOn(global, "setTimeout");
    resetPasswordMock.mockResolvedValueOnce({
      status: "ok",
      message: "Password has been successfully reset.",
    });

    render(<ResetPasswordForm />);

    fireEvent.change(screen.getByLabelText(/^new password/i), {
      target: { value: "newSecurePassword123" },
    });
    fireEvent.change(screen.getByLabelText(/confirm new password/i), {
      target: { value: "newSecurePassword123" },
    });

    fireEvent.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(resetPasswordMock).toHaveBeenCalledWith("valid-test-token", "newSecurePassword123");
      expect(screen.getByText(/password updated/i)).toBeInTheDocument();
      expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 2000);
    });

    // Invoke the timeout callback to verify redirect
    const callback = setTimeoutSpy.mock.calls.find((call) => call[1] === 2000)?.[0] as (() => void) | undefined;
    expect(callback).toBeDefined();
    callback?.();
    expect(pushMock).toHaveBeenCalledWith("/login");

    setTimeoutSpy.mockRestore();
  });

  it("displays error banner when reset fails on server", async () => {
    resetPasswordMock.mockRejectedValueOnce(
      new Error("Password reset token has already been used or invalidated"),
    );

    render(<ResetPasswordForm />);

    fireEvent.change(screen.getByLabelText(/^new password/i), {
      target: { value: "newSecurePassword123" },
    });
    fireEvent.change(screen.getByLabelText(/confirm new password/i), {
      target: { value: "newSecurePassword123" },
    });

    fireEvent.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Password reset token has already been used or invalidated",
      );
    });
  });
});
