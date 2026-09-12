import type { Metadata } from "next";

import { AuthShowcase } from "@/features/auth/AuthShowcase";
import { SignupForm } from "@/features/auth/SignupForm";

export const metadata: Metadata = {
  title: "Create Account - AI Video Studio",
  description: "Create an account for AI Video Studio - AI-powered video creation and production platform.",
};

export default function SignupPage() {
  return (
    <div className="grid min-h-screen w-full lg:grid-cols-2">
      <AuthShowcase />
      <div className="flex items-center justify-center bg-zinc-950 p-4 sm:p-8">
        <SignupForm />
      </div>
    </div>
  );
}
