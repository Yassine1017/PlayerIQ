"use client";

import { ShieldCheck, UserRound } from "lucide-react";
import { useState } from "react";
import { useApp } from "@/components/layout/app-frame";
import { useAuth } from "@/lib/auth/provider";

export default function ProfilePage() {
  const { api } = useAuth();
  const { me, player, refreshIdentity } = useApp();
  const [name, setName] = useState(me.profile?.display_name ?? "");
  const [timezone, setTimezone] = useState(me.profile?.timezone ?? "UTC");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
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
      setError(
        reason instanceof Error ? reason.message : "Could not save profile",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Your account</span>
          <h1 className="page-title">Profile & settings</h1>
          <p className="page-subtitle">
            Manage the display details used in your PlayerIQ workspace.
          </p>
        </div>
      </div>
      <div className="grid-2">
        <section className="card card-pad">
          <div className="card-head">
            <h2 className="section-title">Your profile</h2>
            <UserRound size={19} className="text-emerald-600" />
          </div>
          <form className="grid gap-4" onSubmit={(event) => void save(event)}>
            <label className="field">
              Display name
              <input
                className="input"
                required
                maxLength={160}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="field">
              IANA time zone
              <input
                className="input"
                required
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                placeholder="e.g. Asia/Riyadh"
              />
            </label>
            {error && (
              <div className="error-box" role="alert">
                {error}
              </div>
            )}
            {message && (
              <div className="info-box" role="status">
                {message}
              </div>
            )}
            <div>
              <button type="submit" disabled={busy} className="btn btn-primary">
                {busy ? "Saving…" : "Save profile"}
              </button>
            </div>
          </form>
        </section>
        <section className="card card-pad">
          <div className="card-head">
            <h2 className="section-title">Player access</h2>
            <ShieldCheck size={19} className="text-emerald-600" />
          </div>
          <div className="key-value">
            <span>Selected player</span>
            <strong>{player.display_name}</strong>
          </div>
          <div className="key-value">
            <span>Profile type</span>
            <strong>
              {player.owner_user_id === me.user_id
                ? "Owned player"
                : "Granted access"}
            </strong>
          </div>
          <p className="helper mt-4">
            Report uploads and chart reviews remain available only to the
            uploader. A linked player sees their own accepted session values.
          </p>
        </section>
      </div>
    </div>
  );
}
