"use client";
import { useLocale } from "@/components/localization/locale-provider";

import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { authConfigured, supabase } from "@/lib/auth/provider";
import { LanguageControl } from "@/components/localization/language-control";
import { ThemeControl } from "@/components/theme/theme-control";

export function AuthForm({ mode }: { mode: "sign-in" | "sign-up" }) {
  const { tr, ui } = useLocale();

  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | Error | null>(null);
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
    if (result.error)
      setError(Object.assign(new Error(), { code: result.error.code }));
    else if (result.data.session) router.replace("/app");
    else setNotice("Check your email to confirm the account, then sign in.");
    setBusy(false);
  }
  return (
    <div className="auth-layout">
      <div className="auth-brand">
        <Link href="/" className="brand">
          Player<span>IQ</span>
          <small className="brand-tag">{tr("Performance intelligence")}</small>
        </Link>
        <div className="auth-copy">
          <div className="eyebrow !text-emerald-300">
            {tr("Train with clarity")}
          </div>
          <h1>{tr("Your football data, in focus.")}</h1>
          <p>
            {tr(
              "Turn reviewed GPS reports into a clear picture of your sessions, records, and workload over time.",
            )}
          </p>
          <div className="mt-8 flex items-center gap-2 text-xs text-emerald-200">
            <ShieldCheck size={16} />{" "}
            {tr("Private by design · Grounded in your data")}
          </div>
        </div>
      </div>
      <div className="auth-form-wrap">
        <div className="auth-form">
          <div className="flex justify-end mb-6">
            <div className="preference-controls">
              <ThemeControl />
              <LanguageControl />
            </div>
          </div>
          <span className="eyebrow">
            {signup ? tr("Create your account") : tr("Welcome back")}
          </span>
          <h2>
            {signup
              ? tr("Start tracking with PlayerIQ")
              : tr("Sign in to PlayerIQ")}
          </h2>
          <p className="page-subtitle">
            {signup
              ? tr("Your performance history starts here.")
              : tr("Access your football GPS performance workspace.")}
          </p>
          {!authConfigured && (
            <div className="error-box mt-5" role="alert">
              {tr(
                "Add the public Supabase URL and publishable key to apps/web/.env.local to enable sign-in.",
              )}
            </div>
          )}
          <form onSubmit={(event) => void submit(event)}>
            <label className="field">
              {tr("Email address")}
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
              {tr("Password")}
              <input
                className="input"
                type="password"
                autoComplete={signup ? "new-password" : "current-password"}
                minLength={6}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={tr("At least 6 characters")}
              />
            </label>
            {error && (
              <div className="error-box mt-4" role="alert">
                {ui(error)}
              </div>
            )}
            {notice && (
              <div className="info-box mt-4" role="status">
                {ui(notice)}
              </div>
            )}
            <button
              className="btn btn-dark"
              type="submit"
              disabled={busy || !authConfigured}
            >
              {busy
                ? tr("Please wait…")
                : signup
                  ? tr("Create account")
                  : tr("Sign in")}
              <ArrowRight size={16} className="directional-icon" />
            </button>
          </form>
          <div className="mt-6 border-t border-line pt-5 text-center text-xs text-muted">
            {signup ? tr("Already have an account?") : tr("New to PlayerIQ?")}{" "}
            <Link
              className="inline-link"
              href={signup ? "/auth/sign-in" : "/auth/sign-up"}
            >
              {signup ? tr("Sign in") : tr("Create account")}
            </Link>
          </div>
          <div className="mt-9 flex items-center justify-center gap-2 text-[11px] text-muted">
            <LockKeyhole size={13} />{" "}
            {tr("Your account is protected by Supabase Auth")}
          </div>
        </div>
      </div>
    </div>
  );
}
