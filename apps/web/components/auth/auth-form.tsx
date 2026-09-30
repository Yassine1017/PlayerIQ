"use client";

import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { authConfigured, supabase } from "@/lib/auth/provider";

export function AuthForm({ mode }: { mode: "sign-in" | "sign-up" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const signup = mode === "sign-up";
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const client = supabase();
    if (!client) {
      setError("Public Supabase configuration is missing.");
      setBusy(false);
      return;
    }
    const result = signup
      ? await client.auth.signUp({
          email,
          password,
          options: { emailRedirectTo: `${window.location.origin}/app` },
        })
      : await client.auth.signInWithPassword({ email, password });
    if (result.error) setError(result.error.message);
    else if (result.data.session) router.replace("/app");
    else setNotice("Check your email to confirm the account, then sign in.");
    setBusy(false);
  }
  return (
    <div className="auth-layout">
      <div className="auth-brand">
        <Link href="/" className="brand">
          Player<span>IQ</span>
          <small className="brand-tag">Performance intelligence</small>
        </Link>
        <div className="auth-copy">
          <div className="eyebrow !text-emerald-300">Train with clarity</div>
          <h1>Your football data, in focus.</h1>
          <p>
            Turn reviewed GPS reports into a clear picture of your sessions,
            records, and workload over time.
          </p>
          <div className="mt-8 flex items-center gap-2 text-xs text-emerald-200">
            <ShieldCheck size={16} /> Private by design · Grounded in your data
          </div>
        </div>
      </div>
      <div className="auth-form-wrap">
        <div className="auth-form">
          <span className="eyebrow">
            {signup ? "Create your account" : "Welcome back"}
          </span>
          <h2>
            {signup ? "Start tracking with PlayerIQ" : "Sign in to PlayerIQ"}
          </h2>
          <p className="page-subtitle">
            {signup
              ? "Your performance history starts here."
              : "Access your football GPS performance workspace."}
          </p>
          {!authConfigured && (
            <div className="error-box mt-5" role="alert">
              Add the public Supabase URL and publishable key to
              apps/web/.env.local to enable sign-in.
            </div>
          )}
          <form onSubmit={(event) => void submit(event)}>
            <label className="field">
              Email address
              <input
                className="input"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
              />
            </label>
            <label className="field">
              Password
              <input
                className="input"
                type="password"
                autoComplete={signup ? "new-password" : "current-password"}
                minLength={6}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 6 characters"
              />
            </label>
            {error && (
              <div className="error-box mt-4" role="alert">
                {error}
              </div>
            )}
            {notice && (
              <div className="info-box mt-4" role="status">
                {notice}
              </div>
            )}
            <button
              className="btn btn-dark"
              type="submit"
              disabled={busy || !authConfigured}
            >
              {busy ? "Please wait…" : signup ? "Create account" : "Sign in"}
              <ArrowRight size={16} />
            </button>
          </form>
          <div className="mt-6 border-t border-slate-200 pt-5 text-center text-xs text-slate-500">
            {signup ? "Already have an account?" : "New to PlayerIQ?"}{" "}
            <Link
              className="inline-link"
              href={signup ? "/auth/sign-in" : "/auth/sign-up"}
            >
              {signup ? "Sign in" : "Create account"}
            </Link>
          </div>
          <div className="mt-9 flex items-center justify-center gap-2 text-[11px] text-slate-400">
            <LockKeyhole size={13} /> Your account is protected by Supabase Auth
          </div>
        </div>
      </div>
    </div>
  );
}
