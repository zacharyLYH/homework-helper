import { useState } from "react";
import { Check, Copy, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Message, MessageContent, MessageFooter } from "@/components/ui/message";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import type { ChatMessage } from "@/lib/api";

function CodeBlock({ className, children, ...props }: React.ComponentPropsWithoutRef<"code">) {
  const [copied, setCopied] = useState(false);
  const code = String(children).replace(/\n$/, "");

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="relative group">
      <div className="flex items-center justify-between rounded-t-lg bg-zinc-800 px-4 py-1.5 text-xs text-zinc-400">
        <span>{className?.replace("language-", "") || "code"}</span>
        <button onClick={handleCopy} className="hover:text-zinc-200 transition-colors">
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
      <pre className="overflow-x-auto rounded-b-lg bg-zinc-900 p-4 text-sm leading-relaxed">
        <code className={className} {...props}>{children}</code>
      </pre>
    </div>
  );
}

export default function MessageBubble({ msg, isStreaming, isLast, onRetry }: { msg: ChatMessage; isStreaming: boolean; isLast: boolean; onRetry?: () => void }) {
  const isUser = msg.role === "user";

  if (!isUser && !msg.content && isStreaming && isLast) {
    return (
      <Message align="start">
        <MessageContent>
          <Bubble variant="muted">
            <BubbleContent>
              <span className="flex items-center gap-1 py-1">
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce" style={{ animationDelay: "300ms" }} />
              </span>
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
              <div className="prose prose-sm max-w-none dark:prose-invert">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkMath]}
                  rehypePlugins={[rehypeRaw, rehypeKatex]}
                  components={{
                    code({ className, children, ...props }) {
                      return <CodeBlock className={className} {...props}>{children}</CodeBlock>;
                    },
                  }}
                >
                  {msg.content.replace(/\\n/g, "\n")}
                </ReactMarkdown>
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
