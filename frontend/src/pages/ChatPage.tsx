import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { sendChatStream, getSubjects, getChats, getMessages, type ChatMessage, type TokenUsage, getUsageFromMetadata, getToolCallsFromMetadata, getDrawingFromDrawing, type ChatSummary, type ToolCallInfo } from "@/lib/api";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import ChatHeader from "@/components/ChatHeader";
import ChatMessages from "@/components/ChatMessages";
import ChatInput from "@/components/ChatInput";
import type { Subject } from "@/lib/api";
import { clearPendingDrawing, getPendingDrawing, renderElementsToDataURL, type WhiteboardElement } from "@/lib/whiteboard";

export default function ChatPage() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [chatsBySubject, setChatsBySubject] = useState<Record<number, ChatSummary[]>>({});
  const [loading, setLoading] = useState(true);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentMessageUsage, setCurrentMessageUsage] = useState<TokenUsage | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [quote, setQuote] = useState<string | null>(null);
  const [toolCalls, setToolCalls] = useState<ToolCallInfo[]>([]);
  const toolCallsRef = useRef<ToolCallInfo[]>([]);
  const drawingRef = useRef<WhiteboardElement[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [attachedImage, setAttachedImage] = useState<{ data: string; mediaType: string; isDiagram: boolean } | null>(null);
  const prevChatRef = useRef<number | null>(null);

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
      const formatted: ChatMessage[] = msgs.map((m) => {
        const drawing = getDrawingFromDrawing(m.drawing_json);
        const drawingEls = drawing?.elements as WhiteboardElement[] | undefined;
        const image = m.image_base64 || (drawingEls ? renderElementsToDataURL(drawingEls)?.split(",")[1] : undefined);
        return {
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          image,
          imageMediaType: m.image_base64 ? m.image_media_type : drawingEls ? "image/png" : undefined,
          quote: m.quote,
          usage: getUsageFromMetadata(m.metadata_json),
          tokenCount: m.token_count || undefined,
          toolCalls: getToolCallsFromMetadata(m.metadata_json),
        };
      });
      setMessages(formatted);
    } catch (e) {
      console.error("Failed to load messages", e);
      setMessages([]);
    }
  };

  // Auto-select a chat when arriving via /chat?chatId=N (e.g. from the whiteboard).
  useEffect(() => {
    const param = searchParams.get("chatId");
    if (param && /^\d+$/.test(param) && !selectedChatId) {
      handleSelectChat(Number(param));
    }
    // Run once on mount; selectedChatId starts null.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Adopt the pending whiteboard drawing for the active chat. Kept in memory
  // only; dropped on refresh and discarded when the user switches chats.
  useEffect(() => {
    const pending = getPendingDrawing();
    if (selectedChatId != null && pending && pending.chatId === selectedChatId) {
      setAttachedImage({ data: pending.data, mediaType: pending.mediaType, isDiagram: pending.isDiagram });
    } else if (pending && prevChatRef.current != null && pending.chatId !== selectedChatId) {
      clearPendingDrawing();
      setAttachedImage(null);
    } else {
      setAttachedImage(null);
    }
    prevChatRef.current = selectedChatId;
  }, [selectedChatId]);

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
    setMessages((prev) =>
      prev.map((msg, i) =>
        i === prev.length - 1 && msg.role === "assistant"
          ? { ...msg, content: msg.content + token }
          : msg,
      ),
    );
  }, []);

  const onDone = useCallback((usage: TokenUsage | undefined) => {
    const finalToolCalls = toolCallsRef.current;
    toolCallsRef.current = [];
    if (usage) {
      setCurrentMessageUsage(usage);
      setChatsBySubject((prev) => {
        const sid = Object.keys(prev).find((k) => prev[Number(k)]?.some((c) => c.id === selectedChatId));
        if (!sid) return prev;
        return { ...prev, [Number(sid)]: prev[Number(sid)].map((c) => (c.id === selectedChatId ? { ...c, total_tokens: c.total_tokens + usage.total_tokens } : c)) };
      });
    }
    if (finalToolCalls.length > 0) {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === "assistant") {
          updated[updated.length - 1] = { ...last, toolCalls: finalToolCalls };
        }
        return updated;
      });
    }
    setStreaming(false);
    setToolCalls([]);
  }, [selectedChatId]);

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
    toolCallsRef.current = [];
    setToolCalls([]);
  }, []);

  const onToolCall = useCallback((toolCall: ToolCallInfo) => {
    toolCallsRef.current = [...toolCallsRef.current, toolCall];
    setToolCalls((prev) => [...prev, toolCall]);
  }, []);

  // Accumulate AI `drawing` events and render the diagram as an image on the
  // last assistant message, mirroring how a user image attachment is shown.
  const onDrawing = useCallback((elements: WhiteboardElement[]) => {
    const byId = new Map<string, WhiteboardElement>(drawingRef.current.map((e) => [e.id, e]));
    elements.forEach((el) => byId.set(el.id, el));
    const merged = Array.from(byId.values());
    drawingRef.current = merged;
    const uri = renderElementsToDataURL(merged);
    if (!uri) return;
    const base64 = uri.split(",")[1];
    setMessages((prev) =>
      prev.map((msg, i) =>
        i === prev.length - 1 && msg.role === "assistant"
          ? { ...msg, image: base64, imageMediaType: "image/png" }
          : msg,
      ),
    );
  }, []);

  const sendMessage = useCallback((userMessage: ChatMessage, contextMessages: ChatMessage[], userQuote?: string) => {
    if (streaming || !selectedChatId) return;

    setCurrentMessageUsage(null);
    toolCallsRef.current = [];
    drawingRef.current = [];
    setToolCalls([]);
    setMessages([...contextMessages, { role: "assistant", content: "" } as ChatMessage]);
    setStreaming(true);

    abortRef.current = sendChatStream({
      message: userMessage.content,
      chatId: selectedChatId,
      image: userMessage.image,
      imageMediaType: userMessage.imageMediaType,
      isDiagram: userMessage.isDiagram,
      quote: userQuote,
      messages: contextMessages,
      onToken,
      onDone,
      onError,
      onTitle,
      onToolCall,
      onDrawing,
    });
    setQuote(null);
  }, [streaming, selectedChatId, onToken, onDone, onError, onTitle, onToolCall, onDrawing]);

  const handleSubmitMessage = useCallback(async (text: string, image?: { data: string; mediaType: string; name: string; isDiagram?: boolean }) => {
    if (!text || streaming || !selectedChatId) return;

    const userMessage: ChatMessage = {
      role: "user",
      content: text,
      image: image?.data,
      imageMediaType: image?.mediaType,
      imageName: image?.name,
      isDiagram: image?.isDiagram,
      quote: quote ?? undefined,
    };
    sendMessage(userMessage, [...messages, userMessage], quote ?? undefined);
  }, [streaming, selectedChatId, messages, sendMessage, quote]);

  const handleRetry = useCallback((index: number) => {
    if (streaming || !selectedChatId) return;

    let targetIndex = index;
    while (targetIndex >= 0 && messages[targetIndex].role !== "user") {
      targetIndex--;
    }
    if (targetIndex < 0) return;

    const userMessage = { ...messages[targetIndex] };
    sendMessage(userMessage, [...messages.slice(0, targetIndex), userMessage]);
  }, [streaming, selectedChatId, messages, sendMessage]);

  const handleClearChat = useCallback(() => {
    clearPendingDrawing();
    setAttachedImage(null);
    setSelectedChatId(null);
    setMessages([]);
  }, []);

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
    <SidebarProvider>
      <AppSidebar
        subjects={subjects}
        chatsBySubject={chatsBySubject}
        loading={loading}
        selectedChatId={selectedChatId}
        onSelectChat={handleSelectChat}
        onChatCreated={handleChatCreated}
        onSubjectCreated={handleSubjectCreated}
        onClearChat={handleClearChat}
        onSubjectUpdated={(updated) => setSubjects((prev) => prev.map((s) => s.id === updated.id ? updated : s))}
        onChatUpdated={(chatId, subjectId, title) => setChatsBySubject((prev) => ({ ...prev, [subjectId]: prev[subjectId].map((c) => c.id === chatId ? { ...c, title } : c) }))}
      />
      <SidebarInset className="flex flex-col bg-background h-svh overflow-hidden">
        <ChatHeader email={user?.email} onLogout={handleLogout} />
        <div className="flex flex-1 overflow-hidden">
          <ChatMessages selectedChatId={selectedChatId} messages={messages} streaming={streaming} toolCalls={toolCalls} onRetry={handleRetry} />
        </div>
        <ChatInput
          key={selectedChatId}
          onSubmit={handleSubmitMessage}
          streaming={streaming}
          selectedChatId={selectedChatId}
          selectedChatTokens={selectedChat?.total_tokens ?? 0}
          chatTokenLimit={chatTokenLimit}
          chatTokenPercent={chatTokenPercent}
          quote={quote ?? undefined}
          onClearQuote={() => setQuote(null)}
          onQuote={(text) => setQuote(text)}
          attachedImage={attachedImage}
          onAttachedImageConsumed={() => setAttachedImage(null)}
        />
      </SidebarInset>
    </SidebarProvider>
  );
}
