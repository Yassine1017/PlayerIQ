"use client";

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
  const [error, setError] = useState<string | null>(null);
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
          setError(
            reason instanceof Error ? reason.message : "Could not load chats",
          );
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
          reason instanceof Error
            ? reason.message
            : "Could not load conversation",
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
      setError(
        reason instanceof Error ? reason.message : "Could not finish analysis",
      );
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
          <span className="eyebrow">Interpretation backed by evidence</span>
          <h1 className="page-title">AI Analyst</h1>
          <p className="page-subtitle">
            Ask questions about {player.display_name}&apos;s GPS history.
            PlayerIQ calculates the facts; AI explains them.
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
          <MessageSquarePlus size={17} /> New conversation
        </button>
      </div>
      <div className="analyst-layout">
        <aside className="analyst-history card" aria-label="Conversations">
          <h2>Conversations</h2>
          {loading || loadedPlayerId !== player.id ? (
            <Loading label="Loading conversations…" />
          ) : threads.length === 0 ? (
            <p>No conversations yet.</p>
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
                  <span>{thread.title || "Analysis"}</span>
                  <ArrowRight size={14} />
                </button>
              ))}
            </div>
          )}
        </aside>
        <section
          className="analyst-conversation card"
          aria-label="AI Analyst conversation"
        >
          {!threadId && messages.length === 0 && (
            <div className="analyst-welcome">
              <div className="analyst-welcome-icon">
                <Sparkles size={27} />
              </div>
              <span className="eyebrow">Your performance, explained</span>
              <h2>What would you like to know?</h2>
              <p>
                Ask about confirmed speed, workload, trends, and training
                sessions. Every number is calculated from your accepted history.
              </p>
              <div className="analyst-suggestions">
                {suggestions.map((question) => (
                  <button
                    type="button"
                    key={question}
                    onClick={() => void send(question)}
                    disabled={sending}
                  >
                    {question}
                    <ArrowRight size={15} />
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
                    <span>You</span>
                    <p>{message.question}</p>
                  </div>
                ) : message.analysis ? (
                  <AnswerCard key={message.id} result={message.analysis} />
                ) : null,
              )}
            </div>
          )}
          {threadLoading && <Loading label="Loading conversation…" />}
          {sending && (
            <div className="analyst-thinking" role="status">
              <Sparkles size={18} /> PlayerIQ is analyzing your history…
            </div>
          )}
          {error && (
            <div className="analyst-error">
              <ErrorState
                message={error}
                onRetry={
                  pending ? () => void send(pending.question, true) : undefined
                }
              />
            </div>
          )}
          <form onSubmit={submit} className="analyst-composer">
            <label htmlFor="analyst-question">
              Ask PlayerIQ about your history
            </label>
            <div>
              <textarea
                id="analyst-question"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={600}
                rows={2}
                placeholder="How has my maximum speed changed recently?"
                disabled={sending}
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={sending || !draft.trim()}
                aria-label="Send question"
              >
                <Send size={18} />
              </button>
            </div>
            <small>
              AI interpretation. Verified facts and source sessions are shown
              with each answer.
            </small>
          </form>
        </section>
      </div>
    </div>
  );
}
