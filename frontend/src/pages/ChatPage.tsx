import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { sendChatStream, getSubjects, getChats, getMessages, type ChatMessage, type TokenUsage, getUsageFromMetadata, type ChatSummary } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import ResizeHandle from "@/components/ResizeHandle";
import ChatHeader from "@/components/ChatHeader";
import ChatMessages from "@/components/ChatMessages";
import ChatInput from "@/components/ChatInput";
import type { Subject } from "@/lib/api";

export default function ChatPage() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [chatsBySubject, setChatsBySubject] = useState<Record<number, ChatSummary[]>>({});
  const [loading, setLoading] = useState(true);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentMessageUsage, setCurrentMessageUsage] = useState<TokenUsage | null>(null);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(256);
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const loadSubjects = useCallback(async () => {
    try {
      const data = await getSubjects();
      setSubjects(data);
      const chatsMap: Record<number, ChatSummary[]> = {};
      for (const s of data) {
        chatsMap[s.id] = s.chats;
      }
      setChatsBySubject(chatsMap);
    } catch (e) {
      console.error("Failed to load subjects", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSubjects();
  }, [loadSubjects]);

  const handleSelectChat = async (chatId: number) => {
    setSelectedChatId(chatId);
    try {
      const msgs = await getMessages(chatId);
      const formatted: ChatMessage[] = msgs.map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.content,
        image: m.image_base64 || undefined,
        imageMediaType: m.image_media_type || undefined,
        usage: getUsageFromMetadata(m.metadata_json),
        tokenCount: m.token_count || undefined,
      }));
      setMessages(formatted);
    } catch (e) {
      console.error("Failed to load messages", e);
      setMessages([]);
    }
  };

  const handleChatCreated = async (chatId: number, subjectId: number) => {
    try {
      const chats = await getChats(subjectId);
      setChatsBySubject((prev) => ({ ...prev, [subjectId]: chats }));
      handleSelectChat(chatId);
    } catch (e) {
      console.error("Failed to refresh chats", e);
    }
  };

  const handleSubjectCreated = async (subject: Subject) => {
    setSubjects((prev) => [subject, ...prev]);
    setChatsBySubject((prev) => ({ ...prev, [subject.id]: [] }));
  };

  useEffect(() => {
    if (currentMessageUsage && !streaming) {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant" && !last.usage) {
          last.usage = currentMessageUsage;
          last.tokenCount = currentMessageUsage.total_tokens;
        }
        return updated;
      });
    }
  }, [currentMessageUsage, streaming]);

  const onToken = useCallback((token: string) => {
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (last.role === "assistant") last.content += token;
      return updated;
    });
  }, []);

  const onDone = useCallback((usage: TokenUsage | undefined) => {
    if (usage) setCurrentMessageUsage(usage);
    setStreaming(false);
  }, []);

  const onTitle = useCallback((title: string) => {
    setChatsBySubject((prev) => {
      const sid = Object.keys(prev).find((k) => prev[Number(k)]?.some((c) => c.id === selectedChatId));
      if (!sid) return prev;
      return { ...prev, [Number(sid)]: prev[Number(sid)].map((c) => (c.id === selectedChatId ? { ...c, title } : c)) };
    });
  }, [selectedChatId]);

  const onError = useCallback((err: string) => {
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (last.role === "assistant") last.content = last.content || `Error: ${err}`;
      return updated;
    });
    setStreaming(false);
  }, []);

  const handleSubmitMessage = useCallback(async (text: string, image?: { data: string; mediaType: string; name: string }) => {
    if (!text || streaming || !selectedChatId) return;

    const userMessage: ChatMessage = {
      role: "user",
      content: text,
      image: image?.data,
      imageMediaType: image?.mediaType,
      imageName: image?.name,
    };
    const historyMessages = [...messages, userMessage];
    setCurrentMessageUsage(null);
    setMessages((prev) => [...prev, userMessage]);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    setStreaming(true);

    abortRef.current = sendChatStream({
      message: text,
      chatId: selectedChatId,
      image: image?.data,
      imageMediaType: image?.mediaType,
      messages: historyMessages,
      onToken,
      onDone,
      onError,
      onTitle,
    });
  }, [streaming, selectedChatId, messages, onToken, onDone, onError, onTitle]);

  const handleLogout = async () => {
    abortRef.current?.abort();
    await logout();
    navigate("/login");
  };

  const selectedChat = selectedChatId
    ? Object.values(chatsBySubject).flat().find((c) => c.id === selectedChatId)
    : null;
  const chatTokenLimit = 128000;
  const chatTokenPercent = selectedChat
    ? Math.min((selectedChat.total_tokens / chatTokenLimit) * 100, 100)
    : 0;

  return (
    <div className="flex flex-col h-screen bg-background">
      <ChatHeader email={user?.email} onDebug={() => navigate("/debug")} onLogout={handleLogout} />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          subjects={subjects}
          chatsBySubject={chatsBySubject}
          loading={loading}
          selectedChatId={selectedChatId}
          onSelectChat={handleSelectChat}
          onChatCreated={handleChatCreated}
          onSubjectCreated={handleSubjectCreated}
          style={{ width: sidebarWidth }}
        />
        <ResizeHandle startWidth={sidebarWidth} onResize={setSidebarWidth} />

        <ChatMessages selectedChatId={selectedChatId} messages={messages} streaming={streaming} />
      </div>

      <ChatInput
        onSubmit={handleSubmitMessage}
        streaming={streaming}
        selectedChatId={selectedChatId}
        selectedChatTokens={selectedChat?.total_tokens ?? 0}
        chatTokenLimit={chatTokenLimit}
        chatTokenPercent={chatTokenPercent}
      />
    </div>
  );
}
