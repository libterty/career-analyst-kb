"use client";

import { useState } from "react";
import type { Session } from "@/types";
import { renameSession, deleteSession } from "@/lib/api";

interface Props {
  sessions: Session[];
  currentSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
  onDelete: (sessionId: string) => void;
  onRename: (sessionId: string, title: string) => void;
  username: string;
  maxSessions: number;
}

export default function ConversationSidebar({
  sessions,
  currentSessionId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  username,
  maxSessions,
}: Props) {
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  function startRename(session: Session) {
    setRenamingId(session.session_id);
    setRenameValue(session.title || "");
  }

  async function finishRename(sessionId: string) {
    const trimmed = renameValue.trim();
    setRenamingId(null);
    if (trimmed) {
      try {
        await renameSession(sessionId, trimmed);
        onRename(sessionId, trimmed);
      } catch {
        /* ignore */
      }
    }
  }

  async function handleDelete(e: React.MouseEvent, sessionId: string) {
    e.stopPropagation();
    if (!confirm("確定要刪除這個對話嗎？")) return;
    try {
      await deleteSession(sessionId);
      onDelete(sessionId);
    } catch {
      /* ignore */
    }
  }

  const count = sessions.length;
  const atLimit = count >= maxSessions;

  return (
    <aside className="w-64 min-w-64 bg-[#1e1e1e] flex flex-col h-full overflow-hidden hidden md:flex">
      {/* New chat button */}
      <div className="p-3 border-b border-[#333]">
        <button
          onClick={onNew}
          className="w-full px-3 py-2.5 bg-transparent text-[#e0e0e0] border border-dashed border-[#555] rounded-lg text-sm cursor-pointer flex items-center gap-2 hover:bg-[#2a2a2a] hover:border-[#888] transition"
        >
          <span className="text-lg leading-none">+</span> 新對話
        </button>
        {/* Session counter */}
        {count > 0 && (
          <div
            className={`mt-1.5 text-[11px] text-center ${atLimit ? "text-red-400 font-semibold" : "text-[#999]"}`}
          >
            {atLimit
              ? `⚠️ 已達上限 ${count} / ${maxSessions}`
              : `對話：${count} / ${maxSessions}`}
            <div className="h-0.5 bg-[#333] rounded mt-1 overflow-hidden">
              <div
                className="h-full rounded transition-all"
                style={{
                  width: `${Math.min(100, (count / maxSessions) * 100)}%`,
                  background: atLimit
                    ? "#ef4444"
                    : count / maxSessions >= 0.8
                      ? "#f59e0b"
                      : "#3b82f6",
                }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto p-1.5 scrollbar-thin">
        {sessions.length > 0 && (
          <p className="text-[11px] text-[#999] uppercase tracking-wider px-2.5 py-2">
            最近對話
          </p>
        )}
        {sessions.map((s) => (
          <div
            key={s.session_id}
            onClick={() => onSelect(s.session_id)}
            className={`group px-2.5 py-2.5 rounded-lg cursor-pointer transition mb-0.5 flex flex-col gap-0.5 relative ${
              currentSessionId === s.session_id
                ? "bg-[#1a3a5c] border-l-[3px] border-blue-500 pl-[7px]"
                : "hover:bg-[#2d2d2d]"
            }`}
          >
            {renamingId === s.session_id ? (
              <input
                autoFocus
                className="text-[13px] bg-[#333] text-white border border-blue-500 rounded px-1.5 py-0.5 w-[185px] outline-none"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") finishRename(s.session_id);
                  if (e.key === "Escape") setRenamingId(null);
                }}
                onBlur={() => finishRename(s.session_id)}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span
                className={`text-[13px] whitespace-nowrap overflow-hidden text-ellipsis max-w-[185px] ${
                  currentSessionId === s.session_id
                    ? "text-white"
                    : "text-[#d0d0d0]"
                }`}
              >
                {s.title || "新對話"}
              </span>
            )}
            <span className="text-[11px] text-[#999]">
              {formatRelative(s.updated_at || s.created_at)}
            </span>
            {/* Actions */}
            <div className="absolute right-1.5 top-1/2 -translate-y-1/2 hidden group-hover:flex gap-0.5 items-center">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  startRename(s);
                }}
                className="text-[#888] hover:text-blue-400 hover:bg-white/10 rounded p-0.5 text-sm"
                title="重新命名"
              >
                ✏️
              </button>
              <button
                onClick={(e) => handleDelete(e, s.session_id)}
                className="text-[#888] hover:text-red-400 hover:bg-white/10 rounded p-0.5 text-sm"
                title="刪除對話"
              >
                🗑️
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-[#333] text-[12px] text-[#888]">
        {username}
      </div>
    </aside>
  );
}

function formatRelative(dateStr: string | undefined): string {
  if (!dateStr) return "";
  const normalized = /[Z+]/.test(dateStr) ? dateStr : dateStr + "Z";
  const diff = Date.now() - new Date(normalized).getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return "剛剛";
  if (mins < 60) return `${mins}分鐘前`;
  if (hours < 24) return `${hours}小時前`;
  return `${days}天前`;
}
