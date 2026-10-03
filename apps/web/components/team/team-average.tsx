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
  return (
    <div className="card card-pad">
      <span className="eyebrow">{title}</span>
      <strong className="block mt-3 text-2xl">
        {average?.status === "ok"
          ? metricDisplay(average.value, average.unit)
          : "—"}
      </strong>
      <span className="helper block">
        {!manager
          ? "Private to team managers"
          : !hasSession
            ? "No accepted team session"
            : average?.status === "not_comparable"
              ? "Source definitions differ"
              : average?.status !== "ok"
                ? "No accepted metric values"
                : `${average.sample_size} accepted ${average.sample_size === 1 ? "player" : "players"} with this metric`}
      </span>
      {title === "Average Player Load" && manager && (
        <span className="helper block mt-1">
          Reported index · same activity only
        </span>
      )}
    </div>
  );
}
