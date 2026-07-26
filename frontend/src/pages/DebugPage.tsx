import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  getDebugUsers,
  getDebugSubjects,
  getDebugChats,
  getDebugMessages,
  getMessagesWithLogs,
  getStructuredLogs,
  executeSql,
  type User,
  type Subject,
  type Chat,
  type Message,
  type SqlResult,
  type StructuredLog,
} from "@/lib/api";
import { ArrowLeft, Play, ChevronRight, Database, Users, BookOpen, MessageSquare, RefreshCw, Activity, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { ModeToggle } from "@/components/mode-toggle";


export default function DebugPage() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col h-screen bg-background">
      <header className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate("/chat")} title="Back to chat">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-lg font-semibold text-foreground">Debug Console</h1>
        </div>
        <div className="flex items-center gap-2">
          <ModeToggle />
        </div>
      </header>

      <Tabs defaultValue="browser" className="flex-1 flex flex-col overflow-hidden">
        <div className="px-4 pt-2 border-b border-border">
          <TabsList>
            <TabsTrigger value="browser">
              <Users className="h-3.5 w-3.5" />
              Browser
            </TabsTrigger>
            <TabsTrigger value="sql">
              <Database className="h-3.5 w-3.5" />
              SQL
            </TabsTrigger>
            <TabsTrigger value="trace">
              <Activity className="h-3.5 w-3.5" />
              Trace
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="browser" className="flex-1 overflow-hidden m-0">
          <BrowserPanel />
        </TabsContent>
        <TabsContent value="sql" className="flex-1 overflow-hidden m-0">
          <SqlPanel />
        </TabsContent>
        <TabsContent value="trace" className="flex-1 overflow-hidden m-0">
          <TracePanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function DebugTreeView({
  users, selectedUser, selectUser,
  subjects, selectedSubject, selectSubject,
  chats, selectedChat, selectChat,
  loading,
}: {
  users: User[];
  selectedUser: User | null;
  selectUser: (u: User) => void;
  subjects: Subject[];
  selectedSubject: Subject | null;
  selectSubject: (s: Subject) => void;
  chats: Chat[];
  selectedChat: Chat | null;
  selectChat: (c: Chat) => void;
  loading: boolean;
}) {
  if (users.length === 0) return null;
  return (
    <>
      {users.map((user) => (
        <div key={user.id}>
          <Button
            variant="ghost"
            className={`w-full justify-start rounded-none px-3 py-2 h-auto ${
              selectedUser?.id === user.id ? "bg-accent text-accent-foreground" : ""
            }`}
            onClick={() => selectUser(user)}
          >
            <Users className="h-3.5 w-3.5 text-muted-foreground shrink-0 mr-2" />
            <span className="truncate font-medium">{user.email}</span>
            <ChevronRight className="h-3 w-3 text-muted-foreground ml-auto shrink-0" />
          </Button>

          {selectedUser?.id === user.id && subjects.length > 0 && (
            <div className="border-l-2 border-border ml-5">
              {subjects.map((subject) => (
                <div key={subject.id}>
                  <Button
                    variant="ghost"
                    size="sm"
                    className={`w-full justify-start rounded-none pl-4 pr-3 py-2 h-auto ${
                      selectedSubject?.id === subject.id ? "bg-accent text-accent-foreground" : ""
                    }`}
                    onClick={() => selectSubject(subject)}
                  >
                    <BookOpen className="h-3.5 w-3.5 text-muted-foreground shrink-0 mr-2" />
                    <span className="truncate">{subject.name}</span>
                    <ChevronRight className="h-3 w-3 text-muted-foreground ml-auto shrink-0" />
                  </Button>

                  {selectedSubject?.id === subject.id && chats.length > 0 && (
                    <div className="border-l-2 border-border ml-5">
                      {chats.map((chat) => (
                        <Button
                          key={chat.id}
                          variant="ghost"
                          size="sm"
                          className={`w-full justify-start rounded-none pl-4 pr-3 py-1.5 h-auto ${
                            selectedChat?.id === chat.id ? "bg-accent text-accent-foreground" : ""
                          }`}
                          onClick={() => selectChat(chat)}
                        >
                          <MessageSquare className="h-3 w-3 text-muted-foreground shrink-0 mr-2" />
                          <span className="truncate">{chat.title}</span>
                          <span className="ml-auto text-[10px] text-muted-foreground shrink-0">
                            {chat.mode}
                          </span>
                        </Button>
                      ))}
                    </div>
                  )}

                  {selectedSubject?.id === subject.id && chats.length === 0 && !loading && (
                    <div className="pl-4 py-2 text-xs text-muted-foreground">No chats</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {selectedUser?.id === user.id && subjects.length === 0 && !loading && (
            <div className="ml-5 pl-4 py-2 text-xs text-muted-foreground">No subjects</div>
          )}
        </div>
      ))}
    </>
  );
}

function BrowserPanel() {
  const [users, setUsers] = useState<User[]>([]);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [selectedSubject, setSelectedSubject] = useState<Subject | null>(null);
  const [chats, setChats] = useState<Chat[]>([]);
  const [selectedChat, setSelectedChat] = useState<Chat | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
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

  const selectUser = useCallback(async (user: User) => {
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

  const selectSubject = useCallback(async (subject: Subject) => {
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

  const selectChat = useCallback(async (chat: Chat) => {
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
      <div className="w-72 border-r border-border bg-background flex flex-col shrink-0">
        <div className="p-3 border-b border-border flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Data Browser</span>
          <Button
            variant="ghost"
            size="icon"
            onClick={loadUsers}
            disabled={loading}
            title="Load users"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {users.length === 0 && !loading && (
            <div className="p-4 text-center text-sm text-muted-foreground">
              Click <RefreshCw className="inline h-3 w-3" /> to load users
            </div>
          )}
          <DebugTreeView
            users={users}
            selectedUser={selectedUser}
            selectUser={selectUser}
            subjects={subjects}
            selectedSubject={selectedSubject}
            selectSubject={selectSubject}
            chats={chats}
            selectedChat={selectedChat}
            selectChat={selectChat}
            loading={loading}
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="m-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive">
            {error}
          </div>
        )}

        {!hasSelection && !error && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Select a user to browse data
          </div>
        )}

        {selectedChat && messages.length > 0 && (
          <div className="p-4">
            <div className="mb-4 flex items-center gap-2 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{selectedUser?.email}</span>
              <ChevronRight className="h-3 w-3" />
              <span>{selectedSubject?.name}</span>
              <ChevronRight className="h-3 w-3" />
              <span className="font-medium text-foreground">{selectedChat.title}</span>
              <Badge variant="secondary">{messages.length} messages</Badge>
            </div>
            <div className="space-y-2">
              {messages.map((m) => (
                <Card key={m.id} className="p-3 shadow-none">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                    <Badge variant={m.role === "user" ? "default" : "secondary"}>
                      {m.role}
                    </Badge>
                    <span>ID {m.id}</span>
                    <span>{m.created_at}</span>
                    {m.chat_id > 0 && <span className="text-muted-foreground">chat_id={m.chat_id}</span>}
                  </div>
                  <p className="text-sm text-foreground whitespace-pre-wrap mt-1">{m.content}</p>
                </Card>
              ))}
            </div>
          </div>
        )}

        {selectedChat && messages.length === 0 && !loading && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            No messages in this chat
          </div>
        )}

        {selectedUser && !selectedSubject && !loading && (
          <div className="p-4">
            <h2 className="text-sm font-medium text-foreground mb-2">
              Subjects for {selectedUser.email}
            </h2>
            {subjects.length === 0 ? (
              <p className="text-sm text-muted-foreground">No subjects</p>
            ) : (
              <div className="grid gap-2">
                {subjects.map((s) => (
                  <Card
                    key={s.id}
                    className="p-3 shadow-none cursor-pointer hover:bg-accent transition-colors"
                    onClick={() => selectSubject(s)}
                  >
                    <div className="flex items-center gap-2">
                      <BookOpen className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium text-foreground">{s.name}</span>
                      <Badge variant="outline" className="ml-auto">ID {s.id}</Badge>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        {selectedSubject && !selectedChat && !loading && (
          <div className="p-4">
            <h2 className="text-sm font-medium text-foreground mb-2">
              Chats in {selectedSubject.name}
            </h2>
            {chats.length === 0 ? (
              <p className="text-sm text-muted-foreground">No chats</p>
            ) : (
              <div className="grid gap-2">
                {chats.map((c) => (
                  <Card
                    key={c.id}
                    className="p-3 shadow-none cursor-pointer hover:bg-accent transition-colors"
                    onClick={() => selectChat(c)}
                  >
                    <div className="flex items-center gap-2">
                      <MessageSquare className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm font-medium text-foreground">{c.title}</span>
                      <Badge
                        variant="outline"
                        className={`ml-auto ${
                          c.mode === "guide" ? "border-amber-500/50 text-amber-500" : "border-violet-500/50 text-violet-500"
                        }`}
                      >
                        {c.mode}
                      </Badge>
                    </div>
                    <div className="text-xs text-muted-foreground mt-1">
                      ID {c.id} · created {c.created_at}
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-sm text-muted-foreground flex items-center gap-2">
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
      <div className="border-b border-border bg-background p-4 shrink-0">
        <div className="flex items-center gap-2 mb-2">
          <Database className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">SQL Editor</span>
          <span className="text-xs text-muted-foreground">— Ctrl+Enter to execute</span>
        </div>
        <div className="flex gap-2">
          <Textarea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={4}
            spellCheck={false}
            className="flex-1 font-mono text-sm resize-none"
            placeholder="SELECT * FROM users"
          />
          <Button
            onClick={handleExecute}
            disabled={loading || !sql.trim()}
            className="self-start"
          >
            <Play className="h-4 w-4" />
            {loading ? "Running..." : "Run"}
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4">
        {error && (
          <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive font-mono">
            {error}
          </div>
        )}

        {result && (
          <div>
            <div className="text-xs text-muted-foreground mb-2">
              <Badge variant="secondary">
                {result.row_count} row{result.row_count !== 1 ? "s" : ""} returned
              </Badge>
            </div>
            {result.columns.length > 0 ? (
              <Card className="shadow-none overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {result.columns.map((col) => (
                        <TableHead key={col}>{col}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.rows.map((row, i) => (
                      <TableRow key={i}>
                        {result.columns.map((col) => (
                          <TableCell key={col} className="font-mono text-xs">
                            {formatCell(row[col])}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            ) : (
              <div className="text-sm text-muted-foreground">Query executed successfully (no results)</div>
            )}
          </div>
        )}

        {!result && !error && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Write a query and press Run or Ctrl+Enter
          </div>
        )}
      </div>
    </div>
  );
}

// --- Trace Panel ---

const TYPE_META: Record<string, { component: string; color: string }> = {
  chat_request:     { component: "Chat", color: "#3b82f6" },
  chat_response:    { component: "Chat", color: "#3b82f6" },
  agent_start:      { component: "Agent", color: "#22c55e" },
  agent_tool_call:  { component: "Agent", color: "#22c55e" },
  tool_input:       { component: "Tool", color: "#f59e0b" },
  tool_output:      { component: "Tool", color: "#f59e0b" },
  tool_result:      { component: "Tool", color: "#f59e0b" },
  tool_artifact:    { component: "Tool", color: "#f59e0b" },
  llm_request:      { component: "LLM", color: "#a855f7" },
  llm_stream_start: { component: "LLM", color: "#a855f7" },
  llm_stream_end:   { component: "LLM", color: "#a855f7" },
  llm_tool_call:    { component: "LLM", color: "#a855f7" },
  llm_quota_error:  { component: "LLM", color: "#ef4444" },
  llm_all_models_exhausted: { component: "LLM", color: "#ef4444" },
  graph_route:      { component: "Graph", color: "#64748b" },
  stream_error:     { component: "System", color: "#ef4444" },
};

function getSpanMeta(type: string) {
  return TYPE_META[type] || { component: "Other", color: "#94a3b8" };
}

function formatLogSummary(raw: string): string {
  try {
    const parsed = JSON.parse(raw);
    return Object.entries(parsed)
      .map(([k, v]) => {
        const val = typeof v === "object" ? JSON.stringify(v) : String(v);
        return val.length > 60 ? val.slice(0, 60) + "..." : val;
      })
      .join(" ");
  } catch {
    return raw.slice(0, 120);
  }
}

function formatLogPretty(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

type WaterfallRow = {
  log: StructuredLog;
  meta: { component: string; color: string };
  offsetMs: number;
  summary: string;
};

function WaterfallTrace({ logs, message }: { logs: StructuredLog[]; message: Message }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const rows: WaterfallRow[] = useMemo(() => {
    if (logs.length === 0) return [];
    const t0 = new Date(logs[0].created_at).getTime();
    return logs.map((l) => ({
      log: l,
      meta: getSpanMeta(l.type),
      offsetMs: new Date(l.created_at).getTime() - t0,
      summary: formatLogSummary(l.log),
    }));
  }, [logs]);

  const maxMs = rows.length > 0 ? rows[rows.length - 1].offsetMs || 1 : 1;

  return (
    <div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4 pb-2 border-b border-border">
        <Badge variant={message.role === "user" ? "default" : "secondary"}>
          {message.role}
        </Badge>
        <span className="font-medium text-foreground">Message #{message.id}</span>
        <span>{message.created_at}</span>
        <span className="truncate ml-auto text-foreground/60">{message.content.slice(0, 100)}</span>
      </div>

      {/* Timeline header */}
      <div className="flex text-[10px] text-muted-foreground mb-1 px-2">
        <div className="w-[140px] shrink-0">Span</div>
        <div className="flex-1 relative h-4">
          <div className="absolute inset-0 flex">
            {[0, 25, 50, 75, 100].map((pct) => (
              <div key={pct} className="flex-1 border-l border-border/30 first:border-l-0 text-center">
                {pct > 0 && <span className="block pt-0.5">+{Math.round(maxMs * pct / 100)}ms</span>}
              </div>
            ))}
          </div>
        </div>
        <div className="w-[40px] shrink-0 text-right">Time</div>
      </div>

      {/* Rows */}
      <div className="space-y-0.5">
        {rows.map((row, i) => {
          const leftPct = maxMs > 0 ? (row.offsetMs / maxMs) * 100 : 0;
          const barWidth = Math.max(0.5, (maxMs > 0 ? ((i < rows.length - 1 ? rows[i + 1].offsetMs : maxMs) - row.offsetMs) / maxMs * 100 : 0.5));
          const isExpanded = expandedIdx === i;

          return (
            <div key={i}>
              <div
                className="flex items-center gap-0 px-2 py-1.5 rounded hover:bg-accent/40 cursor-pointer transition-colors text-xs"
                onClick={() => setExpandedIdx(isExpanded ? null : i)}
              >
                {/* Component + type label */}
                <div className="w-[140px] shrink-0 flex items-center gap-1.5">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: row.meta.color }}
                  />
                  <span className="font-medium text-foreground/80 truncate">{row.meta.component}</span>
                  <span className="text-muted-foreground truncate">{row.log.type.replace(/^(chat|agent|tool|llm|graph)_/, "")}</span>
                </div>

                {/* Timeline bar */}
                <div className="flex-1 relative h-5">
                  <div className="absolute inset-0 flex items-center">
                    <div
                      className="h-[6px] rounded-sm opacity-60"
                      style={{
                        backgroundColor: row.meta.color,
                        marginLeft: `${leftPct}%`,
                        width: `${Math.max(barWidth, 0.5)}%`,
                        minWidth: "4px",
                      }}
                    />
                    <span
                      className="w-[10px] h-[10px] rounded-full border-2 border-background shrink-0 -ml-[5px]"
                      style={{ backgroundColor: row.meta.color }}
                    />
                  </div>
                </div>

                {/* Time + expand indicator */}
                <div className="w-[40px] shrink-0 text-right text-muted-foreground">
                  +{row.offsetMs}ms
                </div>
                {isExpanded ? (
                  <ChevronUp className="h-3 w-3 text-muted-foreground shrink-0 ml-1" />
                ) : (
                  <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0 ml-1" />
                )}
              </div>

              {/* Expandable row: summary + raw JSON */}
              {isExpanded && (
                <div className="ml-[148px] mb-1 p-2 rounded bg-muted/30 border border-border/50 text-xs font-mono">
                  <div className="text-muted-foreground mb-1 truncate">{row.summary}</div>
                  <pre className="text-[10px] text-muted-foreground/70 whitespace-pre-wrap max-h-48 overflow-auto">
                    {formatLogPretty(row.log.log)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TracePanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedMsg, setSelectedMsg] = useState<Message | null>(null);
  const [logs, setLogs] = useState<StructuredLog[]>([]);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [error, setError] = useState("");

  const loadMessages = useCallback(async () => {
    setLoadingMsgs(true);
    setError("");
    try {
      const data = await getMessagesWithLogs();
      setMessages(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingMsgs(false);
    }
  }, []);

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  const selectMessage = useCallback(async (msg: Message) => {
    setSelectedMsg(msg);
    setLoadingLogs(true);
    setError("");
    try {
      const data = await getStructuredLogs(msg.id);
      setLogs(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingLogs(false);
    }
  }, []);

  return (
    <div className="flex h-full">
      {/* Message list sidebar */}
      <div className="w-72 border-r border-border bg-background flex flex-col shrink-0">
        <div className="p-3 border-b border-border flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Messages with traces
          </span>
          <Button variant="ghost" size="icon" onClick={loadMessages} disabled={loadingMsgs} title="Refresh">
            <RefreshCw className={`h-3.5 w-3.5 ${loadingMsgs ? "animate-spin" : ""}`} />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loadingMsgs && (
            <div className="p-4 text-center text-xs text-muted-foreground">Loading...</div>
          )}
          {!loadingMsgs && messages.length === 0 && (
            <div className="p-4 text-center text-xs text-muted-foreground">
              Send a chat request with structured logging active
            </div>
          )}
          {messages.map((msg) => (
            <button
              key={msg.id}
              onClick={() => selectMessage(msg)}
              className={`w-full text-left px-3 py-2.5 border-b border-border/50 hover:bg-accent/40 transition-colors ${
                selectedMsg?.id === msg.id ? "bg-accent" : ""
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Badge variant={msg.role === "user" ? "default" : "secondary"} className="text-[10px] px-1.5 py-0">
                  {msg.role}
                </Badge>
                <span className="text-xs font-medium text-foreground">#{msg.id}</span>
                <span className="text-[10px] text-muted-foreground ml-auto">{msg.chat_id && `chat=${msg.chat_id}`}</span>
              </div>
              <p className="text-[11px] text-muted-foreground truncate">{msg.content}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Waterfall view */}
      <div className="flex-1 overflow-y-auto bg-background">
        {error && (
          <div className="m-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive">
            {error}
          </div>
        )}

        {!selectedMsg && !error && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Select a message to view its trace
          </div>
        )}

        {loadingLogs && (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin mr-2" />
            Loading trace...
          </div>
        )}

        {selectedMsg && !loadingLogs && (
          <div className="p-4">
            {logs.length === 0 ? (
              <div className="text-sm text-muted-foreground text-center py-12">
                No structured log events for this message
              </div>
            ) : (
              <WaterfallTrace logs={logs} message={selectedMsg} />
            )}
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
