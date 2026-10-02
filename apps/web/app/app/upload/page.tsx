"use client";

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
  const { api } = useAuth();
  const { teams } = useApp();
  const [teamId, setTeamId] = useState("");
  const [sessionType, setSessionType] = useState<SessionType>("unknown");
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
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
      setError(reason instanceof Error ? reason.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <span className="eyebrow">Add to your history</span>
          <h1 className="page-title">Upload GPS report</h1>
          <p className="page-subtitle">
            Import a whole report into your team, or upload privately to connect
            your own athlete row.
          </p>
        </div>
      </div>
      <div className="grid-2">
        <section className="card card-pad">
          <div className="card-head">
            <div>
              <h2 className="section-title">Choose a report</h2>
              <p className="section-subtitle">
                Supported football GPS PDF layout · maximum 10 MB
              </p>
            </div>
            <UploadCloud className="text-emerald-600" size={21} />
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
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-emerald-100 text-emerald-700">
                <UploadCloud size={25} />
              </div>
              <strong className="mt-3 block text-sm">Drag your PDF here</strong>
              <div className="mt-1 text-xs text-slate-500">
                or select a file from your computer
              </div>
              <input
                ref={input}
                type="file"
                accept="application/pdf,.pdf"
                className="sr-only"
                aria-label="Select GPS PDF"
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
              <button
                type="button"
                className="btn btn-quiet mt-4"
                onClick={() => input.current?.click()}
              >
                Browse files
              </button>
            </div>
          </div>
          {file && (
            <div className="mt-4 flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <FileText size={19} className="text-emerald-600" />
              <div className="min-w-0 flex-1">
                <strong className="block truncate text-xs">{file.name}</strong>
                <span className="small muted">
                  {(file.size / 1024 / 1024).toFixed(2)} MB · PDF
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
                Remove
              </button>
            </div>
          )}
          {teams.some((t) => t.role !== "player") && (
            <label className="field mt-4">
              Report workspace
              <select
                className="select"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
              >
                <option value="">Private to my account</option>
                {teams
                  .filter((t) => t.role !== "player")
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} team workspace
                    </option>
                  ))}
              </select>
              <span className="helper">
                Selecting a team and uploading authorizes automatic import of
                all its identifiable athletes, including nonparticipants.
                Eligible sessions are shared with the team. The PDF and review
                stay private to you.
              </span>
            </label>
          )}
          {teamId && (
            <label className="field mt-4">
              Team session type
              <select
                className="select"
                value={sessionType}
                onChange={(e) => setSessionType(e.target.value as SessionType)}
              >
                <option value="unknown">Unknown</option>
                <option value="training">Training</option>
                <option value="match">Match</option>
              </select>
            </label>
          )}
          {progress !== null && (
            <div className="mt-4">
              <div className="mb-1 flex justify-between text-xs">
                <span>Uploading securely</span>
                <span>{progress}%</span>
              </div>
              <div className="h-2 rounded-full bg-slate-100">
                <div
                  className="h-2 rounded-full bg-emerald-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}
          {error && (
            <div className="error-box mt-4" role="alert">
              {error}
            </div>
          )}
          <button
            className="btn btn-primary mt-5"
            disabled={!file || busy}
            type="button"
            onClick={() => void submit()}
          >
            {busy
              ? "Uploading…"
              : teamId
                ? "Upload and import team athletes"
                : "Upload and process report"}
            <ArrowRight size={15} />
          </button>
        </section>
        <section className="card card-pad">
          <h2 className="section-title">What happens next</h2>
          <p className="section-subtitle mb-5">
            Your report stays private while each step is checked.
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
            <div
              className="flex gap-4 border-t border-slate-100 py-4"
              key={item.n}
            >
              <span className="font-mono text-xs font-bold text-emerald-600">
                {item.n}
              </span>
              <div>
                <strong className="text-xs">{item.title}</strong>
                <p className="mt-1 mb-0 text-xs leading-5 text-slate-500">
                  {item.text}
                </p>
              </div>
            </div>
          ))}
        </section>
      </div>
      <section className="card card-pad">
        <div className="card-head">
          <div>
            <h2 className="section-title">Recent uploads</h2>
            <p className="section-subtitle">
              Only reports uploaded by this account appear here
            </p>
          </div>
          <FolderOpen size={18} className="text-slate-400" />
        </div>
        {uploads.loading ? (
          <Loading />
        ) : uploads.error ? (
          <ErrorState
            message={uploads.error.message}
            onRetry={uploads.refresh}
          />
        ) : !uploads.data?.items.length ? (
          <EmptyState title="No reports uploaded yet">
            Your processed reports will appear here.
          </EmptyState>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Uploaded</th>
                    <th>File</th>
                    <th>Status</th>
                    <th>Athlete rows</th>
                    <th>
                      <span className="sr-only">Action</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {uploads.data.items.map((item) => (
                    <tr key={item.upload_id}>
                      <td>{dateLabel(item.created_at)}</td>
                      <td className="font-bold">{item.original_filename}</td>
                      <td>
                        <Status value={item.status} />
                      </td>
                      <td>{item.athlete_row_count ?? "—"}</td>
                      <td>
                        <Link
                          className="inline-link"
                          href={`/app/uploads/${item.upload_id}`}
                        >
                          Open →
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
                More uploads
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
