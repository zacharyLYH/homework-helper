import { LogOut, Bug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ModeToggle } from "@/components/mode-toggle";

export default function ChatHeader({ email, onDebug, onLogout }: {
  email?: string;
  onDebug: () => void;
  onLogout: () => void;
}) {
  return (
    <header className="flex items-center justify-end px-4 py-3 border-b border-border gap-2">
      <span className="text-sm text-muted-foreground">{email}</span>
      <ModeToggle />
      <Button variant="ghost" size="icon" onClick={onDebug} title="Debug">
        <Bug className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" onClick={onLogout} title="Logout">
        <LogOut className="h-4 w-4" />
      </Button>
    </header>
  );
}
