import { useState, useRef } from "react";
import { Send, Paperclip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  const textInputRef = useRef<HTMLInputElement>(null);

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const msg = input.trim();
    if (!msg || streaming || !selectedChatId) return;

    const image = imageData ? { data: imageData, mediaType: imageMediaType || "", name: imageName } : undefined;
    setInput("");
    clearImage();
    onSubmit(msg, image);
  };

  return (
    <form onSubmit={handleSubmit} className="border-t border-border p-4">
      <div className="max-w-2xl mx-auto space-y-2">
        {imageData && (
          <div className="flex items-center gap-2">
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
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileSelect}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => fileInputRef.current?.click()}
            disabled={streaming || !selectedChatId}
            title="Attach image"
            className="cursor-pointer"
          >
            <Paperclip className="h-4 w-4" />
          </Button>
          <Input
            ref={textInputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={imageData ? "Add a message (optional)..." : "Type your message..."}
            disabled={streaming || !selectedChatId}
          />
          <Button
            type="submit"
            disabled={streaming || !selectedChatId || !input.trim()}
            title={streaming ? "Waiting for response..." : "Send message"}
            className="cursor-pointer"
          >
            <Send className="h-4 w-4" />
          </Button>
          {selectedChatId && (
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" className="relative flex items-center justify-center w-9 h-9 shrink-0">
                  <svg className="w-6 h-6 -rotate-90" viewBox="0 0 36 36">
                    <circle cx="18" cy="18" r="15" fill="none" stroke="currentColor" strokeWidth="3" className="text-border" />
                    <circle
                      cx="18" cy="18" r="15" fill="none" stroke="currentColor" strokeWidth="3"
                      strokeDasharray={`${chatTokenPercent} 100`}
                      className="text-muted-foreground/40"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p>{selectedChatTokens.toLocaleString()} / {chatTokenLimit.toLocaleString()} tokens</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>
    </form>
  );
}
