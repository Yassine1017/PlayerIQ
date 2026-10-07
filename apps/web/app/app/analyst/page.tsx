"use client";
import { useLocale } from "@/components/localization/locale-provider";

import { ArrowRight, MessageSquarePlus, Send, Sparkles } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { AnswerCard } from "@/components/analyst/answer-card";
import { useApp } from "@/components/layout/app-frame";
import { ErrorState, Loading } from "@/components/ui/states";
import type { ChatMessage, ChatThread } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/provider";

const suggestions = [
  "How has my maximum speed changed recently?",
  "When was the last time I exceeded 30 km/h?",
  "What was my hardest training session?",
  "Compare my latest training to my previous five.",
  "Which performance metric improved the most?",
];

export default function AnalystPage() {
  const { tr, ui } = useLocale();

  const { api } = useAuth();
  const { player } = useApp();
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadedPlayerId, setLoadedPlayerId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [threadLoading, setThreadLoading] = useState(false);
  const activeThread = useRef<string | null>(null);
  const [error, setError] = useState<string | Error | null>(null);
  const [pending, setPending] = useState<{
    question: string;
    requestId: string;
  } | null>(null);

  const loadThreads = useCallback(async () => {
    const page = await api.chats(player.id);
    setThreads(page.items);
  }, [api, player.id]);
  const loadMessages = useCallback(
    async (id: string) => {
      const page = await api.chatMessages(player.id, id);
      if (activeThread.current === id) setMessages(page.items);
    },
    [api, player.id],
  );
  useEffect(() => {
    let active = true;
    api
      .chats(player.id)
      .then((page) => {
        if (active) {
          setThreads(page.items);
          activeThread.current = null;
          setThreadLoading(false);
          setThreadId(null);
          setMessages([]);
          setLoadedPlayerId(player.id);
        }
      })
      .catch((reason) => {
        if (active) {
          setThreads([]);
          setMessages([]);
          activeThread.current = null;
          setThreadLoading(false);
          setThreadId(null);
          setLoadedPlayerId(player.id);
          setError(reason instanceof Error ? reason : "Could not load chats");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [api, player.id]);

  async function openThread(id: string) {
    if (sending) return;
    activeThread.current = id;
    setThreadId(id);
    setMessages([]);
    setError(null);
    setThreadLoading(true);
    try {
      await loadMessages(id);
    } catch (reason) {
      if (activeThread.current === id)
        setError(
          reason instanceof Error ? reason : "Could not load conversation",
        );
    } finally {
      if (activeThread.current === id) setThreadLoading(false);
    }
  }
  async function send(question: string, retry = false) {
    const clean = question.trim();
    if (!clean || sending) return;
    const requestId =
      retry && pending ? pending.requestId : crypto.randomUUID();
    setPending({ question: clean, requestId });
    setSending(true);
    setError(null);
    try {
      let id = threadId;
      if (!id) {
        const thread = await api.createChat(player.id, clean.slice(0, 80));
        id = thread.id;
        activeThread.current = id;
        setThreadId(id);
        await loadThreads();
      }
      await api.askAnalyst(player.id, id, clean, requestId);
      await loadMessages(id);
      setDraft("");
      setPending(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason : "Could not finish analysis");
    } finally {
      setSending(false);
    }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send(draft);
  }

  return (
    <div className="stack analyst-page">
      <div className="page-heading analyst-heading">
        <div>
          <span className="eyebrow">
            {tr("Interpretation backed by evidence")}
          </span>
          <h1 className="page-title">{tr("AI Analyst")}</h1>
          <p className="page-subtitle">
            {tr(
              "Ask questions about {name}’s GPS history. PlayerIQ calculates the facts; AI explains them.",
              { name: player.display_name },
            )}
          </p>
        </div>
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => {
            activeThread.current = null;
            setThreadId(null);
            setMessages([]);
            setDraft("");
            setError(null);
          }}
          disabled={sending}
        >
          <MessageSquarePlus size={17} /> {tr("New conversation")}
        </button>
      </div>
      <div className="analyst-layout">
        <aside
          className="analyst-history card"
          aria-label={tr("Conversations")}
        >
          <h2>{tr("Conversations")}</h2>
          {loading || loadedPlayerId !== player.id ? (
            <Loading label={tr("Loading conversations…")} />
          ) : threads.length === 0 ? (
            <p>{tr("No conversations yet.")}</p>
          ) : (
            <div className="analyst-thread-list">
              {threads.map((thread) => (
                <button
                  type="button"
                  key={thread.id}
                  onClick={() => void openThread(thread.id)}
                  disabled={sending}
                  className={threadId === thread.id ? "active" : ""}
                >
                  <Sparkles size={15} />
                  <span dir="auto">{thread.title || tr("Analysis")}</span>
                  <ArrowRight size={14} className="directional-icon" />
                </button>
              ))}
            </div>
          )}
        </aside>
        <section
          className="analyst-conversation card"
          aria-label={tr("AI Analyst conversation")}
        >
          {!threadId && messages.length === 0 && (
            <div className="analyst-welcome">
              <div className="analyst-welcome-icon">
                <Sparkles size={27} />
              </div>
              <span className="eyebrow">
                {tr("Your performance, explained")}
              </span>
              <h2>{tr("What would you like to know?")}</h2>
              <p>
                {tr(
                  "Ask about confirmed speed, workload, trends, and training sessions. Every number is calculated from your accepted history.",
                )}
              </p>
              <div className="analyst-suggestions">
                {suggestions.map((question) => (
                  <button
                    type="button"
                    key={question}
                    onClick={() => void send(question)}
                    disabled={sending}
                  >
                    {ui(question)}
                    <ArrowRight size={15} className="directional-icon" />
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.length > 0 && (
            <div className="analyst-message-list" aria-live="polite">
              {messages.map((message) =>
                message.role === "user" ? (
                  <div className="analyst-question" key={message.id}>
                    <span>{tr("You")}</span>
                    <p dir="auto">{message.question}</p>
                  </div>
                ) : message.analysis ? (
                  <AnswerCard key={message.id} result={message.analysis} />
                ) : null,
              )}
            </div>
          )}
          {threadLoading && <Loading label={tr("Loading conversation…")} />}
          {sending && (
            <div className="analyst-thinking" role="status">
              <Sparkles size={18} /> {tr("PlayerIQ is analyzing your history…")}
            </div>
          )}
          {error && (
            <div className="analyst-error">
              <ErrorState
                message={ui(error)}
                onRetry={
                  pending ? () => void send(pending.question, true) : undefined
                }
              />
            </div>
          )}
          <form onSubmit={submit} className="analyst-composer">
            <label htmlFor="analyst-question">
              {tr("Ask PlayerIQ about your history")}
            </label>
            <div>
              <textarea
                id="analyst-question"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={600}
                rows={2}
                placeholder={tr("How has my maximum speed changed recently?")}
                disabled={sending}
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={sending || !draft.trim()}
                aria-label={tr("Send question")}
              >
                <Send size={18} />
              </button>
            </div>
            <small>
              {tr(
                "AI interpretation. Verified facts and source sessions are shown with each answer.",
              )}
            </small>
          </form>
        </section>
      </div>
    </div>
  );
}
