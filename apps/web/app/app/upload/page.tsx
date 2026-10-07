"use client";
import { useLocale } from "@/components/localization/locale-provider";

import { ArrowRight, FileText, FolderOpen, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { ErrorState, Loading, EmptyState } from "@/components/ui/states";
import { Status } from "@/components/ui/status";
import { useAuth } from "@/lib/auth/provider";
import { useResource } from "@/lib/data/use-resource";
import { dateLabel } from "@/lib/format";
import { validatePdf } from "@/lib/upload";
import { useApp } from "@/components/layout/app-frame";
import type { SessionType } from "@/lib/api/types";

export default function UploadPage() {
  const { tr, ui, locale } = useLocale();

  const { api } = useAuth();
  const { teams } = useApp();
  const [teamId, setTeamId] = useState("");
  const [sessionType, setSessionType] = useState<SessionType>("unknown");
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | Error | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [cursor, setCursor] = useState<string | undefined>();
  const load = useCallback(
    (signal: AbortSignal) => api.uploads(15, cursor, signal),
    [api, cursor],
  );
  const uploads = useResource(`uploads:${cursor ?? "first"}`, load);
  function pick(value: File | null) {
    setError(null);
    setProgress(null);
    if (!value) return;
    const validation = validatePdf(value);
    if (validation) {
      setFile(null);
      setError(validation);
    } else setFile(value);
  }
  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setProgress(0);
    try {
      const result = await api.uploadPdf(
        file,
        setProgress,
        teamId || undefined,
        sessionType,
      );
      router.push(`/app/uploads/${result.upload_id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason : "Upload failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{tr("Add to your history")}</span>
          <h1 className="page-title">{tr("Upload GPS report")}</h1>
          <p className="page-subtitle">
            {tr(
              "Import a whole report into your team, or upload privately to connect your own athlete row.",
            )}
          </p>
        </div>
      </div>
      <div className="grid-2">
        <section className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="section-title">{tr("Choose a report")}</h2>
              <p className="section-subtitle">
                {tr("Supported football GPS PDF layout · maximum 10 MB")}
              </p>
            </div>
            <UploadCloud className="text-accent-text" size={21} />
          </div>
          <div
            className={`upload-drop ${dragging ? "dragging" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pick(e.dataTransfer.files[0] ?? null);
            }}
          >
            <div>
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-accent-soft text-accent-text">
                <UploadCloud size={25} />
              </div>
              <strong className="mt-3 block text-sm">
                {tr("Drag your PDF here")}
              </strong>
              <div className="mt-1 text-xs text-muted">
                {tr("or select a file from your computer")}
              </div>
              <input
                ref={input}
                type="file"
                accept="application/pdf,.pdf"
                className="sr-only"
                aria-label={tr("Select GPS PDF")}
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
              <button
                type="button"
                className="btn btn-quiet mt-4"
                onClick={() => input.current?.click()}
              >
                {tr("Browse files")}
              </button>
            </div>
          </div>
          {file && (
            <div className="mt-4 flex items-center gap-3 rounded-lg border border-line bg-surface-muted p-3">
              <FileText size={19} className="text-accent-text" />
              <div className="min-w-0 flex-1">
                <strong className="block truncate text-xs">
                  <bdi dir="auto">{file.name}</bdi>
                </strong>
                <span className="small muted">
                  {new Intl.NumberFormat(locale, {
                    numberingSystem: "latn",
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  }).format(file.size / 1024 / 1024)}{" "}
                  {tr("MB · PDF")}
                </span>
              </div>
              <button
                type="button"
                className="inline-link"
                onClick={() => {
                  setFile(null);
                  if (input.current) input.current.value = "";
                }}
              >
                {tr("Remove")}
              </button>
            </div>
          )}
          {teams.some((t) => t.role !== "player") && (
            <label className="field mt-4">
              {tr("Report workspace")}
              <select
                className="select"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
              >
                <option value="">{tr("Private to my account")}</option>
                {teams
                  .filter((t) => t.role !== "player")
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} {tr("team workspace")}
                    </option>
                  ))}
              </select>
              <span className="helper">
                {tr(
                  "Selecting a team and uploading authorizes automatic import of all its identifiable athletes, including nonparticipants. Eligible sessions are shared with the team. The PDF and review stay private to you.",
                )}
              </span>
            </label>
          )}
          {teamId && (
            <label className="field mt-4">
              {tr("Team session type")}
              <select
                className="select"
                value={sessionType}
                onChange={(e) => setSessionType(e.target.value as SessionType)}
              >
                <option value="unknown">{tr("Unknown")}</option>
                <option value="training">{tr("Training")}</option>
                <option value="match">{tr("Match")}</option>
              </select>
            </label>
          )}
          {progress !== null && (
            <div className="mt-4">
              <div className="mb-1 flex justify-between text-xs">
                <span>{tr("Uploading securely")}</span>
                <span>{progress}%</span>
              </div>
              <div className="h-2 rounded-full bg-surface-muted">
                <div
                  className="h-2 rounded-full bg-accent-soft0"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}
          {error && (
            <div className="error-box mt-4" role="alert">
              {ui(error)}
            </div>
          )}
          <button
            className="btn btn-primary mt-5"
            disabled={!file || busy}
            type="button"
            onClick={() => void submit()}
          >
            {busy
              ? tr("Uploading…")
              : teamId
                ? tr("Upload and import team athletes")
                : tr("Upload and process report")}
            <ArrowRight size={15} className="directional-icon" />
          </button>
        </section>
        <section className="card card-pad">
          <h2 className="section-title">{tr("What happens next")}</h2>
          <p className="section-subtitle mb-5">
            {tr("Your report stays private while each step is checked.")}
          </p>
          {[
            {
              n: "01",
              title: "Secure processing",
              text: "The backend extracts the supported session and athlete metrics.",
            },
            {
              n: "02",
              title: "Review source rows",
              text: "Printed chart labels are extracted automatically. Uncertain values remain available for review.",
            },
            {
              n: "03",
              title: teamId ? "Import your team" : "Connect your identity",
              text: teamId
                ? "Identifiable athletes join the roster. Eligible sessions appear in the team workspace; conflicts stay in review."
                : "Confirm your athlete row to add accepted data to your personal history.",
            },
          ].map((item) => (
            <div className="flex gap-4 border-t border-line py-4" key={item.n}>
              <span className="font-mono text-xs font-bold text-accent-text">
                {item.n}
              </span>
              <div>
                <strong className="text-xs">{ui(item.title)}</strong>
                <p className="mt-1 mb-0 text-xs leading-5 text-muted">
                  {ui(item.text)}
                </p>
              </div>
            </div>
          ))}
        </section>
      </div>
      <section className="card card-pad">
        <div className="card-head">
          <div>
            <h2 className="section-title">{tr("Recent uploads")}</h2>
            <p className="section-subtitle">
              {tr("Only reports uploaded by this account appear here")}
            </p>
          </div>
          <FolderOpen size={18} className="text-muted" />
        </div>
        {uploads.loading ? (
          <Loading />
        ) : uploads.error ? (
          <ErrorState message={uploads.error} onRetry={uploads.refresh} />
        ) : !uploads.data?.items.length ? (
          <EmptyState title={tr("No reports uploaded yet")}>
            {tr("Your processed reports will appear here.")}
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{tr("Uploaded")}</th>
                    <th>{tr("File")}</th>
                    <th>{tr("Status")}</th>
                    <th>{tr("Athlete rows")}</th>
                    <th>
                      <span className="sr-only">{tr("Action")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {uploads.data.items.map((item) => (
                    <tr key={item.upload_id}>
                      <td>{dateLabel(item.created_at, locale)}</td>
                      <td className="font-bold">
                        <bdi dir="auto">{item.original_filename}</bdi>
                      </td>
                      <td>
                        <Status value={item.status} />
                      </td>
                      <td>{item.athlete_row_count ?? "—"}</td>
                      <td>
                        <Link
                          className="inline-link"
                          href={`/app/uploads/${item.upload_id}`}
                        >
                          {tr("Open →")}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {uploads.data.next_cursor && (
              <button
                type="button"
                className="btn btn-quiet mt-4"
                onClick={() =>
                  setCursor(uploads.data?.next_cursor ?? undefined)
                }
              >
                {tr("More uploads")}
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
