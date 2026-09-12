"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { requestPasswordReset } from "@/api/auth";

interface NoticeState {
  type: "info" | "success" | "error";
  message: string;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | undefined>();
  const [touched, setTouched] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [resetToken, setResetToken] = useState<string | null>(null);

  const validateEmail = (value: string): string | undefined => {
    const trimmed = value.trim();
    if (!trimmed) {
      return "Email address is required.";
    }
    if (!EMAIL_REGEX.test(trimmed)) {
      return "Please enter a valid email address (e.g. creator@studio.ai).";
    }
    return undefined;
  };

  const handleEmailChange = (e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setEmail(value);
    if (touched || emailError) {
      setEmailError(validateEmail(value));
    }
  };

  const handleEmailBlur = () => {
    setTouched(true);
    setEmailError(validateEmail(email));
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (isSubmitting) return;

    const error = validateEmail(email);
    setTouched(true);
    setEmailError(error);

    if (error) {
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    setResetToken(null);

    try {
      const result = await requestPasswordReset(email.trim());
      setNotice({
        type: "success",
        message: result.message || "If an account exists with that email, a password reset link has been sent.",
      });
      if (result.reset_token) {
        setResetToken(result.reset_token);
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to request password reset. Please try again.";
      setNotice({
        type: "error",
        message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

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

        <h1 className="mt-4 text-2xl font-bold tracking-tight text-white">Reset your password</h1>
        <p className="text-sm leading-relaxed text-zinc-400">
          Enter the email address associated with your account, and we will send you a password recovery link.
        </p>
      </div>

      {/* Notice Banner */}
      {notice && (
        <div
          role={notice.type === "error" ? "alert" : "status"}
          className={`mb-6 flex items-start gap-3 rounded-lg border p-3.5 text-xs leading-relaxed transition-all ${
            notice.type === "success"
              ? "border-emerald-500/30 bg-emerald-950/40 text-emerald-300"
              : notice.type === "error"
                ? "border-red-500/30 bg-red-950/40 text-red-300"
                : "border-indigo-500/30 bg-indigo-950/40 text-indigo-200"
          }`}
        >
          <span className="mt-0.5 shrink-0 text-sm" aria-hidden="true">
            {notice.type === "success" ? "✓" : notice.type === "error" ? "⚠" : "ℹ"}
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

      {/* Development Token Helper */}
      {resetToken && (
        <div className="mb-6 rounded-lg border border-indigo-500/40 bg-indigo-950/30 p-4 text-xs text-indigo-200">
          <div className="flex items-center justify-between font-semibold text-indigo-300">
            <span>Dev / Test Mode Token</span>
            <span className="rounded bg-indigo-900/60 px-1.5 py-0.5 text-[10px] uppercase">Active</span>
          </div>
          <p className="mt-1 text-zinc-400">
            Since no transactional email service is required in this environment, you can follow the link below to set a new password directly:
          </p>
          <div className="mt-3">
            <Link
              href={`/reset-password?token=${encodeURIComponent(resetToken)}`}
              className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 font-medium text-white shadow hover:bg-indigo-500 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
            >
              <span>Proceed to Reset Password →</span>
            </Link>
          </div>
        </div>
      )}

      {/* Forgot Password Form */}
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="recovery-email" className="text-xs font-medium text-zinc-300">
            Email address
          </label>
          <input
            id="recovery-email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            required
            disabled={isSubmitting}
            value={email}
            onChange={handleEmailChange}
            onBlur={handleEmailBlur}
            placeholder="creator@studio.ai"
            aria-invalid={Boolean(emailError)}
            aria-describedby={emailError ? "email-error" : undefined}
            className={`h-11 w-full rounded-lg border bg-zinc-900/80 px-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60 ${
              emailError
                ? "border-red-500/80 focus-visible:ring-red-500"
                : "border-zinc-800 hover:border-zinc-700 focus-visible:border-indigo-500 focus-visible:ring-indigo-500"
            }`}
          />
          {emailError && (
            <p id="email-error" role="alert" className="text-xs text-red-400">
              {emailError}
            </p>
          )}
        </div>

        <Button
          type="submit"
          variant="primary"
          isLoading={isSubmitting}
          disabled={isSubmitting}
          className="mt-2 h-11 w-full bg-indigo-600 font-medium text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950"
        >
          {isSubmitting ? "Sending reset link..." : "Send Reset Link"}
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
        <div>
          Don&rsquo;t have an account?{" "}
          <Link
            href="/signup"
            className="font-medium text-indigo-400 transition-colors hover:text-indigo-300 focus-visible:outline-none focus-visible:underline"
          >
            Sign up
          </Link>
        </div>
      </div>
    </div>
  );
}
