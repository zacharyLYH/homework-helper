import { useRef, useEffect, useCallback } from "react";

export default function ResizeHandle({ startWidth, onResize }: { startWidth: number; onResize: (width: number) => void }) {
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startWidth };
  }, [startWidth]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragRef.current) return;
      const delta = e.clientX - dragRef.current.startX;
      onResize(Math.max(180, Math.min(500, dragRef.current.startWidth + delta)));
    };
    const handleMouseUp = () => {
      dragRef.current = null;
    };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [onResize]);

  return (
    <div
      className="w-1.5 cursor-col-resize shrink-0 hover:bg-accent active:bg-accent transition-colors"
      onMouseDown={handleMouseDown}
    />
  );
}
