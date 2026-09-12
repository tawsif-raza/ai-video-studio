import { Suspense } from "react";
import type { Metadata } from "next";

import { AuthShowcase } from "@/features/auth/AuthShowcase";
import { ResetPasswordForm } from "@/features/auth/ResetPasswordForm";

export const metadata: Metadata = {
  title: "Reset Password - AI Video Studio",
  description: "Reset your password for AI Video Studio - AI-powered video creation and production platform.",
};

export default function ResetPasswordPage() {
  return (
    <div className="grid min-h-screen w-full lg:grid-cols-2">
      <AuthShowcase />
      <div className="flex items-center justify-center bg-zinc-950 p-4 sm:p-8">
        <Suspense
          fallback={
            <div className="flex h-48 w-full max-w-md items-center justify-center text-sm text-zinc-500">
              Loading recovery details...
            </div>
          }
        >
          <ResetPasswordForm />
        </Suspense>
      </div>
    </div>
  );
}
