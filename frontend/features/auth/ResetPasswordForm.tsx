"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { resetPassword } from "@/api/auth";

interface FormErrors {
  password?: string;
  confirmPassword?: string;
}

interface NoticeState {
  type: "info" | "success" | "error";
  message: string;
}

export interface ResetPasswordFormProps {
  token?: string;
}

export function ResetPasswordForm({ token: initialToken }: ResetPasswordFormProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryToken = searchParams?.get("token") || "";
  const token = initialToken || queryToken;

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [touched, setTouched] = useState<{ password?: boolean; confirmPassword?: boolean }>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);

  const validatePassword = (val: string): string | undefined => {
    if (!val) return "Password is required.";
    if (val.length < 6) return "Password must be at least 6 characters.";
    return undefined;
  };

  const validateConfirmPassword = (val: string, pwd = password): string | undefined => {
    if (!val) return "Please confirm your password.";
    if (val !== pwd) return "Passwords do not match.";
    return undefined;
  };

  const handlePasswordChange = (e: ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setPassword(val);
    if (touched.password || errors.password) {
      setErrors((prev) => ({ ...prev, password: validatePassword(val) }));
    }
    if (confirmPassword && (touched.confirmPassword || errors.confirmPassword)) {
      setErrors((prev) => ({
        ...prev,
        confirmPassword: validateConfirmPassword(confirmPassword, val),
      }));
    }
  };

  const handleConfirmPasswordChange = (e: ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setConfirmPassword(val);
    if (touched.confirmPassword || errors.confirmPassword) {
      setErrors((prev) => ({
        ...prev,
        confirmPassword: validateConfirmPassword(val, password),
      }));
    }
  };

  const handlePasswordBlur = () => {
    setTouched((prev) => ({ ...prev, password: true }));
    setErrors((prev) => ({ ...prev, password: validatePassword(password) }));
  };

  const handleConfirmPasswordBlur = () => {
    setTouched((prev) => ({ ...prev, confirmPassword: true }));
    setErrors((prev) => ({
      ...prev,
      confirmPassword: validateConfirmPassword(confirmPassword, password),
    }));
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (isSubmitting) return;

    const passwordErr = validatePassword(password);
    const confirmErr = validateConfirmPassword(confirmPassword, password);

    setTouched({ password: true, confirmPassword: true });
    setErrors({ password: passwordErr, confirmPassword: confirmErr });

    if (passwordErr || confirmErr) {
      return;
    }

    if (!token) {
      setNotice({
        type: "error",
        message: "No password reset token was provided. Please request a new recovery link.",
      });
      return;
    }

    setIsSubmitting(true);
    setNotice(null);

    try {
      await resetPassword(token, password);
      setIsSuccess(true);
      setNotice({
        type: "success",
        message: "Your password has been successfully reset! Redirecting to sign in...",
      });
      setTimeout(() => {
        router.push("/login");
      }, 2000);
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to reset password. The link may have expired or already been used.";
      setNotice({
        type: "error",
        message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Missing token error view
  if (!token) {
    return (
      <div className="flex w-full max-w-md flex-col justify-center px-4 py-10 sm:px-8">
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-red-500/30 bg-red-950/40 text-red-400 shadow-sm">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <span className="text-xl font-semibold tracking-tight text-white">Invalid Reset Link</span>
        </div>

        <p className="text-sm leading-relaxed text-zinc-400">
          This password reset link is missing a recovery token or may have expired. Please request a new link to regain access to your account.
        </p>

        <div className="mt-6 flex flex-col gap-3">
          <Link
            href="/forgot-password"
            className="inline-flex h-11 w-full items-center justify-center rounded-lg bg-indigo-600 px-4 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            Request New Reset Link
          </Link>
          <Link
            href="/login"
            className="inline-flex h-11 w-full items-center justify-center rounded-lg border border-zinc-800 bg-zinc-900 px-4 text-sm font-medium text-zinc-300 transition-colors hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-700"
          >
            Return to Sign In
          </Link>
        </div>
      </div>
    );
  }

  // Success view
  if (isSuccess) {
    return (
      <div className="flex w-full max-w-md flex-col justify-center px-4 py-10 sm:px-8">
        <div className="mb-6 flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-950/40 text-emerald-400 shadow-sm">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <span className="text-xl font-semibold tracking-tight text-white">Password Updated</span>
        </div>

        <div
          role="status"
          className="mb-6 rounded-lg border border-emerald-500/30 bg-emerald-950/40 p-4 text-xs leading-relaxed text-emerald-300"
        >
          Your password has been successfully updated. You can now sign in with your new credentials.
        </div>

        <Link
          href="/login"
          className="inline-flex h-11 w-full items-center justify-center rounded-lg bg-indigo-600 px-4 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
        >
          Proceed to Sign In →
        </Link>
      </div>
    );
  }

  return (
    <div className="flex w-full max-w-md flex-col justify-center px-4 py-10 sm:px-8">
      {/* Brand Header */}
      <div className="mb-8 flex flex-col gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-indigo-500/30 bg-indigo-950/40 text-indigo-400 shadow-sm">
            <svg
              className="h-5 w-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect x="2" y="2" width="20" height="20" rx="4" />
              <path d="m10 8 6 4-6 4V8z" fill="currentColor" stroke="none" />
              <path d="M7 2v4" />
              <path d="M17 2v4" />
              <path d="M7 18v4" />
              <path d="M17 18v4" />
            </svg>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xl font-semibold tracking-tight text-white">AI Video Studio</span>
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-zinc-400">
              PRO
            </span>
          </div>
        </div>

        <h1 className="mt-4 text-2xl font-bold tracking-tight text-white">Set new password</h1>
        <p className="text-sm leading-relaxed text-zinc-400">
          Choose a new password for your account. It must be at least 6 characters.
        </p>
      </div>

      {/* Notice Banner */}
      {notice && (
        <div
          role={notice.type === "error" ? "alert" : "status"}
          className={`mb-6 flex items-start gap-3 rounded-lg border p-3.5 text-xs leading-relaxed transition-all ${
            notice.type === "success"
              ? "border-emerald-500/30 bg-emerald-950/40 text-emerald-300"
              : "border-red-500/30 bg-red-950/40 text-red-300"
          }`}
        >
          <span className="mt-0.5 shrink-0 text-sm" aria-hidden="true">
            {notice.type === "success" ? "✓" : "⚠"}
          </span>
          <div className="flex-1">{notice.message}</div>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="text-zinc-400 hover:text-zinc-200 focus-visible:outline-none"
            aria-label="Dismiss message"
          >
            ✕
          </button>
        </div>
      )}

      {/* Reset Password Form */}
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        {/* New Password */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="new-password" className="text-xs font-medium text-zinc-300">
            New password
          </label>
          <div className="relative">
            <input
              id="new-password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              disabled={isSubmitting}
              value={password}
              onChange={handlePasswordChange}
              onBlur={handlePasswordBlur}
              placeholder="••••••••"
              aria-invalid={Boolean(errors.password)}
              aria-describedby={errors.password ? "password-error" : undefined}
              className={`h-11 w-full rounded-lg border bg-zinc-900/80 px-3.5 pr-11 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60 ${
                errors.password
                  ? "border-red-500/80 focus-visible:ring-red-500"
                  : "border-zinc-800 hover:border-zinc-700 focus-visible:border-indigo-500 focus-visible:ring-indigo-500"
              }`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              disabled={isSubmitting}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center text-zinc-400 transition-colors hover:text-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {showPassword ? (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
          {errors.password && (
            <p id="password-error" role="alert" className="text-xs text-red-400">
              {errors.password}
            </p>
          )}
        </div>

        {/* Confirm Password */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="confirm-password" className="text-xs font-medium text-zinc-300">
            Confirm new password
          </label>
          <div className="relative">
            <input
              id="confirm-password"
              name="confirmPassword"
              type={showConfirmPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              disabled={isSubmitting}
              value={confirmPassword}
              onChange={handleConfirmPasswordChange}
              onBlur={handleConfirmPasswordBlur}
              placeholder="••••••••"
              aria-invalid={Boolean(errors.confirmPassword)}
              aria-describedby={errors.confirmPassword ? "confirm-password-error" : undefined}
              className={`h-11 w-full rounded-lg border bg-zinc-900/80 px-3.5 pr-11 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60 ${
                errors.confirmPassword
                  ? "border-red-500/80 focus-visible:ring-red-500"
                  : "border-zinc-800 hover:border-zinc-700 focus-visible:border-indigo-500 focus-visible:ring-indigo-500"
              }`}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword((prev) => !prev)}
              disabled={isSubmitting}
              aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
              className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center text-zinc-400 transition-colors hover:text-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {showConfirmPassword ? (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                </svg>
              ) : (
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>
          {errors.confirmPassword && (
            <p id="confirm-password-error" role="alert" className="text-xs text-red-400">
              {errors.confirmPassword}
            </p>
          )}
        </div>

        {/* Requirements Checklist */}
        <div className="rounded-lg border border-zinc-850 bg-zinc-900/40 p-3 text-xs">
          <span className="font-medium text-zinc-400">Password Checklist:</span>
          <ul className="mt-2 space-y-1 text-zinc-400">
            <li className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 rounded-full ${password.length >= 6 ? "bg-emerald-400" : "bg-zinc-600"}`} />
              <span className={password.length >= 6 ? "text-emerald-300" : "text-zinc-500"}>
                At least 6 characters
              </span>
            </li>
            <li className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 rounded-full ${password && confirmPassword && password === confirmPassword ? "bg-emerald-400" : "bg-zinc-600"}`} />
              <span className={password && confirmPassword && password === confirmPassword ? "text-emerald-300" : "text-zinc-500"}>
                Passwords match
              </span>
            </li>
          </ul>
        </div>

        <Button
          type="submit"
          variant="primary"
          isLoading={isSubmitting}
          disabled={isSubmitting}
          className="mt-2 h-11 w-full bg-indigo-600 font-medium text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950"
        >
          {isSubmitting ? "Updating password..." : "Update Password"}
        </Button>
      </form>

      {/* Navigation Links */}
      <div className="mt-8 flex flex-col items-center gap-3 text-xs text-zinc-400">
        <Link
          href="/login"
          className="font-medium text-indigo-400 transition-colors hover:text-indigo-300 focus-visible:outline-none focus-visible:underline"
        >
          ← Return to sign in
        </Link>
      </div>
    </div>
  );
}
