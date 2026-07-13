"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { getToken, getUsername, clearAuth } from "@/lib/auth";
import { getMe, getSessions, createSession, getSession } from "@/lib/api";
import type { Session, Message } from "@/types";
import ConversationSidebar from "@/components/chat/ConversationSidebar";
import ChatBox from "@/components/chat/ChatBox";

export default function HomePage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [username, setUsernameState] = useState("");
  const [maxSessions, setMaxSessions] = useState(20);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }

    async function init() {
      try {
        const me = await getMe();
        setUsernameState(me.username || getUsername() || "");
        setMaxSessions(me.max_sessions ?? 20);
        const list = await getSessions();
        setSessions(list);
        if (list.length > 0) {
          const s = await getSession(list[0].session_id);
          setCurrentSession(s);
        } else {
          const s = await createSession();
          setSessions([s]);
          setCurrentSession(s);
        }
      } catch {
        clearAuth();
        router.push("/login");
      } finally {
        setReady(true);
      }
    }
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleNewSession = useCallback(async () => {
    try {
      const s = await createSession();
      setSessions((prev) => [s, ...prev]);
      setCurrentSession(s);
    } catch (err: unknown) {
      const e = err as { status?: number; message?: string };
      if (e?.status === 429) alert(e.message || "已達對話數量上限");
    }
  }, []);

  async function handleSelectSession(sessionId: string) {
    try {
      const s = await getSession(sessionId);
      setCurrentSession(s);
    } catch {
      /* ignore */
    }
  }

  function handleDeleteSession(sessionId: string) {
    setSessions((prev) => {
      const remaining = prev.filter((s) => s.session_id !== sessionId);
      if (currentSession?.session_id === sessionId) {
        if (remaining.length > 0) handleSelectSession(remaining[0].session_id);
        else setCurrentSession(null);
      }
      return remaining;
    });
  }

  function handleRenameSession(sessionId: string, title: string) {
    setSessions((prev) =>
      prev.map((s) => (s.session_id === sessionId ? { ...s, title } : s)),
    );
    if (currentSession?.session_id === sessionId)
      setCurrentSession((s) => (s ? { ...s, title } : s));
  }

  function handleFirstMessage(question: string) {
    if (!currentSession) return;
    handleRenameSession(currentSession.session_id, question);
  }

  function handleMessageCountChange(count: number) {
    if (!currentSession) return;
    setCurrentSession((s) => (s ? { ...s, message_count: count } : s));
  }

  function handleLogout() {
    clearAuth();
    router.push("/login");
  }

  if (!ready) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500 text-sm">載入中…</div>
      </div>
    );
  }

  return (
    <div
      className="bg-gray-50 min-h-screen flex flex-col"
      style={{ height: "100vh", overflow: "hidden" }}
    >
      <header className="bg-blue-700 text-white px-6 py-3 flex items-center gap-3 shadow-md flex-shrink-0">
        <div className="text-3xl">💼</div>
        <div>
          <h1 className="text-xl font-bold tracking-wide">
            職涯 AI — Career Analyst KB
          </h1>
          <p className="text-xs opacity-80">
            基於 @hrjasmin 職涯顧問影片的知識庫問答系統
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-xs opacity-80">{username}</span>
          <a
            href="/admin"
            className="text-xs opacity-80 hover:opacity-100 hover:underline"
          >
            管理
          </a>
          <button
            onClick={handleLogout}
            className="px-3 py-1 bg-blue-800 hover:bg-blue-900 rounded text-sm transition"
          >
            登出
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <ConversationSidebar
          sessions={sessions}
          currentSessionId={currentSession?.session_id ?? null}
          onSelect={handleSelectSession}
          onNew={handleNewSession}
          onDelete={handleDeleteSession}
          onRename={handleRenameSession}
          username={username}
          maxSessions={maxSessions}
        />
        {currentSession ? (
          <ChatBox
            sessionId={currentSession.session_id}
            initialMessages={currentSession.messages as Message[]}
            messageCount={currentSession.message_count}
            onFirstMessage={handleFirstMessage}
            onMessageCountChange={handleMessageCountChange}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
            請選擇或建立對話
          </div>
        )}
      </div>
    </div>
  );
}
