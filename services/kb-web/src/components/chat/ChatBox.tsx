"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { Message, Source } from "@/types";
import { streamChat } from "@/lib/api";
import MessageBubble from "./MessageBubble";
import TypingIndicator from "./TypingIndicator";

const TOPICS = [
  { value: "", label: "全部主題" },
  { value: "resume", label: "📄 履歷" },
  { value: "interview", label: "🎤 面試" },
  { value: "salary", label: "💰 薪資談判" },
  { value: "career_planning", label: "🗺️ 職涯規劃" },
  { value: "job_search", label: "🔍 求職" },
  { value: "promotion", label: "📈 升遷" },
  { value: "workplace", label: "🏢 職場" },
  { value: "skill_development", label: "🛠️ 技能發展" },
  { value: "industry_insight", label: "🏭 產業洞察" },
  { value: "general_career", label: "💼 一般職涯" },
];

const MAX_ROUNDS = 50;

interface Props {
  sessionId: string | null;
  initialMessages: Message[];
  messageCount: number;
  onFirstMessage: (question: string) => void;
  onMessageCountChange: (count: number) => void;
}

export default function ChatBox({
  sessionId,
  initialMessages,
  messageCount,
  onFirstMessage,
  onMessageCountChange,
}: Props) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [topic, setTopic] = useState("");
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const isFirstMsg = useRef(messageCount === 0);

  useEffect(() => {
    setMessages(initialMessages);
    isFirstMsg.current = messageCount === 0;
  }, [initialMessages, messageCount]);

  useEffect(() => {
    if (boxRef.current)
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [messages]);

  const rounds = Math.floor(messageCount / 2);
  const atLimit = rounds >= MAX_ROUNDS;

  const handleSend = useCallback(async () => {
    if (!sessionId || !input.trim() || isStreaming || atLimit) return;
    const question = input.trim();
    setInput("");
    setIsStreaming(true);

    const userMsg: Message = { role: "user", content: question };
    setMessages((prev) => [...prev, userMsg]);

    let botText = "";
    let pendingSources: Source[] | null = null;
    let botMsgId: number | undefined;

    const botPlaceholder: Message = { role: "assistant", content: "" };
    setMessages((prev) => [...prev, botPlaceholder]);

    await streamChat(question, sessionId, topic || null, {
      onToken: (token) => {
        botText += token;
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            ...next[next.length - 1],
            content: botText,
          };
          return next;
        });
      },
      onMeta: (meta) => {
        if (meta.message_id) botMsgId = meta.message_id;
      },
      onSources: (sources) => {
        pendingSources = sources;
      },
      onDone: () => {
        if (isFirstMsg.current) {
          isFirstMsg.current = false;
          onFirstMessage(question.slice(0, 50));
        }
        const newCount = messageCount + 2;
        onMessageCountChange(newCount);
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            ...next[next.length - 1],
            id: botMsgId,
            sources: pendingSources ?? undefined,
          };
          return next;
        });
        setIsStreaming(false);
      },
      onError: (msg) => {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", content: msg };
          return next;
        });
        setIsStreaming(false);
      },
    });
  }, [sessionId, input, isStreaming, atLimit, topic, messageCount, onFirstMessage, onMessageCountChange]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSend();
    }
  }

  function handleRatingChange(messageId: number, rating: "up" | "down") {
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, my_rating: rating } : m))
    );
  }

  return (
    <main className="flex-1 flex flex-col overflow-hidden">
      {atLimit && (
        <div className="bg-red-100 border-b border-red-300 text-red-700 px-4 py-2.5 text-sm font-medium flex items-center justify-between">
          <span>已達訊息上限（每個對話最多 50 輪問答），請開新對話繼續提問。</span>
        </div>
      )}

      <div ref={boxRef} className="flex-1 overflow-y-auto p-6 flex flex-col gap-2">
        {messages.length === 0 && <WelcomeMessage />}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} onRatingChange={handleRatingChange} />
        ))}
        {isStreaming && messages[messages.length - 1]?.content === "" && (
          <TypingIndicator />
        )}
      </div>

      <div className="border-t border-gray-200 bg-white px-6 py-4 flex-shrink-0">
        <div className="flex gap-2 max-w-4xl mx-auto mb-2">
          <select
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="border border-gray-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white text-gray-600 flex-shrink-0 min-w-[130px]"
          >
            {TOPICS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            placeholder="請輸入您的職涯問題…"
            className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
          />
          <button
            onClick={handleSend}
            disabled={isStreaming || atLimit || !input.trim()}
            className="px-5 py-2 bg-blue-700 hover:bg-blue-800 text-white rounded-xl text-sm font-medium transition disabled:opacity-50 flex-shrink-0"
          >
            發送
          </button>
        </div>
        <div className="flex justify-between items-center max-w-4xl mx-auto">
          <p className="text-xs text-gray-400">Ctrl+Enter 快速發送 · 基於 @hrjasmin 職涯顧問影片</p>
          {rounds > 0 && (
            <span className="text-xs text-gray-400">
              第 {rounds} / {MAX_ROUNDS} 輪問答
            </span>
          )}
        </div>
      </div>
    </main>
  );
}

function WelcomeMessage() {
  return (
    <div className="max-w-[80%] px-4 py-3 rounded-2xl bg-gray-100 shadow-sm self-start">
      <p className="text-gray-800 font-medium text-sm">歡迎使用職涯 AI 🎯</p>
      <p className="text-gray-600 text-sm mt-1">
        我根據職涯顧問 @hrjasmin 的影片內容，為您解答履歷、面試、薪資談判、職涯規劃等問題。
      </p>
    </div>
  );
}
