import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  getDebugUsers,
  getDebugSubjects,
  getDebugChats,
  getDebugMessages,
  executeSql,
  type DebugUser,
  type DebugSubject,
  type DebugChat,
  type DebugMessage,
  type SqlResult,
} from "@/lib/api";
import { ArrowLeft, Play, ChevronRight, Database, Users, BookOpen, MessageSquare, RefreshCw } from "lucide-react";

type Panel = "browser" | "sql";

export default function DebugPage() {
  const navigate = useNavigate();
  const [panel, setPanel] = useState<Panel>("browser");

  return (
    <div className="flex flex-col h-screen bg-slate-50">
      <header className="flex items-center justify-between px-4 py-3 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/chat")} className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <h1 className="text-lg font-semibold text-slate-900">Debug Console</h1>
        </div>
        <div className="flex gap-1 bg-slate-100 rounded-lg p-0.5">
          <button
            onClick={() => setPanel("browser")}
            className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors ${
              panel === "browser" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <Users className="h-3.5 w-3.5" />
            Browser
          </button>
          <button
            onClick={() => setPanel("sql")}
            className={`px-3 py-1.5 rounded-md text-sm font-medium flex items-center gap-1.5 transition-colors ${
              panel === "sql" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <Database className="h-3.5 w-3.5" />
            SQL
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-hidden">
        {panel === "browser" ? <BrowserPanel /> : <SqlPanel />}
      </div>
    </div>
  );
}

function BrowserPanel() {
  const [users, setUsers] = useState<DebugUser[]>([]);
  const [selectedUser, setSelectedUser] = useState<DebugUser | null>(null);
  const [subjects, setSubjects] = useState<DebugSubject[]>([]);
  const [selectedSubject, setSelectedSubject] = useState<DebugSubject | null>(null);
  const [chats, setChats] = useState<DebugChat[]>([]);
  const [selectedChat, setSelectedChat] = useState<DebugChat | null>(null);
  const [messages, setMessages] = useState<DebugMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const u = await getDebugUsers();
      setUsers(u);
      setSelectedUser(null);
      setSubjects([]);
      setSelectedSubject(null);
      setChats([]);
      setSelectedChat(null);
      setMessages([]);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const selectUser = useCallback(async (user: DebugUser) => {
    setSelectedUser(user);
    setSelectedSubject(null);
    setChats([]);
    setSelectedChat(null);
    setMessages([]);
    setLoading(true);
    setError("");
    try {
      const s = await getDebugSubjects(user.id);
      setSubjects(s);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const selectSubject = useCallback(async (subject: DebugSubject) => {
    setSelectedSubject(subject);
    setSelectedChat(null);
    setMessages([]);
    setLoading(true);
    setError("");
    try {
      const c = await getDebugChats(subject.id);
      setChats(c);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const selectChat = useCallback(async (chat: DebugChat) => {
    setSelectedChat(chat);
    setLoading(true);
    setError("");
    try {
      const m = await getDebugMessages(chat.id);
      setMessages(m);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const hasSelection = selectedUser || selectedSubject || selectedChat;

  return (
    <div className="flex h-full">
      {/* Left sidebar - hierarchy */}
      <div className="w-72 border-r border-slate-200 bg-white flex flex-col shrink-0">
        <div className="p-3 border-b border-slate-100 flex items-center justify-between">
          <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Data Browser</span>
          <button
            onClick={loadUsers}
            disabled={loading}
            className="p-1.5 text-slate-400 hover:text-slate-600 rounded-md hover:bg-slate-100 disabled:opacity-50"
            title="Load users"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {users.length === 0 && !loading && (
            <div className="p-4 text-center text-sm text-slate-400">
              Click <RefreshCw className="inline h-3 w-3" /> to load users
            </div>
          )}

          {users.map((user) => (
            <div key={user.id}>
              <button
                onClick={() => selectUser(user)}
                className={`w-full text-left px-3 py-2 flex items-center gap-2 text-sm border-b border-slate-50 transition-colors ${
                  selectedUser?.id === user.id
                    ? "bg-slate-100 text-slate-900"
                    : "text-slate-700 hover:bg-slate-50"
                }`}
              >
                <Users className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span className="truncate font-medium">{user.email}</span>
                <ChevronRight className="h-3 w-3 text-slate-300 ml-auto shrink-0" />
              </button>

              {selectedUser?.id === user.id && subjects.length > 0 && (
                <div className="bg-slate-50">
                  {subjects.map((subject) => (
                    <div key={subject.id}>
                      <button
                        onClick={() => selectSubject(subject)}
                        className={`w-full text-left pl-8 pr-3 py-2 flex items-center gap-2 text-sm border-b border-slate-100 transition-colors ${
                          selectedSubject?.id === subject.id
                            ? "bg-slate-200/60 text-slate-900"
                            : "text-slate-600 hover:bg-slate-100"
                        }`}
                      >
                        <BookOpen className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                        <span className="truncate">{subject.name}</span>
                        <ChevronRight className="h-3 w-3 text-slate-300 ml-auto shrink-0" />
                      </button>

                      {selectedSubject?.id === subject.id && chats.length > 0 && (
                        <div className="bg-slate-100/50">
                          {chats.map((chat) => (
                            <div key={chat.id}>
                              <button
                                onClick={() => selectChat(chat)}
                                className={`w-full text-left pl-14 pr-3 py-1.5 flex items-center gap-2 text-sm border-b border-slate-100/50 transition-colors ${
                                  selectedChat?.id === chat.id
                                    ? "bg-slate-200/80 text-slate-900"
                                    : "text-slate-500 hover:bg-slate-100"
                                }`}
                              >
                                <MessageSquare className="h-3 w-3 text-slate-400 shrink-0" />
                                <span className="truncate">{chat.title}</span>
                                <span className="ml-auto text-[10px] text-slate-400 shrink-0">
                                  {chat.mode}
                                </span>
                              </button>
                            </div>
                          ))}
                        </div>
                      )}

                      {selectedSubject?.id === subject.id && chats.length === 0 && !loading && (
                        <div className="pl-14 py-2 text-xs text-slate-400">No chats</div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {selectedUser?.id === user.id && subjects.length === 0 && !loading && (
                <div className="pl-8 py-2 text-xs text-slate-400 bg-slate-50">No subjects</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Right content area */}
      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="m-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}

        {!hasSelection && !error && (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            Select a user to browse data
          </div>
        )}

        {selectedChat && messages.length > 0 && (
          <div className="p-4">
            <div className="mb-4 flex items-center gap-2 text-xs text-slate-500">
              <span className="font-medium text-slate-700">{selectedUser?.email}</span>
              <ChevronRight className="h-3 w-3" />
              <span>{selectedSubject?.name}</span>
              <ChevronRight className="h-3 w-3" />
              <span className="font-medium text-slate-700">{selectedChat.title}</span>
              <span className="ml-1 text-slate-400">({messages.length} messages)</span>
            </div>
            <div className="space-y-2">
              {messages.map((m) => (
                <div key={m.id} className="bg-white rounded-lg border border-slate-200 p-3">
                  <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
                    <span className={`font-medium px-1.5 py-0.5 rounded ${
                      m.role === "user" ? "bg-blue-50 text-blue-700" : "bg-emerald-50 text-emerald-700"
                    }`}>
                      {m.role}
                    </span>
                    <span>ID {m.id}</span>
                    <span>{m.created_at}</span>
                    {m.chat_id > 0 && <span className="text-slate-400">chat_id={m.chat_id}</span>}
                  </div>
                  <p className="text-sm text-slate-900 whitespace-pre-wrap mt-1">{m.content}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {selectedChat && messages.length === 0 && !loading && (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            No messages in this chat
          </div>
        )}

        {selectedUser && !selectedSubject && !loading && (
          <div className="p-4">
            <h2 className="text-sm font-medium text-slate-700 mb-2">
              Subjects for {selectedUser.email}
            </h2>
            {subjects.length === 0 ? (
              <p className="text-sm text-slate-400">No subjects</p>
            ) : (
              <div className="grid gap-2">
                {subjects.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => selectSubject(s)}
                    className="text-left bg-white border border-slate-200 rounded-lg p-3 hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <BookOpen className="h-4 w-4 text-slate-400" />
                      <span className="text-sm font-medium text-slate-900">{s.name}</span>
                      <span className="text-xs text-slate-400 ml-auto">ID {s.id}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {selectedSubject && !selectedChat && !loading && (
          <div className="p-4">
            <h2 className="text-sm font-medium text-slate-700 mb-2">
              Chats in {selectedSubject.name}
            </h2>
            {chats.length === 0 ? (
              <p className="text-sm text-slate-400">No chats</p>
            ) : (
              <div className="grid gap-2">
                {chats.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => selectChat(c)}
                    className="text-left bg-white border border-slate-200 rounded-lg p-3 hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <MessageSquare className="h-4 w-4 text-slate-400" />
                      <span className="text-sm font-medium text-slate-900">{c.title}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ml-auto ${
                        c.mode === "guide" ? "bg-amber-50 text-amber-700" : "bg-violet-50 text-violet-700"
                      }`}>
                        {c.mode}
                      </span>
                    </div>
                    <div className="text-xs text-slate-400 mt-1">
                      ID {c.id} · created {c.created_at}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-sm text-slate-400 flex items-center gap-2">
              <RefreshCw className="h-4 w-4 animate-spin" />
              Loading...
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SqlPanel() {
  const [sql, setSql] = useState("SELECT * FROM users");
  const [result, setResult] = useState<SqlResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleExecute = async () => {
    if (!sql.trim() || loading) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const r = await executeSql(sql.trim());
      setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleExecute();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* SQL Editor */}
      <div className="border-b border-slate-200 bg-white p-4 shrink-0">
        <div className="flex items-center gap-2 mb-2">
          <Database className="h-4 w-4 text-slate-400" />
          <span className="text-sm font-medium text-slate-700">SQL Editor</span>
          <span className="text-xs text-slate-400">— Ctrl+Enter to execute</span>
        </div>
        <div className="flex gap-2">
          <textarea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={4}
            spellCheck={false}
            className="flex-1 font-mono text-sm p-3 border border-slate-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent bg-slate-900 text-slate-100 placeholder-slate-500"
            placeholder="SELECT * FROM users"
          />
          <button
            onClick={handleExecute}
            disabled={loading || !sql.trim()}
            className="px-4 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50 flex items-center gap-2 self-start"
          >
            <Play className="h-4 w-4" />
            {loading ? "Running..." : "Run"}
          </button>
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-auto p-4">
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 font-mono">
            {error}
          </div>
        )}

        {result && (
          <div>
            <div className="text-xs text-slate-500 mb-2">
              {result.row_count} row{result.row_count !== 1 ? "s" : ""} returned
            </div>
            {result.columns.length > 0 ? (
              <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr>
                        {result.columns.map((col) => (
                          <th key={col} className="px-3 py-2 text-left font-medium text-slate-600 whitespace-nowrap">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, i) => (
                        <tr key={i} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                          {result.columns.map((col) => (
                            <td key={col} className="px-3 py-2 text-slate-900 font-mono text-xs whitespace-nowrap">
                              {formatCell(row[col])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="text-sm text-slate-500">Query executed successfully (no results)</div>
            )}
          </div>
        )}

        {!result && !error && (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            Write a query and press Run or Ctrl+Enter
          </div>
        )}
      </div>
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "string" && value.length > 200) return value.slice(0, 200) + "...";
  return String(value);
}
