"use client";

import { useEffect, useRef } from "react";
import type { Message, Source } from "@/types";
import { submitFeedback } from "@/lib/api";

interface Props {
  message: Message;
  onRatingChange?: (messageId: number, rating: "up" | "down") => void;
}

export default function MessageBubble({ message, onRatingChange }: Props) {
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (message.role === "assistant" && contentRef.current && message.content) {
      import("marked").then(({ marked }) => {
        marked.use({ breaks: true });
        if (contentRef.current)
          contentRef.current.innerHTML = marked.parse(
            message.content,
          ) as string;
      });
    }
  }, [message.content, message.role]);

  async function handleFeedback(rating: "up" | "down") {
    if (!message.id) return;
    try {
      await submitFeedback(message.id, rating);
      onRatingChange?.(message.id, rating);
    } catch {
      /* ignore */
    }
  }

  if (message.role === "user") {
    return (
      <div className="msg-bubble msg-user self-end max-w-[80%] px-4 py-3 rounded-2xl bg-blue-600 text-white whitespace-pre-wrap text-sm leading-relaxed shadow-sm">
        {message.content}
      </div>
    );
  }

  return (
    <div className="msg-bubble msg-bot self-start max-w-[80%] px-4 py-3 rounded-2xl bg-white border border-gray-200 shadow-sm">
      <div
        ref={contentRef}
        className="text-sm text-gray-900 leading-relaxed prose prose-sm prose-gray max-w-none prose-p:my-1 prose-headings:text-gray-900 prose-li:text-gray-900"
      />
      {message.sources && message.sources.length > 0 && (
        <SourcesPanel sources={message.sources} />
      )}
      {message.id && (
        <FeedbackBar
          rating={message.my_rating ?? null}
          onFeedback={handleFeedback}
        />
      )}
    </div>
  );
}

function SourcesPanel({ sources }: { sources: Source[] }) {
  const seen = new Set<string>();
  const unique = sources.filter((s) => {
    if (!s.url || seen.has(s.url)) return false;
    seen.add(s.url);
    return true;
  });
  if (unique.length === 0) return null;
  return (
    <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded-lg">
      <p className="text-xs font-semibold text-blue-700 mb-1">📹 影片來源</p>
      {unique.map((s) => (
        <a
          key={s.url}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-xs text-blue-600 hover:underline truncate"
        >
          {s.title || s.url}
          {s.topic && <span className="text-slate-400"> · {s.topic}</span>}
        </a>
      ))}
    </div>
  );
}

function FeedbackBar({
  rating,
  onFeedback,
}: {
  rating: "up" | "down" | null;
  onFeedback: (r: "up" | "down") => void;
}) {
  return (
    <div className="flex gap-2 mt-2 items-center">
      <button
        onClick={() => onFeedback("up")}
        className={`border rounded-md px-2 py-0.5 text-sm transition ${
          rating === "up"
            ? "bg-green-100 border-green-500 text-green-700"
            : "border-gray-300 text-gray-500 hover:bg-gray-50"
        }`}
      >
        👍
      </button>
      <button
        onClick={() => onFeedback("down")}
        className={`border rounded-md px-2 py-0.5 text-sm transition ${
          rating === "down"
            ? "bg-red-100 border-red-500 text-red-600"
            : "border-gray-300 text-gray-500 hover:bg-gray-50"
        }`}
      >
        👎
      </button>
      {rating && (
        <span className="text-xs text-gray-400">
          {rating === "up" ? "感謝回饋！" : "感謝告知"}
        </span>
      )}
    </div>
  );
}
