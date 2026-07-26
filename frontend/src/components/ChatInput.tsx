import { useState, useRef } from "react";
import { Send, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Attachment, AttachmentMedia, AttachmentContent, AttachmentTitle, AttachmentActions, AttachmentAction } from "@/components/ui/attachment";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface ChatInputProps {
  onSubmit: (text: string, image?: { data: string; mediaType: string; name: string }) => void;
  streaming: boolean;
  selectedChatId: number | null;
  selectedChatTokens: number;
  chatTokenLimit: number;
  chatTokenPercent: number;
}

export default function ChatInput({ onSubmit, streaming, selectedChatId, selectedChatTokens, chatTokenLimit, chatTokenPercent }: ChatInputProps) {
  const [input, setInput] = useState("");
  const [imageData, setImageData] = useState<string | null>(null);
  const [imageMediaType, setImageMediaType] = useState<string | null>(null);
  const [imageName, setImageName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textInputRef = useRef<HTMLTextAreaElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !file.type.startsWith("image/")) {
      e.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(",")[1];
      setImageData(base64);
      setImageMediaType(file.type);
      setImageName(file.name);
      fileInputRef.current?.blur();
      textInputRef.current?.focus();
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const clearImage = () => {
    setImageData(null);
    setImageMediaType(null);
    setImageName("");
  };

  const handleSubmit = (e: { preventDefault: () => void }) => {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || streaming || !selectedChatId) return;

    const image = imageData ? { data: imageData, mediaType: imageMediaType || "", name: imageName } : undefined;
    setInput("");
    clearImage();
    onSubmit(msg, image);
  };

  return (
    <form onSubmit={handleSubmit} className="border-t border-border bg-background">
      <div className="max-w-3xl mx-auto p-4">
        <div className="rounded-3xl border border-border bg-muted/30 shadow-xs transition-shadow focus-within:shadow-sm focus-within:border-ring/50">
          {imageData && (
            <div className="flex items-center gap-2 px-4 pt-3">
              <Attachment size="sm">
                <AttachmentMedia variant="image">
                  <img
                    src={`data:${imageMediaType};base64,${imageData}`}
                    alt={imageName}
                    className="h-full w-full object-cover"
                  />
                </AttachmentMedia>
                <AttachmentContent>
                  <AttachmentTitle>{imageName}</AttachmentTitle>
                </AttachmentContent>
                <AttachmentActions>
                  <AttachmentAction type="button" aria-label="Remove attachment" onClick={clearImage}>
                    <X className="h-3 w-3" />
                  </AttachmentAction>
                </AttachmentActions>
              </Attachment>
            </div>
          )}
          <div className="flex items-end gap-2 p-3">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileSelect}
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={streaming || !selectedChatId}
                  className="cursor-pointer shrink-0 text-muted-foreground hover:text-foreground"
                >
                  <Paperclip className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Attach image</TooltipContent>
            </Tooltip>
            <Textarea
              ref={textInputRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
              placeholder={imageData ? "Add a message (optional)..." : "Type your message..."}
              disabled={streaming || !selectedChatId}
              className="min-h-0 max-h-40 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 px-0 py-1.5"
            />
            <div className="flex items-center gap-1 shrink-0">
              {selectedChatId && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button type="button" className="relative flex items-center justify-center w-7 h-7 shrink-0">
                      <svg className="w-5 h-5 -rotate-90" viewBox="0 0 36 36">
                        <circle cx="18" cy="18" r="15" fill="none" stroke="currentColor" strokeWidth="3" className="text-border" />
                        <circle
                          cx="18" cy="18" r="15" fill="none" stroke="currentColor" strokeWidth="3"
                          strokeDasharray={`${chatTokenPercent} 100`}
                          className="text-muted-foreground/30"
                          strokeLinecap="round"
                        />
                      </svg>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>{selectedChatTokens.toLocaleString()} / {chatTokenLimit.toLocaleString()} tokens</p>
                  </TooltipContent>
                </Tooltip>
              )}
              <Button
                type="submit"
                disabled={streaming || !selectedChatId || !input.trim()}
                title={streaming ? "Waiting for response..." : "Send message"}
                className="cursor-pointer rounded-full"
                size={input.trim() ? "icon" : "icon"}
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </form>
  );
}
