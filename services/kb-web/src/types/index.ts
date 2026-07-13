export interface Message {
  id?: number;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  my_rating?: "up" | "down" | null;
}

export interface Source {
  url: string;
  title: string;
  topic?: string;
  score?: number;
}

export interface Session {
  session_id: string;
  title: string | null;
  created_at: string;
  updated_at?: string;
  message_count: number;
  messages: Message[];
}

export interface User {
  id: number;
  username: string;
  role: "admin" | "user";
  is_active: boolean;
  max_sessions: number;
  created_at: string;
}

export interface SystemPrompt {
  id: number;
  name: string;
  content: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthMe {
  id: number;
  username: string;
  role: "admin" | "user";
  is_active: boolean;
  max_sessions: number;
}

export interface DocumentItem {
  id: number;
  filename: string;
  doc_hash: string;
  pages: number;
  chunk_count: number;
  uploaded_at: string;
}
