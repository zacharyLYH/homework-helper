import { Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import { Message, MessageContent } from "@/components/ui/message";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import type { ChatMessage } from "@/lib/api";

export default function MessageBubble({ msg, isStreaming, isLast }: { msg: ChatMessage; isStreaming: boolean; isLast: boolean }) {
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
      </MessageContent>
    </Message>
  );
}
