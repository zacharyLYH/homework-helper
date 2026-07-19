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

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  image?: string;
  imageMediaType?: string;
  imageName?: string;
}

export function sendChatStream(
  message: string,
  onToken: (content: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
  chatId?: number,
  onTitle?: (title: string) => void,
  image?: string,
  imageMediaType?: string,
  messages?: ChatMessage[]
): AbortController {
  const controller = new AbortController();

  fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, chat_id: chatId, image, image_media_type: imageMediaType, messages: messages?.map(m => ({ role: m.role, content: m.content })) }),
    credentials: "include",
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json();
        onError(err.detail || "Chat failed");
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) {
        onError("No response body");
        return;
      }
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulatedTitle = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === "token") onToken(data.content);
              else if (data.type === "title") {
                accumulatedTitle += data.content;
                if (onTitle) onTitle(accumulatedTitle);
              }
              else if (data.type === "done") onDone();
              else if (data.type === "error") onError(data.content);
            } catch {}
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onError(err.message || "Network error");
      }
    });

  return controller;
}

export interface DebugUser {
  id: number;
  email: string;
  created_at: string;
}

export interface DebugSubject {
  id: number;
  user_id: number;
  name: string;
  created_at: string;
}

export interface DebugChat {
  id: number;
  subject_id: number;
  user_id: number;
  mode: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface DebugMessage {
  id: number;
  chat_id: number;
  role: string;
  content: string;
  created_at: string;
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
  mode: string;
  title: string;
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
  created_at: string;
}

export async function getSubjects(): Promise<Subject[]> {
  const res = await fetch(`${API_BASE}/subjects`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch subjects");
  return res.json();
}

export async function createSubject(name: string): Promise<Subject> {
  const res = await fetch(`${API_BASE}/subjects?name=${encodeURIComponent(name)}`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to create subject");
  return res.json();
}

export async function deleteSubject(subjectId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/subjects/${subjectId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to delete subject");
}

export async function getChats(subjectId: number): Promise<Chat[]> {
  const res = await fetch(`${API_BASE}/chats?subject_id=${subjectId}`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch chats");
  return res.json();
}

export async function createChat(subjectId: number, mode: string = "guide", title: string = "New Chat"): Promise<Chat> {
  const params = new URLSearchParams();
  params.set("subject_id", String(subjectId));
  params.set("mode", mode);
  params.set("title", title);
  const res = await fetch(`${API_BASE}/chats?${params.toString()}`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to create chat");
  return res.json();
}

export async function getChat(chatId: number): Promise<Chat> {
  const res = await fetch(`${API_BASE}/chats/${chatId}`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch chat");
  return res.json();
}

export async function deleteChat(chatId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/chats/${chatId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to delete chat");
}

export async function getMessages(chatId: number): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/chats/${chatId}/messages`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export interface SqlResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  error?: string;
}

export async function getDebugUsers(): Promise<DebugUser[]> {
  const res = await fetch(`${API_BASE}/debug/users`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function getDebugSubjects(userId: number): Promise<DebugSubject[]> {
  const res = await fetch(`${API_BASE}/debug/users/${userId}/subjects`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch subjects");
  return res.json();
}

export async function getDebugChats(subjectId: number): Promise<DebugChat[]> {
  const res = await fetch(`${API_BASE}/debug/subjects/${subjectId}/chats`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch chats");
  return res.json();
}

export async function getDebugMessages(chatId: number): Promise<DebugMessage[]> {
  const res = await fetch(`${API_BASE}/debug/chats/${chatId}/messages`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export async function executeSql(sql: string): Promise<SqlResult> {
  const res = await fetch(`${API_BASE}/debug/sql`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sql }),
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "SQL execution failed");
  }
  return res.json();
}
