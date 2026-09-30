import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AnalystPage from "@/app/app/analyst/page";
import { AnswerCard } from "@/components/analyst/answer-card";
import type { AnalystResponse } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  chats: vi.fn(),
  createChat: vi.fn(),
  chatMessages: vi.fn(),
  askAnalyst: vi.fn(),
}));
vi.mock("@/components/layout/app-frame", () => ({
  useApp: () => ({
    player: { id: "synthetic-player", display_name: "Synthetic Player" },
  }),
}));
vi.mock("@/lib/auth/provider", () => ({
  useAuth: () => ({ api: mocks }),
}));
const result: AnalystResponse = {
  run_id: "synthetic-run",
  player_id: "synthetic-player",
  thread_id: "synthetic-thread",
  session_id: null,
  answer: {
    status: "answered",
    sentences: [
      {
        text: "Your confirmed speed is available.",
        fact_ids: ["FACT_001"],
        session_ids: ["synthetic-session"],
      },
    ],
  },
  facts: [
    {
      fact_id: "FACT_001",
      kind: "personal_record",
      metric_key: "maximum_velocity_kmh",
      role: "value",
      raw_value: "30.400",
      display_value: "30.4",
      unit: "km/h",
      rule_version: "analytics_v1",
      status: "ok",
      sample_size: 1,
      source_session_ids: ["synthetic-session"],
      source_observation_ids: ["synthetic-observation"],
      definition_id: "metrics_v1",
      comparability_key: "metrics_v1:maximum_velocity_kmh",
    },
  ],
  results: [
    {
      tool: "get_personal_records",
      items: [
        {
          kind: "personal_record",
          status: "ok",
          metric_key: "maximum_velocity_kmh",
          fact_ids: ["FACT_001"],
          session_ids: ["synthetic-session"],
          source_observation_ids: ["synthetic-observation"],
          source_ids_truncated: false,
          from_date: null,
          to_date: "2026-01-01",
          note: null,
          rule_version: "analytics_v1",
        },
      ],
    },
  ],
  generated_at: "2026-01-01T00:00:00Z",
  model: "synthetic-model",
  provider: "fake",
  prompt_version: "analyst_v1",
  analytics_rule_version: "analytics_v1",
  history_fingerprint: "synthetic-fingerprint",
  stale: false,
};
beforeEach(() => {
  mocks.chats.mockResolvedValue({ items: [], next_cursor: null });
  mocks.createChat.mockResolvedValue({
    id: "synthetic-thread",
    title: "Speed",
    player_id: "synthetic-player",
  });
  mocks.chatMessages.mockResolvedValue({
    items: [
      {
        id: "q1",
        role: "user",
        question: "How fast was I?",
        analysis: null,
        created_at: "2026-01-01",
      },
      {
        id: "a1",
        role: "assistant",
        question: null,
        analysis: result,
        created_at: "2026-01-01",
      },
    ],
    next_cursor: null,
  });
  mocks.askAnalyst.mockResolvedValue(result);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("shows evidence and session link without exposing internal fact IDs", () => {
  render(<AnswerCard result={result} />);
  expect(screen.getAllByText("30.4 km/h").length).toBeGreaterThan(0);
  expect(screen.getByRole("link", { name: /session/i })).toHaveAttribute(
    "href",
    "/app/sessions/synthetic-session",
  );
  expect(screen.getByText(/How calculated/i)).toBeInTheDocument();
  expect(
    screen.getByText("analytics_v1", { exact: false }),
  ).toBeInTheDocument();
  expect(screen.queryByText("FACT_001")).not.toBeInTheDocument();
});

it("marks historical analysis stale", () => {
  render(<AnswerCard result={{ ...result, stale: true }} />);
  expect(screen.getByRole("status")).toHaveTextContent(
    /older version of your session history/i,
  );
});

it("explains missing, noncomparable, and ambiguous results in plain language", () => {
  render(
    <AnswerCard
      result={{
        ...result,
        answer: {
          status: "insufficient_data",
          sentences: [
            {
              text: "The available history cannot answer this yet.",
              fact_ids: [],
              session_ids: [],
            },
          ],
        },
        facts: [],
        results: [
          {
            tool: "get_metric_trend",
            items: [
              "insufficient_history",
              "not_comparable",
              "ambiguous_order",
            ].map((status) => ({
              kind: "trend",
              status,
              metric_key: "maximum_velocity_kmh",
              fact_ids: [],
              session_ids: [],
              source_observation_ids: [],
              source_ids_truncated: false,
              from_date: null,
              to_date: null,
              note: null,
              rule_version: "analytics_v1",
            })),
          },
        ],
      }}
    />,
  );
  expect(
    screen.getByText(/More comparable accepted sessions/i),
  ).toBeInTheDocument();
  expect(screen.getByText(/cannot be compared/i)).toBeInTheDocument();
  expect(screen.getByText(/cannot be ordered reliably/i)).toBeInTheDocument();
});

it("creates a chat and sends a suggested question", async () => {
  render(<AnalystPage />);
  expect(
    await screen.findByText("What would you like to know?"),
  ).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: /hardest training session/i }),
  );
  await waitFor(() => expect(mocks.createChat).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(mocks.askAnalyst).toHaveBeenCalledTimes(1));
  expect(mocks.askAnalyst.mock.calls[0][2]).toMatch(/hardest training session/);
  expect(
    await screen.findByText("Your confirmed speed is available."),
  ).toBeInTheDocument();
});
