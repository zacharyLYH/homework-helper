import { Fragment, forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";
import { Stage, Layer, Line, Arrow, Rect, Ellipse, Text as KonvaText, Path } from "react-konva";
import {
  elementBounds,
  hitTest,
  intersects,
  scaleElement,
  themeColor,
  translateElement,
  uid,
  unionBounds,
  type Bounds,
  type WhiteboardElement,
  type WhiteboardTool,
} from "@/lib/whiteboard";

export interface WhiteboardCanvasHandle {
  screenshot: () => string | null;
  clear: () => void;
  undo: () => void;
}

const DEFAULT_STROKE_WIDTH = 2;

type ResizeDir = "n" | "s" | "e" | "w" | "nw" | "ne" | "sw" | "se";

interface ResizeState {
  dir: ResizeDir;
  anchor: [number, number];
  bounds: Bounds;
  ids: string[];
  prev: WhiteboardElement[];
}

export function renderElement(el: WhiteboardElement, fg: string): ReactNode {
  const stroke = el.stroke ?? fg;
  const sw = el.strokeWidth ?? DEFAULT_STROKE_WIDTH;
  const fill = el.fill ?? "#00000000";
  const label = el.label ?? el.text ?? "";
  const labelFill = fg;

  switch (el.type) {
    case "line": {
      const pts = el.points ?? [];
      return (
        <Line
          key={el.id}
          points={pts.flat()}
          stroke={stroke}
          strokeWidth={sw}
          lineCap="round"
          lineJoin="round"
          tension={pts.length > 2 ? 0.4 : 0}
        />
      );
    }
    case "arrow": {
      const [fx, fy] = el.from_pos ?? [0, 0];
      const [tx, ty] = el.to_pos ?? [0, 0];
      return (
        <Arrow
          key={el.id}
          points={[fx, fy, tx, ty]}
          stroke={stroke}
          strokeWidth={sw + 1}
          fill={stroke}
          pointerLength={(sw * 4) + 2}
          pointerWidth={(sw * 4) + 2}
        />
      );
    }
    case "rect":
      return (
        <Fragment key={el.id}>
          <Rect
            x={el.x ?? 0}
            y={el.y ?? 0}
            width={el.w ?? 0}
            height={el.h ?? 0}
            stroke={stroke}
            strokeWidth={sw}
            fill={fill}
          />
          {label && (
            <KonvaText
              x={el.x ?? 0}
              y={el.y ?? 0}
              width={el.w ?? 0}
              height={el.h ?? 0}
              text={label}
              align="center"
              verticalAlign="middle"
              fontSize={14}
              fill={labelFill}
            />
          )}
        </Fragment>
      );
    case "ellipse":
      return (
        <Fragment key={el.id}>
          <Ellipse
            x={el.cx ?? 0}
            y={el.cy ?? 0}
            radiusX={el.rx ?? 0}
            radiusY={el.ry ?? 0}
            stroke={stroke}
            strokeWidth={sw}
            fill={fill}
          />
          {label && (
            <KonvaText
              x={(el.cx ?? 0) - (el.rx ?? 0)}
              y={(el.cy ?? 0) - (el.ry ?? 0)}
              width={(el.rx ?? 0) * 2}
              height={(el.ry ?? 0) * 2}
              text={label}
              align="center"
              verticalAlign="middle"
              fontSize={13}
              fill={labelFill}
            />
          )}
        </Fragment>
      );
    case "path":
      return (
        <Path
          key={el.id}
          data={el.d ?? ""}
          stroke={stroke}
          strokeWidth={sw}
          fill={fill}
        />
      );
    case "text":
      return (
        <KonvaText
          key={el.id}
          x={el.x ?? 0}
          y={el.y ?? 0}
          text={el.text ?? ""}
          fontSize={el.fontSize ?? 24}
          fill={labelFill}
        />
      );
    default:
      return null;
  }
}

interface WhiteboardCanvasProps {
  tool: WhiteboardTool;
  disabled?: boolean;
  onChange?: (state: { canUndo: boolean; hasContent: boolean }) => void;
}

const RESIZE_HANDLES: { dir: ResizeDir; at: (b: Bounds) => [number, number] }[] = [
  { dir: "nw", at: (b) => [b.x, b.y] },
  { dir: "ne", at: (b) => [b.x + b.w, b.y] },
  { dir: "sw", at: (b) => [b.x, b.y + b.h] },
  { dir: "se", at: (b) => [b.x + b.w, b.y + b.h] },
  { dir: "n", at: (b) => [b.x + b.w / 2, b.y] },
  { dir: "s", at: (b) => [b.x + b.w / 2, b.y + b.h] },
  { dir: "e", at: (b) => [b.x + b.w, b.y + b.h / 2] },
  { dir: "w", at: (b) => [b.x, b.y + b.h / 2] },
];

function resizeAnchor(dir: ResizeDir, b: Bounds): [number, number] {
  const ax = dir.includes("e") ? b.x : dir.includes("w") ? b.x + b.w : b.x;
  const ay = dir.includes("s") ? b.y : dir.includes("n") ? b.y + b.h : b.y;
  return [ax, ay];
}

function resizeScale(dir: ResizeDir, b: Bounds, px: number, py: number): [number, number] {
  let sx = 1;
  let sy = 1;
  if (dir.includes("e")) sx = b.w > 0 ? (px - b.x) / b.w : 1;
  if (dir.includes("w")) sx = b.w > 0 ? (b.x + b.w - px) / b.w : 1;
  if (dir.includes("s")) sy = b.h > 0 ? (py - b.y) / b.h : 1;
  if (dir.includes("n")) sy = b.h > 0 ? (b.y + b.h - py) / b.h : 1;
  const clamp = (v: number) => Math.max(0.05, Math.min(10, v));
  return [clamp(sx), clamp(sy)];
}

const WhiteboardCanvas = forwardRef<WhiteboardCanvasHandle, WhiteboardCanvasProps>(function WhiteboardCanvas(
  { tool, disabled = false, onChange },
  ref,
) {
  const [userElements, setUserElements] = useState<WhiteboardElement[]>([]);
  const [draft, setDraft] = useState<WhiteboardElement | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [textDraft, setTextDraft] = useState<{ x: number; y: number; value: string } | null>(null);
  const [lasso, setLasso] = useState<{ start: [number, number]; cur: [number, number] } | null>(null);
  const [stageSize, setStageSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [fgColor, setFgColor] = useState(() => themeColor("--foreground"));
  const [bgColor, setBgColor] = useState(() => themeColor("--card"));

  const stageRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const elsRef = useRef<WhiteboardElement[]>([]);
  const historyRef = useRef<WhiteboardElement[][]>([]);
  const draggingRef = useRef(false);
  const startRef = useRef<[number, number]>([0, 0]);
  const penRef = useRef(false);
  const moveRef = useRef<{ ids: string[]; start: [number, number]; prev: WhiteboardElement[] } | null>(null);
  const movedRef = useRef(false);
  const resizeRef = useRef<ResizeState | null>(null);
  const textInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    elsRef.current = userElements;
  }, [userElements]);

  useEffect(() => {
    onChange?.({
      canUndo: historyRef.current.length > 0,
      hasContent: userElements.length > 0,
    });
  }, [userElements, onChange]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      setStageSize({ w: el.clientWidth, h: el.clientHeight });
    };
    update();
    const mo = new ResizeObserver(update);
    mo.observe(el);
    return () => mo.disconnect();
  }, []);

  // Re-resolve the ink and canvas colors when the theme class flips, so an
  // existing drawing and the exported PNG both adopt the new theme.
  useEffect(() => {
    const root = document.documentElement;
    const update = () => {
      setFgColor(themeColor("--foreground"));
      setBgColor(themeColor("--card"));
    };
    update();
    const mo = new MutationObserver(update);
    mo.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => mo.disconnect();
  }, []);

  useEffect(() => {
    if (!textDraft) return;
    const t = setTimeout(() => textInputRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [textDraft]);

  const pushHistory = useCallback((snapshot?: WhiteboardElement[]) => {
    historyRef.current.push(JSON.parse(JSON.stringify(snapshot ?? elsRef.current)));
  }, []);

  const setElements = useCallback((next: WhiteboardElement[]) => {
    elsRef.current = next;
    setUserElements(next);
  }, []);

  const undo = useCallback(() => {
    if (textDraft) return;
    const prev = historyRef.current.pop();
    if (prev) {
      setElements(JSON.parse(JSON.stringify(prev)));
      setSelectedIds([]);
    }
  }, [textDraft, setElements]);

  const getPos = useCallback((evt: MouseEvent): [number, number] | null => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return [evt.clientX - rect.left, evt.clientY - rect.top];
  }, []);

  const eraseAt = useCallback(
    (point: [number, number]) => {
      const hit = hitTest(point, elsRef.current);
      if (!hit) return;
      pushHistory();
      setElements(elsRef.current.filter((el) => el.id !== hit.id));
    },
    [pushHistory, setElements],
  );

  const deleteByIds = useCallback(
    (ids: string[]) => {
      const idSet = new Set(ids);
      const targets = elsRef.current.filter((el) => idSet.has(el.id));
      if (!targets.length) return;
      pushHistory();
      setElements(elsRef.current.filter((el) => !idSet.has(el.id)));
    },
    [pushHistory, setElements],
  );

  const addElement = useCallback(
    (el: WhiteboardElement) => {
      pushHistory();
      setElements([...elsRef.current, el]);
    },
    [pushHistory, setElements],
  );

  const selElements = selectedIds
    .map((id) => elsRef.current.find((el) => el.id === id))
    .filter((el): el is WhiteboardElement => Boolean(el));
  const selBounds = selElements.length ? unionBounds(selElements) : null;

  const handleMouseDown = useCallback(
    (e: MouseEvent) => {
      e.preventDefault();
      if (disabled) return;
      const pos = getPos(e);
      if (!pos) return;
      if (textDraft || draft) return;

      switch (tool) {
        case "pen":
          draggingRef.current = true;
          penRef.current = true;
          setDraft({ type: "line", id: uid(), points: [pos], strokeWidth: 3 });
          break;
        case "line":
          draggingRef.current = true;
          penRef.current = false;
          startRef.current = pos;
          setDraft({ type: "line", id: uid(), points: [pos, pos], strokeWidth: DEFAULT_STROKE_WIDTH });
          break;
        case "arrow":
          draggingRef.current = true;
          penRef.current = false;
          startRef.current = pos;
          setDraft({ type: "arrow", id: uid(), from_pos: pos, to_pos: pos, strokeWidth: DEFAULT_STROKE_WIDTH });
          break;
        case "rect":
          draggingRef.current = true;
          penRef.current = false;
          startRef.current = pos;
          setDraft({ type: "rect", id: uid(), x: pos[0], y: pos[1], w: 0, h: 0, strokeWidth: DEFAULT_STROKE_WIDTH });
          break;
        case "ellipse":
          draggingRef.current = true;
          penRef.current = false;
          startRef.current = pos;
          setDraft({ type: "ellipse", id: uid(), cx: pos[0], cy: pos[1], rx: 0, ry: 0, strokeWidth: DEFAULT_STROKE_WIDTH });
          break;
        case "text":
          setTextDraft({ x: pos[0], y: pos[1], value: "" });
          break;
        case "eraser":
          eraseAt(pos);
          break;
        case "select": {
          // Resize handles take priority over element/empty hits.
          if (selBounds) {
            const handle = RESIZE_HANDLES.find((h) => {
              const [hx, hy] = h.at(selBounds);
              return Math.hypot(pos[0] - hx, pos[1] - hy) < 8;
            });
            if (handle) {
              resizeRef.current = {
                dir: handle.dir,
                anchor: resizeAnchor(handle.dir, selBounds),
                bounds: { ...selBounds },
                ids: [...selectedIds],
                prev: JSON.parse(JSON.stringify(elsRef.current)),
              };
              break;
            }
          }

          const hit = hitTest(pos, elsRef.current);
          const inSelectionBox =
            selBounds &&
            pos[0] >= selBounds.x &&
            pos[0] <= selBounds.x + selBounds.w &&
            pos[1] >= selBounds.y &&
            pos[1] <= selBounds.y + selBounds.h;

          let ids: string[];
          if (hit) {
            ids = selectedIds.includes(hit.id) ? [...selectedIds] : [hit.id];
          } else if (inSelectionBox) {
            // Grab the lasso by its empty interior to move the whole group.
            ids = [...selectedIds];
          } else {
            setSelectedIds([]);
            setLasso({ start: pos, cur: pos });
            break;
          }
          setSelectedIds(ids);
          moveRef.current = { ids, start: pos, prev: JSON.parse(JSON.stringify(elsRef.current)) };
          movedRef.current = false;
          break;
        }
      }
    },
    [tool, disabled, getPos, textDraft, draft, eraseAt, selBounds, selectedIds],
  );

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (disabled) return;
    const pos = getPos(e);
    if (!pos) return;

    if (draggingRef.current && draft) {
      if (draft.type === "line" && penRef.current) {
        setDraft((d) => (d ? { ...d, points: [...(d.points ?? []), pos] } : d));
      } else if (draft.type === "arrow") {
        setDraft((d) => (d ? { ...d, to_pos: pos } : d));
      } else if (draft.type === "rect") {
        const [sx, sy] = startRef.current;
        setDraft((d) => (d ? { ...d, x: Math.min(sx, pos[0]), y: Math.min(sy, pos[1]), w: Math.abs(pos[0] - sx), h: Math.abs(pos[1] - sy) } : d));
      } else if (draft.type === "ellipse") {
        // Box-style: the ellipse fills the rectangle from the click point to
        // the cursor, like the rectangle tool.
        const [sx, sy] = startRef.current;
        setDraft((d) =>
          d ? { ...d, cx: (sx + pos[0]) / 2, cy: (sy + pos[1]) / 2, rx: Math.abs(pos[0] - sx) / 2, ry: Math.abs(pos[1] - sy) / 2 } : d,
        );
      } else if (draft.type === "line") {
        setDraft((d) => (d ? { ...d, points: [startRef.current, pos] } : d));
      }
    } else if (tool === "select") {
      if (resizeRef.current) {
        const r = resizeRef.current;
        const [sx, sy] = resizeScale(r.dir, r.bounds, pos[0], pos[1]);
        const idSet = new Set(r.ids);
        const byPrevId = new Map(r.prev.map((p) => [p.id, p]));
        // Always recompute from the frozen pre-resize snapshot so we never
        // compound an already-scaled element.
        setElements(
          elsRef.current.map((el) => {
            if (!idSet.has(el.id)) return el;
            const original = byPrevId.get(el.id) ?? el;
            return scaleElement(original, r.anchor, sx, sy);
          }),
        );
      } else if (moveRef.current) {
        const m = moveRef.current;
        const dx = pos[0] - m.start[0];
        const dy = pos[1] - m.start[1];
        if (dx !== 0 || dy !== 0) movedRef.current = true;
        const idSet = new Set(m.ids);
        const byPrevId = new Map(m.prev.map((p) => [p.id, p]));
        // Recompute from the frozen pre-move snapshot to avoid compounding.
        setElements(
          elsRef.current.map((el) => {
            if (!idSet.has(el.id)) return el;
            const original = byPrevId.get(el.id) ?? el;
            return translateElement(original, dx, dy);
          }),
        );
      } else if (lasso) {
        setLasso({ start: lasso.start, cur: pos });
      }
    } else if (tool === "eraser") {
      eraseAt(pos);
    }
  }, [tool, disabled, getPos, draft, penRef, eraseAt, setElements, lasso]);

  const handleMouseUp = useCallback(() => {
    if (resizeRef.current) {
      const r = resizeRef.current;
      pushHistory(r.prev);
      resizeRef.current = null;
      return;
    }
    if (moveRef.current) {
      if (movedRef.current) pushHistory(moveRef.current.prev);
      moveRef.current = null;
      movedRef.current = false;
    } else if (lasso) {
      const x = Math.min(lasso.start[0], lasso.cur[0]);
      const y = Math.min(lasso.start[1], lasso.cur[1]);
      const w = Math.abs(lasso.cur[0] - lasso.start[0]);
      const h = Math.abs(lasso.cur[1] - lasso.start[1]);
      if (w < 4 || h < 4) {
        setSelectedIds([]);
      } else {
        const box: Bounds = { x, y, w, h };
        setSelectedIds(elsRef.current.filter((el) => intersects(box, elementBounds(el))).map((el) => el.id));
      }
      setLasso(null);
    }
    if (draggingRef.current) {
      draggingRef.current = false;
      const d = draft;
      setDraft(null);
      if (!d) return;
      const b = elementBounds(d);
      if (b.w === 0 && b.h === 0) return;
      pushHistory();
      setElements([...elsRef.current, d]);
    }
  }, [lasso, draft, pushHistory, setElements]);

  const commitText = useCallback(() => {
    if (!textDraft) return;
    if (textDraft.value.trim()) {
      addElement({ type: "text", id: uid(), x: textDraft.x, y: textDraft.y, text: textDraft.value.trim(), fontSize: 18 });
    }
    setTextDraft(null);
  }, [textDraft, addElement]);

  // Input is handled with native DOM listeners on the container rather than
  // react-konva's Stage events, so coordinates always come from a real
  // MouseEvent (evt.clientX/clientY) and never depend on Konva pointer mapping.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("mousedown", handleMouseDown);
    el.addEventListener("mousemove", handleMouseMove);
    el.addEventListener("mouseup", handleMouseUp);
    el.addEventListener("mouseleave", handleMouseUp);
    return () => {
      el.removeEventListener("mousedown", handleMouseDown);
      el.removeEventListener("mousemove", handleMouseMove);
      el.removeEventListener("mouseup", handleMouseUp);
      el.removeEventListener("mouseleave", handleMouseUp);
    };
  }, [handleMouseDown, handleMouseMove, handleMouseUp]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "Delete" || e.key === "Backspace") && selectedIds.length && !disabled && !textDraft) {
        if ((e.target as HTMLElement)?.tagName === "INPUT") return;
        e.preventDefault();
        deleteByIds(selectedIds);
        setSelectedIds([]);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedIds, disabled, textDraft, deleteByIds]);

  useImperativeHandle(ref, () => ({
    screenshot: () => {
      try {
        const uri = stageRef.current?.toDataURL({ mimeType: "image/png", pixelRatio: 2 });
        return typeof uri === "string" ? uri : null;
      } catch {
        return null;
      }
    },
    clear: () => {
      historyRef.current = [];
      elsRef.current = [];
      setUserElements([]);
      setSelectedIds([]);
      setTextDraft(null);
      setDraft(null);
      setLasso(null);
      draggingRef.current = false;
      moveRef.current = null;
      movedRef.current = false;
      resizeRef.current = null;
    },
    undo,
  }));

  const lassoBox: Bounds | null = lasso
    ? {
        x: Math.min(lasso.start[0], lasso.cur[0]),
        y: Math.min(lasso.start[1], lasso.cur[1]),
        w: Math.abs(lasso.cur[0] - lasso.start[0]),
        h: Math.abs(lasso.cur[1] - lasso.start[1]),
      }
    : null;

  return (
    <div ref={containerRef} className="relative flex-1 overflow-hidden bg-card">
      <Stage
        ref={stageRef}
        width={stageSize.w}
        height={stageSize.h}
        style={{ cursor: disabled ? "default" : "crosshair" }}
      >
        <Layer>
          <Rect x={0} y={0} width={stageSize.w} height={stageSize.h} fill={bgColor} />
          {userElements.map((el) => renderElement(el, fgColor))}
          {draft && renderElement(draft, fgColor)}
        </Layer>
        {selBounds && tool === "select" && (
          <Layer listening={false}>
            <Rect
              x={selBounds.x - 4}
              y={selBounds.y - 4}
              width={selBounds.w + 8}
              height={selBounds.h + 8}
              stroke="#f59e0b"
              dash={[4, 4]}
              strokeWidth={1}
            />
            {RESIZE_HANDLES.map((h) => {
              const [hx, hy] = h.at(selBounds);
              return <Rect key={h.dir} x={hx - 4} y={hy - 4} width={8} height={8} fill="#f59e0b" stroke="#ffffff" strokeWidth={1} />;
            })}
          </Layer>
        )}
        {lassoBox && tool === "select" && (
          <Layer listening={false}>
            <Rect
              x={lassoBox.x}
              y={lassoBox.y}
              width={lassoBox.w}
              height={lassoBox.h}
              stroke="#f59e0b"
              dash={[6, 4]}
              strokeWidth={1.5}
            />
          </Layer>
        )}
      </Stage>
      {textDraft &&
        (() => {
          const rect = containerRef.current?.getBoundingClientRect();
          const left = (rect?.left ?? 0) + textDraft.x;
          const top = (rect?.top ?? 0) + textDraft.y;
          return createPortal(
            <input
              ref={textInputRef}
              autoFocus
              value={textDraft.value}
              onChange={(e) => setTextDraft((d) => (d ? { ...d, value: e.target.value } : d))}
              onPointerDown={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitText();
                else if (e.key === "Escape") {
                  e.currentTarget.blur();
                  setTextDraft(null);
                }
              }}
              onBlur={commitText}
              className="rounded-md border border-ring bg-background px-1.5 py-0.5 text-sm text-foreground outline-none shadow-sm"
              style={{ position: "fixed", left, top, width: 200 }}
            />,
            document.body,
          );
        })()}
    </div>
  );
});

export default WhiteboardCanvas;
