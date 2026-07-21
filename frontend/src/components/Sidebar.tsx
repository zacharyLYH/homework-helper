import { useState } from "react";
import { Plus, MessageSquare } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { createSubject, createChat, type Subject } from "@/lib/api";

interface Chat {
  id: number;
  subject_id: number;
  user_id: number;
  mode: string;
  title: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
  updated_at: string;
}

interface SidebarProps {
  subjects: Subject[];
  chatsBySubject: Record<number, Chat[]>;
  loading: boolean;
  selectedChatId: number | null;
  onSelectChat: (chatId: number) => void;
  onChatCreated: (chatId: number, subjectId: number) => void;
  onSubjectCreated: (subject: Subject) => void;
}

export default function Sidebar({
  subjects,
  chatsBySubject,
  loading,
  selectedChatId,
  onSelectChat,
  onChatCreated,
  onSubjectCreated,
}: SidebarProps) {
  const [createType, setCreateType] = useState<"subject" | "chat">("subject");
  const [subjectName, setSubjectName] = useState("");
  const [chatSubjectId, setChatSubjectId] = useState<string>("");
  const [chatMode, setChatMode] = useState("guide");
  const [open, setOpen] = useState(false);

  const handleCreateSubject = async () => {
    const name = subjectName.trim();
    if (!name) return;
    try {
      const subject = await createSubject(name);
      onSubjectCreated(subject);
      setSubjectName("");
      setOpen(false);
    } catch (e) {
      console.error("Failed to create subject", e);
    }
  };

  const handleCreateChat = async () => {
    if (!chatSubjectId) return;
    try {
      const chat = await createChat(Number(chatSubjectId), chatMode, "New Chat");
      onChatCreated(chat.id, chat.subject_id);
      setChatSubjectId("");
      setChatMode("guide");
      setOpen(false);
    } catch (e) {
      console.error("Failed to create chat", e);
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
    if (!newOpen) {
      setCreateType("subject");
      setSubjectName("");
      setChatSubjectId("");
      setChatMode("guide");
    }
  };

  const handleDone = () => {
    if (createType === "subject") {
      handleCreateSubject();
    } else {
      handleCreateChat();
    }
  };

  return (
    <div className="w-64 border-r border-border flex flex-col bg-muted/30">
      <div className="p-3 border-b border-border flex items-center justify-between">
        <h2 className="text-sm font-semibold">Chats</h2>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" className="h-7 w-7">
              <Plus className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => { setCreateType("subject"); setOpen(true); }}>
              New Subject
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => { setCreateType("chat"); setOpen(true); }} disabled={subjects.length === 0}>
              New Chat
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-8 bg-muted rounded animate-pulse" />
            ))}
          </div>
        ) : subjects.length === 0 ? (
          <p className="text-xs text-muted-foreground px-2 py-4">No subjects yet. Create one to get started.</p>
        ) : (
          <Accordion type="multiple" className="w-full">
            {subjects.map((subject) => (
              <AccordionItem key={subject.id} value={`subject-${subject.id}`}>
                <AccordionTrigger className="text-sm py-2 px-2 hover:no-underline">
                  <span className="truncate">{subject.name}</span>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="space-y-1">
                    {(chatsBySubject[subject.id] || []).map((chat) => (
                      <button
                        key={chat.id}
                        onClick={() => onSelectChat(chat.id)}
                        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm text-left transition-colors ${
                          selectedChatId === chat.id
                            ? "bg-accent text-accent-foreground"
                            : "hover:bg-accent/50 text-muted-foreground"
                        }`}
                      >
                        <MessageSquare className="h-3 w-3 shrink-0" />
                        <span className="truncate flex-1">{chat.title}</span>
                        {chat.total_tokens > 0 && (
                          <span className="text-[10px] text-muted-foreground/60 tabular-nums shrink-0">
                            {chat.total_tokens >= 1000
                              ? `${(chat.total_tokens / 1000).toFixed(1)}k`
                              : chat.total_tokens}
                          </span>
                        )}
                      </button>
                    ))}
                    {(!chatsBySubject[subject.id] || chatsBySubject[subject.id].length === 0) && (
                      <p className="text-xs text-muted-foreground px-2 py-1">No chats yet</p>
                    )}
                  </div>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        )}
      </div>

      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New {createType === "subject" ? "Subject" : "Chat"}</DialogTitle>
            <DialogDescription>
              {createType === "subject"
                ? "I want to create a new subject called"
                : "I want to create a new chat for"}
            </DialogDescription>
          </DialogHeader>

          {createType === "subject" ? (
            <div className="space-y-2">
              <Label htmlFor="subject-name">Subject Name</Label>
              <Input
                id="subject-name"
                placeholder="e.g., AP Biology"
                value={subjectName}
                onChange={(e) => setSubjectName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateSubject()}
              />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="chat-subject">Subject</Label>
                <Select value={chatSubjectId} onValueChange={setChatSubjectId}>
                  <SelectTrigger id="chat-subject">
                    <SelectValue placeholder="Select a subject" />
                  </SelectTrigger>
                  <SelectContent>
                    {subjects.map((s) => (
                      <SelectItem key={s.id} value={String(s.id)}>
                        {s.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="chat-mode">Mode</Label>
                <Select value={chatMode} onValueChange={setChatMode}>
                  <SelectTrigger id="chat-mode">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="guide">Guide</SelectItem>
                    <SelectItem value="just-solve">Just Solve</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleDone} disabled={createType === "subject" ? !subjectName.trim() : !chatSubjectId}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
