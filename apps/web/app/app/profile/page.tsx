"use client";
import { dateLabel } from "@/lib/format";
import { useLocale } from "@/components/localization/locale-provider";

import { ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import Link from "next/link";
import { useApp } from "@/components/layout/app-frame";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { ErrorState, Loading } from "@/components/ui/states";
import { useCallback } from "react";

export default function ProfilePage() {
  const { tr, ui, locale } = useLocale();

  const { api } = useAuth();
  const { me, player, refreshIdentity } = useApp();
  const loadIdentities = useCallback(
    (signal: AbortSignal) => api.sourceIdentities(signal),
    [api],
  );
  const identities = useResource("my-source-identities", loadIdentities);
  const [name, setName] = useState(me.profile?.display_name ?? "");
  const [timezone, setTimezone] = useState(me.profile?.timezone ?? "UTC");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | Error | null>(null);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await api.updateMe({
        display_name: name.trim(),
        timezone: timezone.trim(),
      });
      await refreshIdentity();
      setMessage("Profile updated.");
    } catch (reason) {
      setError(reason instanceof Error ? reason : "Could not save profile");
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    if (
      !window.confirm(
        "Disconnect this GPS source identity? Existing accepted sessions stay in your history; future rows will no longer be recognized.",
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await api.revokeSourceIdentity(id);
      identities.refresh();
      setMessage("GPS identity disconnected. Historical sessions remain.");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason : "Could not disconnect identity",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{tr("Your account")}</span>
          <h1 className="page-title">{tr("Profile & settings")}</h1>
          <p className="page-subtitle">
            {tr("Manage the display details used in your PlayerIQ workspace.")}
          </p>
        </div>
      </div>
      <div className="grid-2">
        <section className="card card-pad">
          <div className="card-head">
            <h2 className="section-title">{tr("Your profile")}</h2>
            <UserRound size={19} className="text-accent-text" />
          </div>
          <form className="grid gap-4" onSubmit={(event) => void save(event)}>
            <label className="field">
              {tr("Display name")}
              <input
                className="input"
                required
                maxLength={160}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="field">
              {tr("IANA time zone")}
              <input
                className="input"
                required
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                placeholder={tr("e.g. Asia/Riyadh")}
              />
            </label>
            {error && (
              <div className="error-box" role="alert">
                {ui(error)}
              </div>
            )}
            {message && (
              <div className="info-box" role="status">
                {ui(message)}
              </div>
            )}
            <div>
              <button type="submit" disabled={busy} className="btn btn-primary">
                {busy ? tr("Saving…") : tr("Save profile")}
              </button>
            </div>
          </form>
        </section>
        <section className="card card-pad">
          <div className="card-head">
            <h2 className="section-title">{tr("Player access")}</h2>
            <ShieldCheck size={19} className="text-accent-text" />
          </div>
          <div className="key-value">
            <span>{tr("My player")}</span>
            <strong>
              <bdi dir="auto">{player.display_name}</bdi>
            </strong>
          </div>
          <div className="key-value">
            <span>{tr("Profile type")}</span>
            <strong>{tr("Owned player")}</strong>
          </div>
          <p className="helper mt-4">
            {tr(
              "Report uploads and chart reviews remain available only to the uploader. A linked player sees their own accepted session values.",
            )}
          </p>
        </section>
      </div>
      <section className="card card-pad">
        <div className="card-head">
          <div>
            <h2 className="section-title">{tr("GPS identity")}</h2>
            <p className="section-subtitle">
              {tr(
                "A source label is connected only after you explicitly confirm your row.",
              )}
            </p>
          </div>
          <ShieldCheck size={19} className="text-accent-text" />
        </div>
        {identities.loading ? (
          <Loading />
        ) : identities.error ? (
          <ErrorState message={identities.error} onRetry={identities.refresh} />
        ) : !identities.data?.items.some(
            (item) => item.status === "connected",
          ) ? (
          <div className="info-box">
            {tr(
              "Not connected yet. Open one of your processed reports, select your athlete row, then choose “This is me.”",
            )}{" "}
            <Link href="/app/upload" className="inline-link ms-1">
              {tr("My Reports →")}
            </Link>
          </div>
        ) : (
          <div className="grid gap-3">
            {identities.data.items.map((item) => (
              <div
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3"
              >
                <div>
                  <span className="status success">
                    {item.status === "connected"
                      ? tr("Connected")
                      : tr("Revoked")}
                  </span>
                  <strong className="block mt-2 text-sm">
                    {item.original_label}
                  </strong>
                  <span className="helper">
                    {tr("Confirmed")}
                    {dateLabel(item.confirmed_at, locale)}
                  </span>
                </div>
                {item.status === "connected" && (
                  <button
                    type="button"
                    className="btn btn-quiet"
                    disabled={busy}
                    onClick={() => void revoke(item.id)}
                  >
                    {tr("Disconnect")}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
