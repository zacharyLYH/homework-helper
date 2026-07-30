import { useState, useCallback, useRef } from "react";
import { Sigma, Check } from "lucide-react";
import "mathlive";
import { MathfieldElement } from "mathlive";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

MathfieldElement.fontsDirectory = "/fonts/";

interface MathEquationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInsert: (latex: string) => void;
}

export default function MathEquationDialog({
  open,
  onOpenChange,
  onInsert,
}: MathEquationDialogProps) {
  const [hasValue, setHasValue] = useState(false);
  const valueRef = useRef("");

  const handleInsert = useCallback(() => {
    const v = valueRef.current.trim();
    if (!v) return;
    onInsert(`$$${v}$$`);
    onOpenChange(false);
  }, [onInsert, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sigma className="h-4 w-4" />
            Type a math expression
          </DialogTitle>
        </DialogHeader>

        <math-field
          class="min-h-24 p-3 border border-border rounded-lg focus-within:border-ring bg-background text-base w-full"
          style={{ outline: "none" }}
          onInput={(e: React.FormEvent<HTMLElement>) => {
            const v = (e.target as MathfieldElement).value ?? "";
            valueRef.current = v;
            setHasValue(!!v.trim());
          }}
        />

        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="destructive" className="cursor-pointer">
              Cancel
            </Button>
          </DialogClose>
          <Button
            type="button"
            onClick={handleInsert}
            disabled={!hasValue}
            className="cursor-pointer"
          >
            <Check className="h-4 w-4 mr-1" />
            Insert
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
