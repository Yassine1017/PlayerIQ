"use client";
import { useLocale } from "@/components/localization/locale-provider";
import { interfaceText } from "@/lib/i18n";
import { statusText, factDisplay } from "@/lib/format";
import type { Locale } from "@/lib/i18n/locale";
import Link from "next/link";
import { ArrowUpRight, DatabaseZap, Info, Sparkles } from "lucide-react";
import type { AnalystResponse, AnalystFact } from "@/lib/api/types";
import { metricLabels } from "@/lib/api/types";

function factLabel(fact: AnalystFact, locale: Locale) {
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
  return `${interfaceText(locale, metric)} · ${interfaceText(locale, role[fact.role] ?? "Unavailable")}`;
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
  const { tr, ui, locale } = useLocale();

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
  const budgetExhausted = result.error_code === "ai_budget_exhausted";
  return (
    <article
      className="analyst-answer"
      aria-label={tr("PlayerIQ Analyst answer")}
    >
      <div className="analyst-answer-head">
        <span className="analyst-mark">
          <Sparkles size={17} />
        </span>
        <div>
          <strong>{tr("PlayerIQ Analyst")}</strong>
          <span>{tr("Interpretation grounded in your sessions")}</span>
        </div>
        <span className="analyst-state">
          {result.answer.status === "answered"
            ? tr("Verified")
            : result.answer.status === "insufficient_data"
              ? tr("Limited data")
              : tr("Unavailable")}
        </span>
      </div>
      {result.stale && (
        <div className="analyst-notice" role="status">
          {tr(
            "This analysis was generated from an older version of your session history. Ask again for a current answer.",
          )}
        </div>
      )}
      <div className="analyst-prose">
        {budgetExhausted ? (
          <p>
            {tr(
              "AI Analyst is temporarily unavailable because this month's AI usage limit has been reached.",
            )}
          </p>
        ) : (
          result.answer.sentences.map((sentence, index) => (
            <p key={index} dir="auto">
              {sentence.text}
              {sentence.fact_ids.length > 0 && (
                <span className="analyst-inline-facts">
                  {sentence.fact_ids.map((id) => {
                    const fact = facts.get(id);
                    return fact ? (
                      <span className="analyst-inline-fact" key={id}>
                        <bdi dir="ltr">
                          {factDisplay(fact.display_value, locale)}{" "}
                          {fact.unit === "%" ? "" : fact.unit}
                        </bdi>
                      </span>
                    ) : null;
                  })}
                </span>
              )}
            </p>
          ))
        )}
      </div>
      {limitations.length > 0 && (
        <div className="analyst-limitations" role="note">
          {limitations.map((message) => (
            <p key={message}>{ui(message)}</p>
          ))}
        </div>
      )}
      {shown.length > 0 && (
        <div className="analyst-evidence">
          <div className="analyst-section-title">
            <DatabaseZap size={16} /> {tr("Verified facts")}
          </div>
          <div className="analyst-fact-grid">
            {shown.map((fact) => (
              <div className="analyst-fact" key={fact.fact_id}>
                <span>{factLabel(fact, locale)}</span>
                <strong>
                  <bdi dir="ltr">
                    {factDisplay(fact.display_value, locale)}{" "}
                    {fact.unit === "%" ? "" : fact.unit}
                  </bdi>
                </strong>
                <small>
                  {tr("{count} comparable sessions", {
                    count: fact.sample_size,
                  })}
                </small>
              </div>
            ))}
          </div>
        </div>
      )}
      {sources.length > 0 && (
        <div className="analyst-sources">
          <span>{tr("Source sessions")}</span>
          <div>
            {sources.slice(0, 12).map((id, index) => (
              <Link href={`/app/sessions/${id}`} key={id}>
                {tr("Session {number}", { number: index + 1 })}{" "}
                <ArrowUpRight size={13} className="directional-icon" />
              </Link>
            ))}
          </div>
        </div>
      )}
      <details className="analyst-method">
        <summary>
          <Info size={15} /> {tr("How calculated")}
        </summary>
        <p>
          {tr(
            "PlayerIQ used {rule} on accepted, linked sessions. Every displayed value came from a read-only backend tool; the AI wrote only the explanation. Missing, held, and noncomparable values are excluded from calculations.",
            { rule: result.analytics_rule_version },
          )}
        </p>
        {result.results.map((tool, index) => (
          <div key={`${tool.tool}-${index}`}>
            <strong>{tool.tool}</strong>
            <span>
              {tool.items
                .map((item) => statusText(item.status, locale))
                .join(", ")}
            </span>
          </div>
        ))}
      </details>
    </article>
  );
}
