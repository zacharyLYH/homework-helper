import { useCallback, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ClipboardPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import WhiteboardCanvas, { type WhiteboardCanvasHandle } from "@/components/WhiteboardCanvas";
import WhiteboardToolbar from "@/components/WhiteboardToolbar";
import { savePendingDrawing, type WhiteboardTool } from "@/lib/whiteboard";

export default function WhiteboardPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const chatIdParam = searchParams.get("chatId");
  const chatId = chatIdParam && /^\d+$/.test(chatIdParam) ? Number(chatIdParam) : null;

  const [tool, setTool] = useState<WhiteboardTool>("pen");
  const [canvasState, setCanvasState] = useState({ canUndo: false, hasContent: false });

  const canvasRef = useRef<WhiteboardCanvasHandle>(null);

  const handleBack = useCallback(() => {
    navigate(chatId ? `/chat?chatId=${chatId}` : "/chat");
  }, [navigate, chatId]);

  const handleAttach = useCallback(() => {
    if (!chatId || !canvasState.hasContent) return;
    const uri = canvasRef.current?.screenshot();
    if (!uri) return;
    const base64 = uri.split(",")[1];
    savePendingDrawing(chatId, base64, "image/png");
    navigate(`/chat?chatId=${chatId}`);
  }, [chatId, canvasState.hasContent, navigate]);

  return (
    <div className="flex h-svh flex-col bg-background">
      <WhiteboardToolbar
        tool={tool}
        onToolChange={setTool}
        onUndo={() => canvasRef.current?.undo()}
        canUndo={canvasState.canUndo}
        onClear={() => canvasRef.current?.clear()}
        onBack={handleBack}
      />

      {!chatId && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 text-muted-foreground">
          <p>No chat selected.</p>
          <Button onClick={() => navigate("/chat")}>Back to chat</Button>
        </div>
      )}

      {chatId && (
        <>
          <WhiteboardCanvas ref={canvasRef} tool={tool} onChange={setCanvasState} />
          <div className="border-t border-border bg-background">
            <div className="mx-auto flex items-center justify-end gap-2 p-3">
              <Button
                onClick={handleAttach}
                disabled={!canvasState.hasContent}
                className="shrink-0 cursor-pointer"
              >
                <ClipboardPlus className="h-4 w-4" />
                Attach to chat
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}