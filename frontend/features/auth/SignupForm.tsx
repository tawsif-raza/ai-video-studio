"use client";

import { useState, type ChangeEvent, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { useAuth } from "@/features/auth/AuthContext";
import { sanitizeDestination } from "@/features/auth/ProtectedRoute";

interface FormErrors {
  name?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
  terms?: string;
}

interface NoticeState {
  type: "info" | "success" | "error";
  message: string;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function SignupForm() {
  const { signup } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);

  const [errors, setErrors] = useState<FormErrors>({});
  const [touched, setTouched] = useState<{
    name?: boolean;
    email?: boolean;
    password?: boolean;
    confirmPassword?: boolean;
    terms?: boolean;
  }>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [notice, setNotice] = useState<NoticeState | null>(null);

  // Password rules validation
  const hasMinLength = password.length >= 8;
  const hasNumber = /\d/.test(password);
  const hasUppercase = /[A-Z]/.test(password);
  const hasSpecialChar = /[\W_]/.test(password);

  const validateName = (val: string): string | undefined => {
    const trimmed = val.trim();
    if (!trimmed) return "Full name is required.";
    if (trimmed.length < 2) return "Name must be at least 2 characters.";
    return undefined;
  };

  const validateEmail = (val: string): string | undefined => {
    const trimmed = val.trim();
    if (!trimmed) return "Email address is required.";
    if (!EMAIL_REGEX.test(trimmed)) {
      return "Please enter a valid email address (e.g. creator@studio.ai).";
    }
    return undefined;
  };

  const validatePassword = (val: string): string | undefined => {
    if (!val) return "Password is required.";
    if (val.length < 8) return "Password must be at least 8 characters.";
    if (!/\d/.test(val)) return "Password must contain at least one number.";
    if (!/[A-Z]/.test(val)) return "Password must contain at least one uppercase letter.";
    if (!/[\W_]/.test(val)) return "Password must contain at least one special character.";
    return undefined;
  };

  const validateConfirmPassword = (val: string, pwd = password): string | undefined => {
    if (!val) return "Please confirm your password.";
    if (val !== pwd) return "Passwords do not match.";
    return undefined;
  };

  const validateTerms = (checked: boolean): string | undefined => {
    if (!checked) return "You must agree to the Terms of Service to create an account.";
    return undefined;
  };

  const handleNameChange = (e: ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setName(val);
    if (touched.name || errors.name) {
      setErrors((prev) => ({ ...prev, name: validateName(val) }));
    }
  };

  const handleEmailChange = (e: ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setEmail(val);
    if (touched.email || errors.email) {
      setErrors((prev) => ({ ...prev, email: validateEmail(val) }));
    }
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

  const handleTermsChange = (e: ChangeEvent<HTMLInputElement>) => {
    const checked = e.target.checked;
    setAgreedToTerms(checked);
    if (touched.terms || errors.terms) {
      setErrors((prev) => ({ ...prev, terms: validateTerms(checked) }));
    }
  };

  const handleBlur = (field: keyof FormErrors) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    switch (field) {
      case "name":
        setErrors((prev) => ({ ...prev, name: validateName(name) }));
        break;
      case "email":
        setErrors((prev) => ({ ...prev, email: validateEmail(email) }));
        break;
      case "password":
        setErrors((prev) => ({ ...prev, password: validatePassword(password) }));
        break;
      case "confirmPassword":
        setErrors((prev) => ({
          ...prev,
          confirmPassword: validateConfirmPassword(confirmPassword, password),
        }));
        break;
      case "terms":
        setErrors((prev) => ({ ...prev, terms: validateTerms(agreedToTerms) }));
        break;
    }
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (isSubmitting) return;

    const nameErr = validateName(name);
    const emailErr = validateEmail(email);
    const pwdErr = validatePassword(password);
    const confirmErr = validateConfirmPassword(confirmPassword, password);
    const termsErr = validateTerms(agreedToTerms);

    setTouched({
      name: true,
      email: true,
      password: true,
      confirmPassword: true,
      terms: true,
    });

    setErrors({
      name: nameErr,
      email: emailErr,
      password: pwdErr,
      confirmPassword: confirmErr,
      terms: termsErr,
    });

    if (nameErr || emailErr || pwdErr || confirmErr || termsErr) {
      return;
    }

    setIsSubmitting(true);
    setNotice(null);

    try {
      await signup({
        full_name: name.trim(),
        email: email.trim(),
        password,
      });
      setNotice({
        type: "success",
        message: "Account created successfully! Redirecting to studio...",
      });
      const searchParams =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search)
          : null;
      const target = searchParams?.get("next") || searchParams?.get("redirect");
      router.push(sanitizeDestination(target));
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to create account. Please try again.";
      setNotice({
        type: "error",
        message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGoogleSignUp = () => {
    setNotice({
      type: "info",
      message:
        "Google Sign-Up is a UI placeholder and will be enabled with OAuth setup in the next phase.",
    });
  };

  return (
    <div className="flex w-full max-w-md flex-col justify-center px-4 py-8 sm:px-8">
      {/* Brand Header */}
      <div className="mb-6 flex flex-col gap-2">
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

        <h1 className="mt-2 text-lg font-semibold text-zinc-100">Create your studio account</h1>
        <p className="text-xs text-zinc-400">
          Start producing cinematic video stories with autonomous AI agents.
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

      {/* Google Sign-up Placeholder */}
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={handleGoogleSignUp}
          disabled={isSubmitting}
          aria-label="Sign up with Google"
          className="group relative flex h-11 w-full items-center justify-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/90 px-4 text-sm font-medium text-zinc-200 transition-all hover:border-zinc-700 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" aria-hidden="true">
            <path
              fill="#4285F4"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="#34A853"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="#FBBC05"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
            />
            <path
              fill="#EA4335"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
            />
          </svg>
          <span>Sign up with Google</span>
        </button>

        {/* Divider */}
        <div className="relative my-3 flex items-center justify-center">
          <div className="w-full border-t border-zinc-800" aria-hidden="true" />
          <span className="absolute bg-zinc-950 px-3 text-[11px] font-medium tracking-wider text-zinc-500 uppercase">
            OR REGISTER WITH EMAIL
          </span>
        </div>
      </div>

      {/* Signup Form */}
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-3.5">
        {/* Full Name Field */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="name" className="text-xs font-medium text-zinc-300">
            Full name
          </label>
          <input
            id="name"
            name="name"
            type="text"
            autoComplete="name"
            required
            disabled={isSubmitting}
            value={name}
            onChange={handleNameChange}
            onBlur={() => handleBlur("name")}
            placeholder="Alex Vance"
            aria-invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? "name-error" : undefined}
            className={`h-10 w-full rounded-lg border bg-zinc-900/80 px-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60 ${
              errors.name
                ? "border-red-500/80 focus-visible:ring-red-500"
                : "border-zinc-800 hover:border-zinc-700 focus-visible:border-indigo-500 focus-visible:ring-indigo-500"
            }`}
          />
          {errors.name && (
            <p id="name-error" role="alert" className="text-xs text-red-400">
              {errors.name}
            </p>
          )}
        </div>

        {/* Email Field */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="email" className="text-xs font-medium text-zinc-300">
            Email address
          </label>
          <input
            id="email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            required
            disabled={isSubmitting}
            value={email}
            onChange={handleEmailChange}
            onBlur={() => handleBlur("email")}
            placeholder="creator@studio.ai"
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? "email-error" : undefined}
            className={`h-10 w-full rounded-lg border bg-zinc-900/80 px-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60 ${
              errors.email
                ? "border-red-500/80 focus-visible:ring-red-500"
                : "border-zinc-800 hover:border-zinc-700 focus-visible:border-indigo-500 focus-visible:ring-indigo-500"
            }`}
          />
          {errors.email && (
            <p id="email-error" role="alert" className="text-xs text-red-400">
              {errors.email}
            </p>
          )}
        </div>

        {/* Password Field */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="new-password" className="text-xs font-medium text-zinc-300">
            Password
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
              onBlur={() => handleBlur("password")}
              placeholder="••••••••"
              aria-invalid={Boolean(errors.password)}
              aria-describedby={errors.password ? "password-error" : "password-checklist"}
              className={`h-10 w-full rounded-lg border bg-zinc-900/80 px-3.5 pr-11 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60 ${
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
              className="absolute right-0 top-0 flex h-10 w-10 items-center justify-center text-zinc-400 transition-colors hover:text-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {showPassword ? (
                <svg
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"
                  />
                </svg>
              ) : (
                <svg
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                  />
                </svg>
              )}
            </button>
          </div>

          {/* Password Requirements Checklist */}
          <div id="password-checklist" className="mt-1 grid grid-cols-2 gap-1 text-[11px]">
            <div
              className={`flex items-center gap-1.5 ${hasMinLength ? "text-emerald-400" : "text-zinc-500"}`}
            >
              <span aria-hidden="true">{hasMinLength ? "✓" : "•"}</span>
              <span>8+ characters</span>
            </div>
            <div
              className={`flex items-center gap-1.5 ${hasUppercase ? "text-emerald-400" : "text-zinc-500"}`}
            >
              <span aria-hidden="true">{hasUppercase ? "✓" : "•"}</span>
              <span>Uppercase letter</span>
            </div>
            <div
              className={`flex items-center gap-1.5 ${hasNumber ? "text-emerald-400" : "text-zinc-500"}`}
            >
              <span aria-hidden="true">{hasNumber ? "✓" : "•"}</span>
              <span>One number</span>
            </div>
            <div
              className={`flex items-center gap-1.5 ${hasSpecialChar ? "text-emerald-400" : "text-zinc-500"}`}
            >
              <span aria-hidden="true">{hasSpecialChar ? "✓" : "•"}</span>
              <span>Special symbol</span>
            </div>
          </div>

          {errors.password && (
            <p id="password-error" role="alert" className="text-xs text-red-400">
              {errors.password}
            </p>
          )}
        </div>

        {/* Confirm Password Field */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="confirm-password" className="text-xs font-medium text-zinc-300">
            Confirm password
          </label>
          <input
            id="confirm-password"
            name="confirmPassword"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            required
            disabled={isSubmitting}
            value={confirmPassword}
            onChange={handleConfirmPasswordChange}
            onBlur={() => handleBlur("confirmPassword")}
            placeholder="••••••••"
            aria-invalid={Boolean(errors.confirmPassword)}
            aria-describedby={errors.confirmPassword ? "confirm-error" : undefined}
            className={`h-10 w-full rounded-lg border bg-zinc-900/80 px-3.5 text-sm text-zinc-100 placeholder:text-zinc-600 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950 disabled:cursor-not-allowed disabled:opacity-60 ${
              errors.confirmPassword
                ? "border-red-500/80 focus-visible:ring-red-500"
                : "border-zinc-800 hover:border-zinc-700 focus-visible:border-indigo-500 focus-visible:ring-indigo-500"
            }`}
          />
          {errors.confirmPassword && (
            <p id="confirm-error" role="alert" className="text-xs text-red-400">
              {errors.confirmPassword}
            </p>
          )}
        </div>

        {/* Terms Agreement Checkbox */}
        <div className="mt-1 flex flex-col gap-1">
          <label className="flex items-start gap-2.5 text-xs text-zinc-400 cursor-pointer select-none">
            <input
              id="terms"
              type="checkbox"
              checked={agreedToTerms}
              onChange={handleTermsChange}
              onBlur={() => handleBlur("terms")}
              disabled={isSubmitting}
              aria-invalid={Boolean(errors.terms)}
              aria-describedby={errors.terms ? "terms-error" : undefined}
              className="mt-0.5 h-4 w-4 rounded border-zinc-700 bg-zinc-900 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-zinc-950 disabled:opacity-60"
            />
            <span>
              I agree to the{" "}
              <span className="text-zinc-200 underline hover:text-white">Terms of Service</span> and{" "}
              <span className="text-zinc-200 underline hover:text-white">Privacy Policy</span>.
            </span>
          </label>
          {errors.terms && (
            <p id="terms-error" role="alert" className="text-xs text-red-400">
              {errors.terms}
            </p>
          )}
        </div>

        {/* Primary Sign Up Button */}
        <Button
          type="submit"
          variant="primary"
          isLoading={isSubmitting}
          disabled={isSubmitting}
          className="mt-2 h-11 w-full bg-indigo-600 font-medium text-white hover:bg-indigo-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950"
        >
          {isSubmitting ? "Creating account..." : "Create Account"}
        </Button>
      </form>

      {/* Return to Sign-in */}
      <div className="mt-6 text-center text-xs text-zinc-400">
        Already have an account?{" "}
        <Link
          href="/login"
          className="font-medium text-indigo-400 transition-colors hover:text-indigo-300 focus-visible:outline-none focus-visible:underline"
        >
          Sign in
        </Link>
      </div>
    </div>
  );
}
