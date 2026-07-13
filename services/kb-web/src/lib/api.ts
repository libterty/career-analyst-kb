import { getToken, clearAuth } from "./auth";
import type { Session, User, SystemPrompt, AuthMe, Source } from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL !== undefined
    ? process.env.NEXT_PUBLIC_API_URL
    : "";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers as Record<string, string>),
    },
  });

  if (res.status === 401) {
    clearAuth();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const err = new Error(body.detail ?? "Request failed") as Error & {
      status: number;
    };
    err.status = res.status;
    throw err;
  }

  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(
  username: string,
  password: string,
): Promise<{ access_token: string }> {
  const form = new URLSearchParams({ username, password });
  const res = await fetch(`${API_BASE}/api/auth/token`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error("用戶名或密碼錯誤");
  return res.json();
}

export async function getMe(): Promise<AuthMe> {
  return request<AuthMe>("/api/auth/me");
}

// ── Sessions ──────────────────────────────────────────────────────────────────

export async function getSessions(): Promise<Session[]> {
  return request<Session[]>("/api/sessions");
}

export async function createSession(title?: string): Promise<Session> {
  return request<Session>("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title ?? null }),
  });
}

export async function getSession(sessionId: string): Promise<Session> {
  return request<Session>(`/api/sessions/${sessionId}`);
}

export async function renameSession(
  sessionId: string,
  title: string,
): Promise<void> {
  await request(`/api/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function deleteSession(sessionId: string): Promise<void> {
  await request(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

// ── Chat streaming ────────────────────────────────────────────────────────────

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onMeta: (meta: { message_id?: number }) => void;
  onSources: (sources: Source[]) => void;
  onDone: () => void;
  onError: (msg: string) => void;
}

export async function streamChat(
  question: string,
  sessionId: string,
  topic: string | null,
  callbacks: StreamCallbacks,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ question, session_id: sessionId, topic }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: "發生錯誤" }));
    if (res.status === 429)
      callbacks.onError(`⚠️ ${body.detail ?? "已達訊息上限，請開新對話"}`);
    else callbacks.onError(`⚠️ ${body.detail ?? "發生錯誤"}`);
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const token = line.slice(6);

      if (token === "[DONE]") {
        callbacks.onDone();
        return;
      }

      if (token.startsWith("[META:")) {
        try {
          callbacks.onMeta(JSON.parse(token.slice(6, -1)));
        } catch {
          /* ignore */
        }
        continue;
      }

      if (token.startsWith("[SOURCES:")) {
        try {
          callbacks.onSources(JSON.parse(token.slice(9, -1)));
        } catch {
          /* ignore */
        }
        continue;
      }

      if (token.startsWith("[ERROR]")) {
        callbacks.onError(token);
        return;
      }

      callbacks.onToken(token);
    }
  }
}

// ── VoltAgent streaming ───────────────────────────────────────────────────────

type FilterState = { inThink: boolean; partial: string };

function filterThinkChunk(chunk: string, state: FilterState): string {
  let visible = "";
  let buf = state.partial + chunk;

  while (buf.length > 0) {
    if (state.inThink) {
      const end = buf.indexOf("</think>");
      if (end !== -1) {
        state.inThink = false;
        buf = buf.slice(end + 8);
      } else {
        state.partial = buf.slice(Math.max(0, buf.length - 7));
        return visible;
      }
    } else {
      const start = buf.indexOf("<think>");
      if (start !== -1) {
        visible += buf.slice(0, start);
        state.inThink = true;
        buf = buf.slice(start + 7);
      } else {
        const keep = Math.max(0, buf.length - 6);
        visible += buf.slice(0, keep);
        state.partial = buf.slice(keep);
        return visible;
      }
    }
  }

  state.partial = "";
  return visible;
}

export async function streamVoltAgent(
  question: string,
  sessionId: string,
  topic: string | null,
  callbacks: StreamCallbacks,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`/agents/CareerLeadAgent/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input: question,
        options: {
          conversationId: sessionId,
          userId: sessionId,
          ...(topic ? { context: { topic } } : {}),
        },
      }),
    });
  } catch {
    callbacks.onError("⚠️ VoltAgent 無法連線，請確認服務已啟動");
    return;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    callbacks.onError(
      `⚠️ VoltAgent 錯誤 (${res.status})${body.error ? `: ${body.error}` : ""}`,
    );
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const thinkState: FilterState = { inThink: false, partial: "" };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;

      let event: { type: string; text?: string; finishReason?: string };
      try {
        event = JSON.parse(raw);
      } catch {
        continue;
      }

      if (event.type === "text-delta" && event.text != null) {
        const visible = filterThinkChunk(event.text, thinkState);
        if (visible) callbacks.onToken(visible);
      } else if (event.type === "finish") {
        callbacks.onDone();
        return;
      }
    }
  }

  callbacks.onDone();
}

// ── Feedback ──────────────────────────────────────────────────────────────────

export async function submitFeedback(
  messageId: number,
  rating: "up" | "down",
): Promise<void> {
  await request("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message_id: messageId, rating }),
  });
}

// ── Documents ─────────────────────────────────────────────────────────────────

export async function getDocuments(): Promise<
  import("@/types").DocumentItem[]
> {
  return request<import("@/types").DocumentItem[]>("/api/documents/list");
}

export async function uploadDocument(
  file: File,
): Promise<{ filename: string; chunks: number }> {
  const form = new FormData();
  form.append("file", file);
  return request("/api/documents/upload", { method: "POST", body: form });
}

export async function deleteDocument(docId: number): Promise<void> {
  await request(`/api/documents/${docId}`, { method: "DELETE" });
}

// ── Admin: Users ──────────────────────────────────────────────────────────────

export async function getUsers(): Promise<User[]> {
  return request<User[]>("/api/admin/users");
}

export async function createUser(data: {
  username: string;
  password: string;
  role: "admin" | "user";
}): Promise<User> {
  return request<User>("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateUserPassword(
  userId: number,
  password: string,
): Promise<void> {
  await request(`/api/admin/users/${userId}/password`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
}

export async function updateUserMaxSessions(
  userId: number,
  maxSessions: number,
): Promise<void> {
  await request(`/api/admin/users/${userId}/max-sessions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_sessions: maxSessions }),
  });
}

export async function deleteUser(userId: number): Promise<void> {
  await request(`/api/admin/users/${userId}`, { method: "DELETE" });
}

// ── Admin: System Prompts ─────────────────────────────────────────────────────

export async function getSystemPrompts(): Promise<SystemPrompt[]> {
  return request<SystemPrompt[]>("/api/admin/system-prompts");
}

export async function activatePrompt(promptId: number): Promise<void> {
  await request(`/api/admin/system-prompts/${promptId}/activate`, {
    method: "PATCH",
  });
}

export async function createPrompt(data: {
  name: string;
  content: string;
}): Promise<SystemPrompt> {
  return request<SystemPrompt>("/api/admin/system-prompts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updatePrompt(
  promptId: number,
  data: { name?: string; content?: string },
): Promise<SystemPrompt> {
  return request<SystemPrompt>(`/api/admin/system-prompts/${promptId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deletePrompt(promptId: number): Promise<void> {
  await request(`/api/admin/system-prompts/${promptId}`, { method: "DELETE" });
}

// ── Hill Climbing ─────────────────────────────────────────────────────────────

export interface HillClimbingDiff {
  id: string;
  risk: string;
  target_category: string;
  rationale: string;
  original_excerpt: string;
  replacement: string;
}

export interface ApplyLogEntry {
  timestamp: string;
  applied: string[];
  missed: string[];
  backup: string;
  outcome: string;
  applied_by?: string;
}

export interface HillClimbingPending {
  generated_at: string | null;
  overall_accuracy: number | null;
  summary: string;
  diffs: HillClimbingDiff[];
  apply_log: ApplyLogEntry[];
}

export async function getHillClimbingPending(): Promise<HillClimbingPending> {
  return request<HillClimbingPending>("/api/admin/hill-climbing/pending");
}

export async function applyHillClimbingDiffs(
  approvedIds: string[],
): Promise<{
  applied: string[];
  missed: string[];
  archived: string | null;
  note: string;
}> {
  return request("/api/admin/hill-climbing/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved_ids: approvedIds }),
  });
}

export async function archiveHillClimbingBatch(): Promise<{
  archived: string;
  note: string;
}> {
  return request("/api/admin/hill-climbing/archive", { method: "POST" });
}
