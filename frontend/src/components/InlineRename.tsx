import { useState, useRef, useEffect } from "react";
import { Input } from "@/components/ui/input";

interface InlineRenameProps {
  initialValue: string;
  onSave: (value: string) => Promise<void>;
  onCancel: () => void;
  inputClassName?: string;
  stopPropagation?: boolean;
}

export function InlineRename({
  initialValue,
  onSave,
  onCancel,
  inputClassName,
  stopPropagation,
}: InlineRenameProps) {
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState("");
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);

  const handleSave = async () => {
    const trimmed = value.trim();
    if (!trimmed) {
      setError("Name cannot be empty");
      return;
    }
    if (trimmed === initialValue) {
      onCancel();
      return;
    }
    try {
      await onSave(trimmed);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSave();
    }
    if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    }
    if (stopPropagation) e.stopPropagation();
  };

  return (
    <>
      <Input
        ref={ref}
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setError("");
        }}
        onKeyDown={handleKeyDown}
        onBlur={handleSave}
        className={inputClassName}
      />
      {error && (
        <p className="text-xs text-destructive w-full">{error}</p>
      )}
    </>
  );
}
