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
          </TabsList>
        </div>

        <TabsContent value="browser" className="flex-1 overflow-hidden m-0">
          <BrowserPanel />
        </TabsContent>
        <TabsContent value="sql" className="flex-1 overflow-hidden m-0">
          <SqlPanel />
        </TabsContent>
      </Tabs>
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
        </div>
      </div>

      {/* Right content area */}
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

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "string" && value.length > 200) return value.slice(0, 200) + "...";
  return String(value);
}
