import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import MessageBubble from "@/components/MessageBubble";
import { Button } from "@/components/ui/button";
import type { ChatMessage, ToolCallInfo } from "@/lib/api";

export default function ChatMessages({
  selectedChatId,
  messages,
  streaming,
  toolCalls,
  onRetry,
  llmReady,
  onActivate,
}: {
  selectedChatId: number | null;
  messages: ChatMessage[];
  streaming: boolean;
  toolCalls: ToolCallInfo[];
  onRetry?: (index: number) => void;
  llmReady: boolean;
  onActivate: () => void;
}) {
  return (
    <div className="flex-1 overflow-hidden">
      {!llmReady ? (
        <ActivationPanel onActivate={onActivate} />
      ) : (
        <MessageScrollerProvider
          autoScroll
          defaultScrollPosition="last-anchor"
          scrollPreviousItemPeek={64}
        >
          {!selectedChatId ? (
            <div className="flex flex-col items-center justify-center h-full gap-4 p-4 px-8">
              <img
                src="/hh-icon.png"
                alt="Homework Helper"
                className="h-14 w-14 rounded-2xl"
              />
              <div className="text-center space-y-2">
                <h2 className="text-xl font-semibold text-foreground">
                  Homework Helper
                </h2>
                <p className="text-sm text-muted-foreground max-w-sm leading-relaxed">
                  I can help you understand concepts, solve problems, and prepare
                  for exams. Select an existing chat or create a new chat!
                </p>
              </div>
            </div>
          ) : (
            <MessageScroller>
              <MessageScrollerViewport>
                <MessageScrollerContent
                  className="p-4 gap-6"
                  aria-busy={streaming}
                >
                  {messages.map((msg, i) => (
                    <MessageScrollerItem
                      key={msg.id ?? i}
                      messageId={String(msg.id ?? i)}
                      scrollAnchor={msg.role === "user"}
                    >
                      <div className="animate-fade-in">
                        <MessageBubble
                          msg={msg}
                          isStreaming={streaming}
                          isLast={i === messages.length - 1}
                          onRetry={onRetry ? () => onRetry(i) : undefined}
                        />
                        {(() => {
                          const showStreaming =
                            toolCalls.length > 0 &&
                            i === messages.length - 2 &&
                            msg.role === "user";
                          const chips = showStreaming
                            ? toolCalls
                            : (msg.toolCalls ?? []);
                          if (chips.length === 0) return null;
                          return (
                            <div className="flex flex-wrap gap-2 mt-2">
                              {chips.map((tc, idx) => (
                                <div
                                  key={tc.id ?? idx}
                                  className="flex items-center gap-1.5 text-xs text-muted-foreground bg-muted/50 rounded-full px-3 py-1"
                                >
                                  <span
                                    className={`h-2 w-2 rounded-full bg-blue-500 ${showStreaming ? "animate-pulse" : ""}`}
                                  />
                                  {showStreaming
                                    ? tc.name === "web_search"
                                      ? `Searching for "${tc.args.query}"`
                                      : `Using ${tc.name}...`
                                    : tc.name === "web_search"
                                      ? `Searched for "${tc.args.query}"`
                                      : `Used ${tc.name}`}
                                </div>
                              ))}
                            </div>
                          );
                        })()}
                      </div>
                    </MessageScrollerItem>
                  ))}
                </MessageScrollerContent>
              </MessageScrollerViewport>
              <MessageScrollerButton />
            </MessageScroller>
          )}
        </MessageScrollerProvider>
      )}
    </div>
  );
}

function ActivationPanel({ onActivate }: { onActivate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 p-4 px-8">
      <img
        src="/hh-icon.png"
        alt="Homework Helper"
        className="h-14 w-14 rounded-2xl"
      />
      <div className="text-center space-y-3 max-w-sm">
        <h2 className="text-xl font-semibold text-foreground">
          No active LLM
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          You need at least one model for chat and one for memory before you can
          start asking questions. Add your model choices and API keys in Settings
          to activate your LLM.
        </p>
        <Button onClick={onActivate} className="cursor-pointer">
          Activate your LLM
        </Button>
      </div>
    </div>
  );
}
