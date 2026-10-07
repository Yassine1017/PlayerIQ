"use client";
import { useLocale } from "@/components/localization/locale-provider";
import type { TeamAverage } from "@/lib/api/types";
import { metricDisplay } from "@/lib/format";

export function TeamAverageCard({
  title,
  average,
  manager,
  hasSession,
}: {
  title: string;
  average: TeamAverage | null | undefined;
  manager: boolean;
  hasSession: boolean;
}) {
  const { tr, ui, locale } = useLocale();

  return (
    <div className="card card-pad">
      <span className="eyebrow">{ui(title)}</span>
      <strong className="block mt-3 text-2xl">
        <bdi dir="ltr">
          {average?.status === "ok"
            ? metricDisplay(average.value, average.unit, locale)
            : "—"}
        </bdi>
      </strong>
      <span className="helper block">
        {!manager
          ? tr("Private to team managers")
          : !hasSession
            ? tr("No accepted team session")
            : average?.status === "not_comparable"
              ? tr("Source definitions differ")
              : average?.status !== "ok"
                ? tr("No accepted metric values")
                : tr("metricParticipantCount", { count: average.sample_size })}
      </span>
      {ui(title) === tr("Average Player Load") && manager && (
        <span className="helper block mt-1">
          {tr("Reported index · same activity only")}
        </span>
      )}
    </div>
  );
}
