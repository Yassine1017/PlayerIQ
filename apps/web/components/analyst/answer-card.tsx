import Link from "next/link";
import { ArrowUpRight, DatabaseZap, Info, Sparkles } from "lucide-react";
import type { AnalystResponse, AnalystFact } from "@/lib/api/types";
import { metricLabels } from "@/lib/api/types";

function factLabel(fact: AnalystFact) {
  const metric = fact.metric_key
    ? (metricLabels[fact.metric_key] ?? fact.metric_key.replaceAll("_", " "))
    : "Value";
  const role: Record<string, string> = {
    value: "Recorded value",
    baseline: "Comparable baseline",
    delta: "Change",
    percent_change: "Percentage change",
    slope_per_week: "Weekly slope",
    median: "Prior median",
    mad: "Median absolute deviation",
    modified_z_score: "Outlier score",
  };
  return `${metric} · ${role[fact.role] ?? fact.role}`;
}

const resultMessages: Record<string, string> = {
  missing_metric: "No accepted value is available for this metric.",
  insufficient_history:
    "More comparable accepted sessions are needed for this calculation.",
  not_comparable:
    "These sessions cannot be compared under the available GPS definitions.",
  not_found: "No accepted session meets that condition.",
  ambiguous_order: "Sessions on the same date cannot be ordered reliably.",
};

export function AnswerCard({ result }: { result: AnalystResponse }) {
  const facts = new Map(result.facts.map((fact) => [fact.fact_id, fact]));
  const cited = new Set(
    result.answer.sentences.flatMap((sentence) => sentence.fact_ids),
  );
  const shown = result.facts.filter((fact) => cited.has(fact.fact_id));
  const sources = Array.from(
    new Set(
      result.answer.sentences.flatMap((sentence) => sentence.session_ids),
    ),
  );
  const limitations = Array.from(
    new Set(
      result.results.flatMap((tool) =>
        tool.items
          .filter((item) => item.status !== "ok")
          .map(
            (item) =>
              resultMessages[item.status] ?? "This calculation is unavailable.",
          ),
      ),
    ),
  );
  return (
    <article className="analyst-answer" aria-label="PlayerIQ Analyst answer">
      <div className="analyst-answer-head">
        <span className="analyst-mark">
          <Sparkles size={17} />
        </span>
        <div>
          <strong>PlayerIQ Analyst</strong>
          <span>Interpretation grounded in your sessions</span>
        </div>
        <span className="analyst-state">
          {result.answer.status === "answered"
            ? "Verified"
            : result.answer.status === "insufficient_data"
              ? "Limited data"
              : "Unavailable"}
        </span>
      </div>
      {result.stale && (
        <div className="analyst-notice" role="status">
          This analysis was generated from an older version of your session
          history. Ask again for a current answer.
        </div>
      )}
      <div className="analyst-prose">
        {result.answer.sentences.map((sentence, index) => (
          <p key={index}>
            {sentence.text}
            {sentence.fact_ids.length > 0 && (
              <span className="analyst-inline-facts">
                {sentence.fact_ids.map((id) => {
                  const fact = facts.get(id);
                  return fact ? (
                    <span className="analyst-inline-fact" key={id}>
                      {fact.display_value} {fact.unit === "%" ? "" : fact.unit}
                    </span>
                  ) : null;
                })}
              </span>
            )}
          </p>
        ))}
      </div>
      {limitations.length > 0 && (
        <div className="analyst-limitations" role="note">
          {limitations.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}
      {shown.length > 0 && (
        <div className="analyst-evidence">
          <div className="analyst-section-title">
            <DatabaseZap size={16} /> Verified facts
          </div>
          <div className="analyst-fact-grid">
            {shown.map((fact) => (
              <div className="analyst-fact" key={fact.fact_id}>
                <span>{factLabel(fact)}</span>
                <strong>
                  {fact.display_value} {fact.unit === "%" ? "" : fact.unit}
                </strong>
                <small>
                  {fact.sample_size} comparable{" "}
                  {fact.sample_size === 1 ? "session" : "sessions"}
                </small>
              </div>
            ))}
          </div>
        </div>
      )}
      {sources.length > 0 && (
        <div className="analyst-sources">
          <span>Source sessions</span>
          <div>
            {sources.slice(0, 12).map((id, index) => (
              <Link href={`/app/sessions/${id}`} key={id}>
                Session {index + 1} <ArrowUpRight size={13} />
              </Link>
            ))}
          </div>
        </div>
      )}
      <details className="analyst-method">
        <summary>
          <Info size={15} /> How calculated
        </summary>
        <p>
          PlayerIQ used {result.analytics_rule_version} on accepted, linked
          sessions. Every displayed value came from a read-only backend tool;
          the AI wrote only the explanation. Missing, held, and noncomparable
          values are excluded from calculations.
        </p>
        {result.results.map((tool, index) => (
          <div key={`${tool.tool}-${index}`}>
            <strong>
              {tool.tool.replaceAll("get_", "").replaceAll("_", " ")}
            </strong>
            <span>
              {tool.items
                .map((item) => item.status.replaceAll("_", " "))
                .join(", ")}
            </span>
          </div>
        ))}
      </details>
    </article>
  );
}
