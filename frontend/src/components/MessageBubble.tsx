import { Copy, Loader2, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Message, MessageContent, MessageFooter } from "@/components/ui/message";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import type { ChatMessage } from "@/lib/api";

export default function MessageBubble({ msg, isStreaming, isLast, onRetry }: { msg: ChatMessage; isStreaming: boolean; isLast: boolean; onRetry?: () => void }) {
  const isUser = msg.role === "user";

  if (!isUser && !msg.content && isStreaming && isLast) {
    return (
      <Message align="start">
        <MessageContent>
          <Bubble variant="muted">
            <BubbleContent>
              <Loader2 className="h-4 w-4 animate-spin" />
            </BubbleContent>
          </Bubble>
        </MessageContent>
      </Message>
    );
  }

  return (
    <Message align={isUser ? "end" : "start"}>
      <MessageContent>
        <Bubble variant={isUser ? "default" : "muted"}>
          <BubbleContent>
            {isUser ? (
              <>
                {msg.image && (
                  <img
                    src={`data:${msg.imageMediaType};base64,${msg.image}`}
                    alt={msg.imageName || "Attached image"}
                    className="max-w-full max-h-48 rounded-lg mb-2"
                  />
                )}
                {msg.content}
              </>
            ) : (
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{msg.content}</ReactMarkdown>
              </div>
            )}
          </BubbleContent>
        </Bubble>
        <MessageFooter>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-xs" onClick={() => navigator.clipboard.writeText(msg.content)} className="cursor-pointer">
                <Copy />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Copy</TooltipContent>
          </Tooltip>
          {!(isStreaming && isLast) && onRetry && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-xs" onClick={onRetry} className="cursor-pointer">
                  <RefreshCw />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Retry</TooltipContent>
            </Tooltip>
          )}
        </MessageFooter>
      </MessageContent>
    </Message>
  );
}
