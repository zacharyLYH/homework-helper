import { useState } from "react";
import {
  PanelLeftClose,
  MessageSquarePlus,
  MessageSquare,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  useSidebar,
} from "@/components/ui/sidebar";
import { InlineRename } from "@/components/InlineRename";
import { MoreMenu } from "@/components/MoreMenu";
import {
  createSubject,
  createChat,
  updateSubject,
  updateChatTitle,
  type Subject,
  type ChatSummary,
} from "@/lib/api";

interface AppSidebarProps {
  subjects: Subject[];
  chatsBySubject: Record<number, ChatSummary[]>;
  loading: boolean;
  selectedChatId: number | null;
  onSelectChat: (chatId: number) => void;
  onChatCreated: (chatId: number, subjectId: number) => void;
  onSubjectCreated: (subject: Subject) => void;
  onClearChat: () => void;
  onSubjectUpdated?: (subject: Subject) => void;
  onChatUpdated?: (chatId: number, subjectId: number, title: string) => void;
}

export function AppSidebar({
  subjects,
  chatsBySubject,
  loading,
  selectedChatId,
  onSelectChat,
  onChatCreated,
  onSubjectCreated,
  onClearChat,
  onSubjectUpdated,
  onChatUpdated,
}: AppSidebarProps) {
  const { toggleSidebar, state } = useSidebar();

  const [createType, setCreateType] = useState<"subject" | "chat">("subject");
  const [subjectName, setSubjectName] = useState("");
  const [chatSubjectId, setChatSubjectId] = useState<string>("");
  const [open, setOpen] = useState(false);

  const [editingSubjectId, setEditingSubjectId] = useState<number | null>(null);
  const [editingChatId, setEditingChatId] = useState<number | null>(null);
  const [hoveredSubjectId, setHoveredSubjectId] = useState<number | null>(null);
  const [hoveredChatId, setHoveredChatId] = useState<number | null>(null);

  const startEditSubject = (subject: Subject) => {
    setEditingSubjectId(subject.id);
    setEditingChatId(null);
  };

  const startEditChat = (chat: ChatSummary) => {
    setEditingChatId(chat.id);
    setEditingSubjectId(null);
  };

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
      const chat = await createChat(Number(chatSubjectId), "New Chat");
      onChatCreated(chat.id, chat.subject_id);
      setChatSubjectId("");
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
    <>
      <Sidebar collapsible="icon" className="border-r border-border">
        <SidebarHeader className="p-4 group-data-[collapsible=icon]:p-2">
          <button
            onClick={() =>
              state === "collapsed" ? toggleSidebar() : onClearChat()
            }
            className="flex items-center gap-2 cursor-pointer group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center"
          >
            <img
              src="/hh-icon.png"
              alt="Homework Helper"
              className="h-7 w-7 rounded-lg shrink-0"
            />
            <h1 className="text-sm font-semibold group-data-[collapsible=icon]:hidden">
              Homework Helper
            </h1>
          </button>
          <div className="hidden group-data-[collapsible=icon]:flex flex-col items-center gap-3 pt-3">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="h-7 w-7 cursor-pointer"
                  onClick={toggleSidebar}
                >
                  <PanelLeftClose className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">Expand sidebar</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="h-7 w-7 cursor-pointer"
                  onClick={() => setOpen(true)}
                >
                  <MessageSquarePlus className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">New chat</TooltipContent>
            </Tooltip>
          </div>
        </SidebarHeader>

        <SidebarContent className=" group-data-[collapsible=icon]:hidden">
          <div className="flex flex-col pb-3">
            <Button
              variant="ghost"
              size="sm"
              className="justify-start gap-2 cursor-pointer"
              onClick={toggleSidebar}
            >
              <PanelLeftClose className="h-4 w-4" />
              <span>Collapse</span>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="justify-start gap-2 cursor-pointer"
              onClick={() => setOpen(true)}
            >
              <MessageSquarePlus className="h-4 w-4" />
              <span>New Chat</span>
            </Button>
          </div>
          {loading ? (
            <SidebarMenu>
              {[1, 2, 3].map((i) => (
                <SidebarMenuItem key={i}>
                  <SidebarMenuSkeleton />
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          ) : subjects.length === 0 ? (
            <p className="text-xs text-muted-foreground px-4 py-8 text-center group-data-[collapsible=icon]:hidden">
              No subjects yet.
            </p>
          ) : (
            subjects.map((subject) => (
              <Collapsible key={subject.id} defaultOpen asChild>
                <SidebarGroup>
                  <SidebarGroupLabel
                    asChild
                    className="text-sm font-normal text-foreground h-9 hover:bg-accent/30 rounded-none p-0"
                  >
                    <div
                      className="flex items-center w-full flex-wrap"
                      onMouseEnter={() => setHoveredSubjectId(subject.id)}
                      onMouseLeave={() => setHoveredSubjectId(null)}
                    >
                      {editingSubjectId === subject.id ? (
                        <InlineRename
                          initialValue={subject.name}
                          onSave={async (value) => {
                            if (subjects.some((s) => s.id !== editingSubjectId && s.name === value)) {
                              throw new Error("A subject with this name already exists");
                            }
                            const updated = await updateSubject(editingSubjectId!, value);
                            onSubjectUpdated?.(updated);
                            setEditingSubjectId(null);
                          }}
                          onCancel={() => setEditingSubjectId(null)}
                          inputClassName="h-7 text-sm px-2 mx-1 flex-1"
                        />
                      ) : (
                        <CollapsibleTrigger className="flex-1 flex items-center gap-2 h-9 px-3 hover:bg-accent/30 rounded-none">
                          <span className="truncate">{subject.name}</span>
                          <ChevronDown className="ml-auto size-3.5 transition-transform group-data-[state=open]/collapsible:rotate-180 shrink-0" />
                        </CollapsibleTrigger>
                      )}
                      <MoreMenu
                        onRename={() => startEditSubject(subject)}
                        show={hoveredSubjectId === subject.id}
                      />
                    </div>
                  </SidebarGroupLabel>
                  <CollapsibleContent>
                    <SidebarGroupContent>
                      <SidebarMenu>
                        {(chatsBySubject[subject.id] || []).map((chat) => (
                          <SidebarMenuItem key={chat.id}>
                            <div
                              className="relative flex items-center"
                              onMouseEnter={() => setHoveredChatId(chat.id)}
                              onMouseLeave={() => setHoveredChatId(null)}
                            >
                              {editingChatId === chat.id ? (
                                <InlineRename
                                  initialValue={chat.title}
                                  onSave={async (value) => {
                                    const sid = Object.entries(chatsBySubject).find(([, chats]) =>
                                      chats.some((c) => c.id === editingChatId),
                                    )?.[0];
                                    if (!sid) return;
                                    if (
                                      chatsBySubject[Number(sid)].some(
                                        (c) => c.id !== editingChatId && c.title === value,
                                      )
                                    ) {
                                      throw new Error("A chat with this title already exists in this subject");
                                    }
                                    await updateChatTitle(editingChatId!, value);
                                    onChatUpdated?.(editingChatId!, Number(sid), value);
                                    setEditingChatId(null);
                                  }}
                                  onCancel={() => setEditingChatId(null)}
                                  inputClassName="h-6 text-sm px-1 py-0"
                                  stopPropagation
                                />
                              ) : (
                                <SidebarMenuButton
                                  isActive={selectedChatId === chat.id}
                                  onClick={() => onSelectChat(chat.id)}
                                  tooltip={chat.title}
                                  className="flex-1 px-4 h-9 text-sm gap-3 hover:bg-accent/30 hover:text-foreground data-[active=true]:bg-accent data-[active=true]:text-accent-foreground data-[active=true]:font-medium rounded-none"
                                >
                                  <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                                  <span className="truncate">
                                    {chat.title}
                                  </span>
                                  {chat.total_tokens > 0 && (
                                    <SidebarMenuBadge className="static ml-auto text-[11px] text-muted-foreground/40 tabular-nums font-normal relative top-auto right-auto">
                                      {chat.total_tokens >= 1000
                                        ? `${(chat.total_tokens / 1000).toFixed(1)}k`
                                        : chat.total_tokens}
                                    </SidebarMenuBadge>
                                  )}
                                </SidebarMenuButton>
                              )}
                              {editingChatId !== chat.id && (
                                <MoreMenu
                                  onRename={() => startEditChat(chat)}
                                  show={hoveredChatId === chat.id}
                                  className="absolute right-1"
                                />
                              )}
                            </div>
                          </SidebarMenuItem>
                        ))}
                        {(!chatsBySubject[subject.id] ||
                          chatsBySubject[subject.id].length === 0) && (
                          <SidebarMenuItem>
                            <span className="text-xs text-muted-foreground/50 px-4 py-2 italic block">
                              No chats yet
                            </span>
                          </SidebarMenuItem>
                        )}
                      </SidebarMenu>
                    </SidebarGroupContent>
                  </CollapsibleContent>
                </SidebarGroup>
              </Collapsible>
            ))
          )}
        </SidebarContent>
      </Sidebar>

      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New</DialogTitle>
          </DialogHeader>
          <Tabs
            value={createType}
            onValueChange={(v) => setCreateType(v as "subject" | "chat")}
          >
            <TabsList className="w-full">
              <TabsTrigger
                value="chat"
                className="flex-1"
                disabled={subjects.length === 0}
              >
                New Chat
              </TabsTrigger>
              <TabsTrigger value="subject" className="flex-1">
                New Subject
              </TabsTrigger>
            </TabsList>
            <TabsContent value="subject">
              <div className="space-y-2 pt-2">
                <Label htmlFor="subject-name">Subject Name</Label>
                <Input
                  id="subject-name"
                  placeholder="e.g., AP Biology"
                  value={subjectName}
                  onChange={(e) => setSubjectName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreateSubject()}
                />
              </div>
            </TabsContent>
            <TabsContent value="chat">
              <div className="space-y-4 pt-2">
                <div className="space-y-2">
                  <Label htmlFor="chat-subject">Subject</Label>
                  <Select
                    value={chatSubjectId}
                    onValueChange={setChatSubjectId}
                  >
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
              </div>
            </TabsContent>
          </Tabs>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleDone}
              disabled={
                createType === "subject" ? !subjectName.trim() : !chatSubjectId
              }
            >
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
