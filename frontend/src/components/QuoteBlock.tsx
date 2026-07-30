import { Quote, X } from "lucide-react";

interface QuoteBlockProps {
    text: string;
    onClear?: () => void;
}

export default function QuoteBlock({ text, onClear }: QuoteBlockProps) {
    return (
        <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 text-sm w-full">
            <Quote className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <p className="text-muted-foreground truncate flex-1">
                {text}
            </p>
            {onClear && (
                <button
                    type="button"
                    onClick={onClear}
                    className="hover:text-foreground transition-colors shrink-0 cursor-pointer"
                >
                    <X className="h-3 w-3" />
                </button>
            )}
        </div>
    );
}
