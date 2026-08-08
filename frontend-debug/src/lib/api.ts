const API_BASE = "/api";

export async function requestCode(email: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/auth/request-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to send code");
  }
  return res.json();
}

export async function refreshToken(): Promise<{ access_token: string }> {
  const res = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Refresh failed");
  }
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" });
}

export async function verifyCode(
  email: string,
  code: string
): Promise<{ access_token: string; user: { id: number; email: string } }> {
  const res = await fetch(`${API_BASE}/auth/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Invalid code");
  }
  return res.json();
}

export interface User {
  id: number;
  email: string;
}

export interface Subject {
  id: number;
  user_id: number;
  name: string;
  created_at: string;
}

export interface Chat {
  id: number;
  subject_id: number;
  user_id: number;
  title: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  chat_id: number;
  role: string;
  content: string;
  image_base64?: string;
  image_media_type?: string;
  metadata_json?: string;
  quote?: string;
  token_count: number;
  created_at: string;
  chat_title?: string;
  subject_name?: string;
  user_email?: string;
}

export interface SqlResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  error?: string;
}

export async function getDebugUsers(): Promise<User[]> {
  const res = await fetch(`${API_BASE}/debug/users`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function getDebugSubjects(userId: number): Promise<Subject[]> {
  const res = await fetch(`${API_BASE}/debug/users/${userId}/subjects`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch subjects");
  return res.json();
}

export async function getDebugChats(subjectId: number): Promise<Chat[]> {
  const res = await fetch(`${API_BASE}/debug/subjects/${subjectId}/chats`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch chats");
  return res.json();
}

export async function getDebugMessages(chatId: number): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/debug/chats/${chatId}/messages`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export interface StructuredLog {
  id: number;
  type: string;
  created_at: string;
  message_id: number | null;
  log: string;
}

export async function getStructuredLogs(messageId?: number): Promise<StructuredLog[]> {
  const params = messageId ? `?message_id=${messageId}` : "";
  const res = await fetch(`${API_BASE}/debug/logs${params}`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch structured logs");
  return res.json();
}

export async function getMessagesWithLogs(): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/debug/traces`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch messages with logs");
  return res.json();
}

export async function executeSql(sql: string, limit?: number | null): Promise<SqlResult> {
  const res = await fetch(`${API_BASE}/debug/sql`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sql, limit: limit ?? null }),
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "SQL execution failed");
  }
  return res.json();
}
