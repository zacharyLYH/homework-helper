import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { sendChatStream, getSubjects, getChats, getMessages, type ChatMessage, type TokenUsage, getUsageFromMetadata } from "@/lib/api";
import { Send, LogOut, Bug, Loader2, Paperclip, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ModeToggle } from "@/components/mode-toggle";
import Sidebar from "@/components/Sidebar";
import { Attachment, AttachmentMedia, AttachmentContent, AttachmentTitle, AttachmentActions, AttachmentAction } from "@/components/ui/attachment";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Subject, Chat as ChatType, Message as MessageType } from "@/lib/api";

export default function ChatPage() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [chatsBySubject, setChatsBySubject] = useState<Record<number, ChatType[]>>({});
  const [loading, setLoading] = useState(true);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [currentMessageUsage, setCurrentMessageUsage] = useState<TokenUsage | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [imageData, setImageData] = useState<string | null>(null);
  const [imageMediaType, setImageMediaType] = useState<string | null>(null);
  const [imageName, setImageName] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const loadSubjects = useCallback(async () => {
    try {
      const data = await getSubjects();
      setSubjects(data);
      const chatsMap: Record<number, ChatType[]> = {};
      await Promise.all(
        data.map(async (s) => {
          try {
            const chats = await getChats(s.id);
            chatsMap[s.id] = chats;
          } catch {
            chatsMap[s.id] = [];
          }
        })
      );
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
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const msg = input.trim();
    if ((!msg && !imageData) || streaming || !selectedChatId) return;

    const sentImage = imageData;
    const sentMediaType = imageMediaType;
    const sentName = imageName;
    const historyMessages = [...messages, { role: "user" as const, content: msg, image: sentImage || undefined, imageMediaType: sentMediaType || undefined, imageName: sentName || undefined }];
    setInput("");
    clearImage();
    setCurrentMessageUsage(null);
    setMessages((prev) => [...prev, { role: "user", content: msg, image: sentImage || undefined, imageMediaType: sentMediaType || undefined, imageName: sentName || undefined }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    setStreaming(true);

    abortRef.current = sendChatStream(
      msg || "What's in this image?",
      (token) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            last.content += token;
          }
          return [...updated];
        });
      },
      (usage) => {
        if (usage) {
          setCurrentMessageUsage(usage);
          if (selectedChatId) {
            setChatsBySubject((prev) => {
              const subjectId = subjects.find((s) => prev[s.id]?.some((c) => c.id === selectedChatId))?.id;
              if (subjectId && prev[subjectId]) {
                return {
                  ...prev,
                  [subjectId]: prev[subjectId].map((c) =>
                    c.id === selectedChatId
                      ? {
                          ...c,
                          input_tokens: c.input_tokens + usage.input_tokens,
                          output_tokens: c.output_tokens + usage.output_tokens,
                          total_tokens: c.total_tokens + usage.total_tokens,
                        }
                      : c
                  ),
                };
              }
              return prev;
            });
          }
        }
        setStreaming(false);
      },
      (err) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            last.content = last.content || `Error: ${err}`;
          }
          return [...updated];
        });
        setStreaming(false);
      },
      selectedChatId,
      (title) => {
        if (selectedChatId) {
          setChatsBySubject((prev) => {
            const subjectId = subjects.find((s) => prev[s.id]?.some((c) => c.id === selectedChatId))?.id;
            if (subjectId && prev[subjectId]) {
              return {
                ...prev,
                [subjectId]: prev[subjectId].map((c) =>
                  c.id === selectedChatId ? { ...c, title } : c
                ),
              };
            }
            return prev;
          });
        }
      },
      sentImage || undefined,
      sentMediaType || undefined,
      historyMessages
    );
  };

  const handleLogout = async () => {
    abortRef.current?.abort();
    await logout();
    navigate("/login");
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !file.type.startsWith("image/")) {
      e.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(",")[1];
      setImageData(base64);
      setImageMediaType(file.type);
      setImageName(file.name);
      fileInputRef.current?.blur();
      textInputRef.current?.focus();
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const clearImage = () => {
    setImageData(null);
    setImageMediaType(null);
    setImageName("");
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
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h1 className="text-lg font-semibold text-foreground">Homework Helper</h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">{user?.email}</span>
          <ModeToggle />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/debug")}
            title="Debug"
          >
            <Bug className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleLogout}
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          subjects={subjects}
          chatsBySubject={chatsBySubject}
          loading={loading}
          selectedChatId={selectedChatId}
          onSelectChat={handleSelectChat}
          onChatCreated={handleChatCreated}
          onSubjectCreated={handleSubjectCreated}
        />

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!selectedChatId ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Select a chat or create a new one to get started.
            </div>
          ) : messages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Ask me anything about your homework!
            </div>
          ) : (
            messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div>
                  <div
                    className={`max-w-[80%] rounded-xl px-4 py-2 text-sm ${
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {msg.role === "assistant" && !msg.content && streaming && i === messages.length - 1 ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : msg.role === "assistant" ? (
                      <div className="prose prose-sm max-w-none">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    ) : (
                      <div>
                        {msg.image && (
                          <img
                            src={`data:${msg.imageMediaType};base64,${msg.image}`}
                            alt={msg.imageName || "Attached image"}
                            className="max-w-full max-h-48 rounded-lg mb-2"
                          />
                        )}
                        {msg.content}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-border p-4">
        <div className="max-w-2xl mx-auto space-y-2">
          {imageData && (
            <div className="flex items-center gap-2">
              <Attachment size="sm">
                <AttachmentMedia variant="image">
                  <img
                    src={`data:${imageMediaType};base64,${imageData}`}
                    alt={imageName}
                    className="h-full w-full object-cover"
                  />
                </AttachmentMedia>
                <AttachmentContent>
                  <AttachmentTitle>{imageName}</AttachmentTitle>
                </AttachmentContent>
                <AttachmentActions>
                  <AttachmentAction
                    aria-label="Remove attachment"
                    onClick={clearImage}
                  >
                    <X className="h-3 w-3" />
                  </AttachmentAction>
                </AttachmentActions>
              </Attachment>
            </div>
          )}
          <div className="flex gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileSelect}
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => fileInputRef.current?.click()}
              disabled={streaming || !selectedChatId}
              title="Attach image"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
            <Input
              ref={textInputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={imageData ? "Add a message (optional)..." : "Type your message..."}
              disabled={streaming || !selectedChatId}
            />
            <Button
              type="submit"
              disabled={streaming || (!input.trim() && !imageData)}
              title={streaming ? "Waiting for response..." : "Send message"}
            >
              <Send className="h-4 w-4" />
            </Button>
            {selectedChat && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button type="button" className="relative flex items-center justify-center w-9 h-9 shrink-0">
                    <svg className="w-6 h-6 -rotate-90" viewBox="0 0 36 36">
                      <circle cx="18" cy="18" r="15" fill="none" stroke="currentColor" strokeWidth="3" className="text-border" />
                      <circle
                        cx="18" cy="18" r="15" fill="none" stroke="currentColor" strokeWidth="3"
                        strokeDasharray={`${chatTokenPercent} 100`}
                        className="text-muted-foreground/40"
                        strokeLinecap="round"
                      />
                    </svg>
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{selectedChat.total_tokens.toLocaleString()} / {chatTokenLimit.toLocaleString()} tokens</p>
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
