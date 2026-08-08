const API_BASE = "/api";

import type { WhiteboardElement } from "./whiteboard";

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

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface ChatMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  image?: string;
  imageMediaType?: string;
  imageName?: string;
  isDiagram?: boolean;
  quote?: string;
  usage?: TokenUsage;
  tokenCount?: number;
  toolCalls?: ToolCallInfo[];
}

export interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
  id: string;
}

export interface ChatStreamOptions {
  message: string;
  chatId?: number;
  image?: string;
  imageMediaType?: string;
  isDiagram?: boolean;
  messages?: ChatMessage[];
  quote?: string;
  onToken: (content: string) => void;
  onDone: (usage?: TokenUsage) => void;
  onError: (error: string) => void;
  onTitle?: (title: string) => void;
  onToolCall?: (toolCall: ToolCallInfo) => void;
  onDrawing?: (elements: WhiteboardElement[]) => void;
}

export function sendChatStream(options: ChatStreamOptions): AbortController {
  const { message, chatId, image, imageMediaType, isDiagram, messages, quote, onToken, onDone, onError, onTitle, onToolCall, onDrawing } = options;
  const controller = new AbortController();

  fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, chat_id: chatId, image, image_media_type: imageMediaType, is_diagram: isDiagram, quote, messages: messages?.map(m => ({ role: m.role, content: m.content })) }),
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
              else if (data.type === "done") {
                onDone(data.usage);
              }
              else if (data.type === "tool_call" && onToolCall) onToolCall({ name: data.name, args: data.args, id: data.id });
              else if (data.type === "drawing" && onDrawing) onDrawing(data.elements);
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

export interface ChatSummary {
  id: number;
  title: string;
  total_tokens: number;
}

export interface SubjectWithChats extends Subject {
  chats: ChatSummary[];
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
  drawing_json?: string;
  quote?: string;
  token_count: number;
  created_at: string;
  chat_title?: string;
  subject_name?: string;
  user_email?: string;
}

export function getToolCallsFromMetadata(metadata_json?: string): ToolCallInfo[] | undefined {
  if (!metadata_json) return undefined;
  try {
    const metadata = JSON.parse(metadata_json);
    return metadata.tool_calls;
  } catch {
    return undefined;
  }
}

export function getUsageFromMetadata(metadata_json?: string): TokenUsage | undefined {
  if (!metadata_json) return undefined;
  try {
    const metadata = JSON.parse(metadata_json);
    return metadata.usage || metadata.token_usage || undefined;
  } catch {
    return undefined;
  }
}

export function getDrawingFromDrawing(json?: string): { elements: unknown[] } | undefined {
  if (!json) return undefined;
  try {
    const parsed = JSON.parse(json);
    return Array.isArray(parsed) ? { elements: parsed } : undefined;
  } catch {
    return undefined;
  }
}

export async function getSubjects(): Promise<SubjectWithChats[]> {
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

export async function updateSubject(subjectId: number, name: string): Promise<Subject> {
  const res = await fetch(`${API_BASE}/subjects/${subjectId}?name=${encodeURIComponent(name)}`, {
    method: "PATCH",
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to update subject");
  }
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

export async function createChat(subjectId: number, title: string = "New Chat"): Promise<Chat> {
  const params = new URLSearchParams();
  params.set("subject_id", String(subjectId));
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

export async function updateChatTitle(chatId: number, title: string): Promise<Chat> {
  const res = await fetch(`${API_BASE}/chats/${chatId}?title=${encodeURIComponent(title)}`, {
    method: "PATCH",
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to update chat");
  }
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


