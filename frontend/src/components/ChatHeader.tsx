import { LogOut, PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ModeToggle } from "@/components/mode-toggle";
import { useSidebar } from "@/components/ui/sidebar";

export default function ChatHeader({ email, onLogout }: {
  email?: string;
  onLogout: () => void;
}) {
  const { toggleSidebar } = useSidebar();
  return (
    <header className="flex items-center justify-between px-3 sm:px-4 py-3 border-b border-border gap-2">
      <div className="flex items-center gap-1 min-w-0">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleSidebar}
          title="Toggle sidebar"
          className="md:hidden cursor-pointer"
        >
          <PanelLeft className="h-4 w-4" />
        </Button>
        <span className="md:hidden text-sm font-semibold truncate shrink-0">
          Homework Helper
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="hidden sm:inline text-sm text-muted-foreground truncate max-w-40">
          {email}
        </span>
        <ModeToggle />
        <Button variant="ghost" size="icon" onClick={onLogout} title="Logout">
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}