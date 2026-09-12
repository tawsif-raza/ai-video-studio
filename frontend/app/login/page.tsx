import type { Metadata } from "next";

import { AuthShowcase } from "@/features/auth/AuthShowcase";
import { LoginForm } from "@/features/auth/LoginForm";

export const metadata: Metadata = {
  title: "Sign In - AI Video Studio",
  description: "Sign in to AI Video Studio - AI-powered video creation and production platform.",
};

export default function LoginPage() {
  return (
    <div className="grid min-h-screen w-full lg:grid-cols-2">
      <AuthShowcase />
      <div className="flex items-center justify-center bg-zinc-950 p-4 sm:p-8">
        <LoginForm />
      </div>
    </div>
  );
}
