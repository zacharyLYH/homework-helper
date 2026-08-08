import { ArrowLeft, Eraser, Minus, MousePointer2, Pen, Redo2, Square, Trash2, Type, Circle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { WhiteboardTool } from "@/lib/whiteboard";
import { TOOL_LABELS } from "@/lib/whiteboard";

const TOOLS: { id: WhiteboardTool; icon: React.ElementType }[] = [
  { id: "select", icon: MousePointer2 },
  { id: "pen", icon: Pen },
  { id: "line", icon: Minus },
  { id: "arrow", icon: ArrowRight },
  { id: "rect", icon: Square },
  { id: "ellipse", icon: Circle },
  { id: "text", icon: Type },
  { id: "eraser", icon: Eraser },
];

interface WhiteboardToolbarProps {
  tool: WhiteboardTool;
  onToolChange: (tool: WhiteboardTool) => void;
  onUndo: () => void;
  canUndo: boolean;
  onClear: () => void;
  onBack: () => void;
  disabled?: boolean;
}

export default function WhiteboardToolbar({
  tool,
  onToolChange,
  onUndo,
  canUndo,
  onClear,
  onBack,
  disabled = false,
}: WhiteboardToolbarProps) {
  return (
    <div className="flex items-center gap-2 border-b border-border bg-background px-3 sm:px-4 py-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" onClick={onBack} disabled={disabled} title="Back to chat" className="cursor-pointer">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Back to chat</TooltipContent>
      </Tooltip>

      <Separator orientation="vertical" className="h-6 shrink-0" />

      <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto scrollbar-thin">
        {TOOLS.map((t) => {
          const Icon = t.icon;
          const active = tool === t.id;
          return (
            <Tooltip key={t.id}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => onToolChange(t.id)}
                  disabled={disabled}
                  aria-pressed={active}
                  className={cn("cursor-pointer", active && "bg-accent text-accent-foreground")}
                >
                  <Icon className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{TOOL_LABELS[t.id]}</TooltipContent>
            </Tooltip>
          );
        })}
      </div>

      <Separator orientation="vertical" className="h-6 shrink-0" />

      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="secondary" size="icon" onClick={onUndo} disabled={disabled || !canUndo} title="Undo">
            <Redo2 className="h-4 w-4 -scale-x-100" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Undo</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="destructive" size="icon" onClick={onClear} disabled={disabled} title="Clear canvas">
            <Trash2 className="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Clear canvas</TooltipContent>
      </Tooltip>
    </div>
  );
}