import { useRef, useEffect } from "react";
import MessageBubble from "@/components/MessageBubble";
import type { ChatMessage } from "@/lib/api";

export default function ChatMessages({ selectedChatId, messages, streaming, onRetry }: { selectedChatId: number | null; messages: ChatMessage[]; streaming: boolean; onRetry?: (index: number) => void }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
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
          <MessageBubble key={i} msg={msg} isStreaming={streaming} isLast={i === messages.length - 1} onRetry={onRetry ? () => onRetry(i) : undefined} />
        ))
      )}
      <div ref={endRef} />
    </div>
  );
}
