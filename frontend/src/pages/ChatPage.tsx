import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { sendChatStream, getSubjects, getChats, getMessages, type ChatMessage } from "@/lib/api";
import { Send, LogOut, Bug, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ModeToggle } from "@/components/mode-toggle";
import Sidebar from "@/components/Sidebar";
import type { Subject, Chat as ChatType, Message as MessageType } from "@/lib/api";

export default function ChatPage() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [chatsBySubject, setChatsBySubject] = useState<Record<number, ChatType[]>>({});
  const [loading, setLoading] = useState(true);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || streaming) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: msg }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    setStreaming(true);

    abortRef.current = sendChatStream(
      msg,
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
      () => setStreaming(false),
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
      }
    );
  };

  const handleLogout = async () => {
    abortRef.current?.abort();
    await logout();
    navigate("/login");
  };

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
                    msg.content
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-border p-4">
        <div className="flex gap-2 max-w-2xl mx-auto">
          <Input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            disabled={streaming || !selectedChatId}
          />
          <Button
            type="submit"
            disabled={streaming || !input.trim()}
            title={streaming ? "Waiting for response..." : !input.trim() ? "Type a message to send" : "Send message"}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </form>
    </div>
  );
}
