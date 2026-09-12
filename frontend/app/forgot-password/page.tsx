import type { Metadata } from "next";

import { AuthShowcase } from "@/features/auth/AuthShowcase";
import { ForgotPasswordForm } from "@/features/auth/ForgotPasswordForm";

export const metadata: Metadata = {
  title: "Forgot Password - AI Video Studio",
  description: "Reset your password for AI Video Studio - AI-powered video creation and production platform.",
};

export default function ForgotPasswordPage() {
  return (
    <div className="grid min-h-screen w-full lg:grid-cols-2">
      <AuthShowcase />
      <div className="flex items-center justify-center bg-zinc-950 p-4 sm:p-8">
        <ForgotPasswordForm />
      </div>
    </div>
  );
}
