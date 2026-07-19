import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { sendChatStream, type ChatMessage } from "@/lib/api";
import { Send, LogOut, Bug, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { user, logout } = useAuth();
  const navigate = useNavigate();

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
    <div className="flex flex-col h-screen bg-white">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
        <h1 className="text-lg font-semibold text-slate-900">Homework Helper</h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-500">{user?.email}</span>
          <button
            onClick={() => navigate("/debug")}
            className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100"
            title="Debug"
          >
            <Bug className="h-4 w-4" />
          </button>
          <button
            onClick={handleLogout}
            className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100"
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            Ask me anything about your homework!
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-xl px-4 py-2 text-sm ${
                msg.role === "user"
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-900"
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
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t border-slate-200 p-4">
        <div className="flex gap-2 max-w-2xl mx-auto">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            disabled={streaming}
            className="flex-1 px-4 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50 flex items-center gap-2"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
