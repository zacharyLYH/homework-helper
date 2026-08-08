export type WhiteboardTool =
  | "select"
  | "pen"
  | "line"
  | "arrow"
  | "rect"
  | "ellipse"
  | "text"
  | "eraser";

import Konva from "konva";

export interface WhiteboardElement {
  type: "line" | "arrow" | "rect" | "ellipse" | "path" | "text";
  id: string;
  points?: [number, number][];
  from_pos?: [number, number];
  to_pos?: [number, number];
  x?: number;
  y?: number;
  w?: number;
  h?: number;
  cx?: number;
  cy?: number;
  rx?: number;
  ry?: number;
  d?: string;
  text?: string;
  label?: string;
  fontSize?: number;
  stroke?: string;
  strokeWidth?: number;
  fill?: string;
  kind?: string;
  directed?: boolean;
}

export function uid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `el-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// --- Pending whiteboard drawing (composer draft, tied to a chat) ---
// Persisted in sessionStorage so an accidental refresh keeps the drawing, but
// cleared as soon as the message is submitted or the chat is switched.

const PENDING_KEY = "homework-helper:pending-whiteboard";

export function savePendingDrawing(chatId: number, data: string, mediaType: string): void {
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify({ chatId, data, mediaType }));
  } catch {
    /* storage full/unavailable — draft is best-effort */
  }
}

export function getPendingDrawing(): { chatId: number; data: string; mediaType: string } | null {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    if (!raw) return null;
    const p = JSON.parse(raw);
    return p && typeof p.chatId === "number" && typeof p.data === "string" ? p : null;
  } catch {
    return null;
  }
}

export function clearPendingDrawing(): void {
  try {
    sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* ignore */
  }
}

// Renders a set of elements (typically an AI drawing from a `drawing` SSE
// event) to an offscreen canvas and returns the resulting PNG data URL, so the
// diagram can be shown in chat as an image like a user attachment.
export function renderElementsToDataURL(elements: WhiteboardElement[]): string | null {
  if (!elements.length) return null;
  const holder = document.createElement("div");
  holder.style.cssText = "position:fixed;left:-9999px;top:0;pointer-events:none;";
  document.body.appendChild(holder);
  try {
    const bounds = unionBounds(elements);
    if (!bounds) return null;
    const pad = 24;
    const width = Math.max(1, Math.ceil(bounds.w + pad * 2));
    const height = Math.max(1, Math.ceil(bounds.h + pad * 2));
    const stage = new Konva.Stage({ container: holder, width, height });
    const layer = new Konva.Layer();
    const group = new Konva.Group({ x: pad - bounds.x, y: pad - bounds.y });
    layer.add(group);

    const AI_STROKE = "#94a3b8";
    for (const el of elements) {
      const stroke = el.stroke ?? AI_STROKE;
      const sw = el.strokeWidth ?? 2;
      const fill = el.fill ?? "#00000000";
      const label = el.label ?? el.text ?? "";
      switch (el.type) {
        case "line": {
          const pts = el.points ?? [];
          group.add(
            new Konva.Line({
              points: pts.flat(),
              stroke,
              strokeWidth: sw,
              lineCap: "round",
              lineJoin: "round",
              tension: pts.length > 2 ? 0.4 : 0,
            }),
          );
          break;
        }
        case "arrow": {
          const [fx, fy] = el.from_pos ?? [0, 0];
          const [tx, ty] = el.to_pos ?? [0, 0];
          group.add(
            new Konva.Arrow({
              points: [fx, fy, tx, ty],
              stroke,
              strokeWidth: sw + 1,
              fill: stroke,
              pointerLength: sw * 4 + 2,
              pointerWidth: sw * 4 + 2,
            }),
          );
          break;
        }
        case "rect": {
          group.add(new Konva.Rect({ x: el.x ?? 0, y: el.y ?? 0, width: el.w ?? 0, height: el.h ?? 0, stroke, strokeWidth: sw, fill }));
          if (label) {
            group.add(
              new Konva.Text({
                x: el.x ?? 0,
                y: el.y ?? 0,
                width: el.w ?? 0,
                height: el.h ?? 0,
                text: label,
                align: "center",
                verticalAlign: "middle",
                fontSize: 16,
                fill: AI_STROKE,
              }),
            );
          }
          break;
        }
        case "ellipse": {
          group.add(
            new Konva.Ellipse({
              x: el.cx ?? 0,
              y: el.cy ?? 0,
              radiusX: el.rx ?? 0,
              radiusY: el.ry ?? 0,
              stroke,
              strokeWidth: sw,
              fill,
            }),
          );
          if (label) {
            group.add(
              new Konva.Text({
                x: (el.cx ?? 0) - (el.rx ?? 0),
                y: (el.cy ?? 0) - (el.ry ?? 0),
                width: (el.rx ?? 0) * 2,
                height: (el.ry ?? 0) * 2,
                text: label,
                align: "center",
                verticalAlign: "middle",
                fontSize: 14,
                fill: AI_STROKE,
              }),
            );
          }
          break;
        }
        case "path":
          group.add(new Konva.Path({ data: el.d ?? "", stroke, strokeWidth: sw, fill }));
          break;
        case "text":
          group.add(new Konva.Text({ x: el.x ?? 0, y: el.y ?? 0, text: el.text ?? "", fontSize: el.fontSize ?? 18, fill: AI_STROKE }));
          break;
      }
    }

    stage.add(layer);
    stage.draw();
    const uri = stage.toDataURL({ mimeType: "image/png", pixelRatio: 2 });
    stage.destroy();
    return uri;
  } catch {
    return null;
  } finally {
    holder.remove();
  }
}

// --- Theme-aware colors for Konva strokes ---
// The app defines its palette via oklch CSS variables (see index.css). Konva
// needs a concrete color, so resolve a CSS variable into a hex value. Falls
// back to a plain hex when the variable isn't oklch.

function oklchToHex(value: string): string | null {
  const m = value.match(/^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$/);
  if (!m) return null;
  const L = parseFloat(m[1]);
  const C = parseFloat(m[2]);
  const H = (parseFloat(m[3]) * Math.PI) / 180;

  const a = C * Math.cos(H);
  const b = C * Math.sin(H);

  const l1 = L + 0.3963377774 * a + 0.2158037573 * b;
  const m1 = L - 0.1055613458 * a - 0.0638541728 * b;
  const s1 = L - 0.0894841775 * a - 1.291485548 * b;

  const lC = l1 ** 3;
  const mC = m1 ** 3;
  const sC = s1 ** 3;

  const lr = 4.0767416621 * lC - 3.3077115913 * mC + 0.2309699292 * sC;
  const lg = -1.2684380046 * lC + 2.6097574011 * mC - 0.3413193965 * sC;
  const lb = -0.0041960863 * lC - 0.7034186147 * mC + 1.707614701 * sC;

  const gamma = (c: number) => {
    const cc = Math.max(0, Math.min(1, c));
    const g = cc <= 0.0031308 ? 12.92 * cc : 1.055 * Math.pow(cc, 1 / 2.4) - 0.055;
    return Math.round(g * 255);
  };

  return `rgb(${gamma(lr)}, ${gamma(lg)}, ${gamma(lb)})`;
}

export function themeColor(variableName: string): string {
  if (typeof document === "undefined") return "#000000";
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(variableName)
    .trim();
  if (!value) return "#000000";
  return oklchToHex(value) ?? value;
}

export const TOOL_LABELS: Record<WhiteboardTool, string> = {
  select: "Select",
  pen: "Pen",
  line: "Line",
  arrow: "Arrow",
  rect: "Rectangle",
  ellipse: "Ellipse",
  text: "Text",
  eraser: "Eraser",
};

// --- Geometry helpers ---

export function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const abx = bx - ax;
  const aby = by - ay;
  const apx = px - ax;
  const apy = py - ay;
  const len2 = abx * abx + aby * aby;
  let t = 0;
  if (len2 > 0) t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / len2));
  const cx = ax + t * abx;
  const cy = ay + t * aby;
  return Math.hypot(px - cx, py - cy);
}

export function pointInElement(point: [number, number], el: WhiteboardElement): boolean {
  const [px, py] = point;
  const hit = (el.strokeWidth ?? 2) / 2 + 4;
  switch (el.type) {
    case "line": {
      const pts = el.points ?? [];
      let min = Infinity;
      for (let i = 0; i < pts.length - 1; i++) {
        const [ax, ay] = pts[i] as [number, number];
        const [bx, by] = pts[i + 1] as [number, number];
        min = Math.min(min, distToSegment(px, py, ax, ay, bx, by));
      }
      if (pts.length === 1) min = Math.hypot(px - pts[0][0], py - pts[0][1]);
      return min <= hit;
    }
    case "arrow": {
      const [ax, ay] = el.from_pos ?? [0, 0];
      const [bx, by] = el.to_pos ?? [0, 0];
      return distToSegment(px, py, ax, ay, bx, by) <= hit;
    }
    case "rect": {
      const x = el.x ?? 0;
      const y = el.y ?? 0;
      const w = el.w ?? 0;
      const h = el.h ?? 0;
      return px >= x && px <= x + w && py >= y && py <= y + h;
    }
    case "ellipse": {
      const cx = el.cx ?? 0;
      const cy = el.cy ?? 0;
      const rx = el.rx ?? 0;
      const ry = el.ry ?? 0;
      if (rx <= 0 || ry <= 0) return false;
      const dx = (px - cx) / rx;
      const dy = (py - cy) / ry;
      return dx * dx + dy * dy <= 1;
    }
    case "text": {
      const x = el.x ?? 0;
      const y = el.y ?? 0;
      const size = el.fontSize ?? 24;
      const approxW = ((el.text ?? "").length * size * 0.55) + size;
      const h = size * 1.4;
      return px >= x && px <= x + approxW && py >= y - size && py <= y + h - size;
    }
    default:
      return false;
  }
}

export function hitTest(point: [number, number], elements: WhiteboardElement[]): WhiteboardElement | null {
  for (let i = elements.length - 1; i >= 0; i--) {
    if (pointInElement(point, elements[i])) return elements[i];
  }
  return null;
}

export function elementBounds(el: WhiteboardElement): { x: number; y: number; w: number; h: number } {
  let pts: [number, number][] = [];
  if (el.type === "line") pts = el.points ?? [];
  else if (el.type === "arrow" && el.from_pos && el.to_pos) pts = [el.from_pos, el.to_pos];
  if (el.type === "rect") {
    return { x: el.x ?? 0, y: el.y ?? 0, w: el.w ?? 0, h: el.h ?? 0 };
  }
  if (el.type === "ellipse") {
    const rx = el.rx ?? 0;
    const ry = el.ry ?? 0;
    return { x: (el.cx ?? 0) - rx, y: (el.cy ?? 0) - ry, w: rx * 2, h: ry * 2 };
  }
  if (el.type === "text") {
    const size = el.fontSize ?? 16;
    return { x: el.x ?? 0, y: (el.y ?? 0) - size, w: (el.text ?? "").length * size * 0.55, h: size * 1.4 };
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const [x, y] of pts) {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  if (!Number.isFinite(minX)) return { x: 0, y: 0, w: 0, h: 0 };
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

// Returns a copy of `el` translated by (dx, dy). Note: `path` elements (from
// the AI) aren't translated since their SVG `d` string can't be shifted cheaply.
export function translateElement(el: WhiteboardElement, dx: number, dy: number): WhiteboardElement {
  switch (el.type) {
    case "line":
      return { ...el, points: (el.points ?? []).map(([x, y]) => [x + dx, y + dy]) };
    case "arrow": {
      const [fx, fy] = el.from_pos ?? [0, 0];
      const [tx, ty] = el.to_pos ?? [0, 0];
      return { ...el, from_pos: [fx + dx, fy + dy], to_pos: [tx + dx, ty + dy] };
    }
    case "rect":
      return { ...el, x: (el.x ?? 0) + dx, y: (el.y ?? 0) + dy };
    case "ellipse":
      return { ...el, cx: (el.cx ?? 0) + dx, cy: (el.cy ?? 0) + dy };
    case "text":
      return { ...el, x: (el.x ?? 0) + dx, y: (el.y ?? 0) + dy };
    default:
      return el;
  }
}

export interface Bounds {
  x: number;
  y: number;
  w: number;
  h: number;
}

// Returns a copy of `el` scaled by (sx, sy) about the given anchor point.
// `path` elements (AI-only) aren't scaled here.
export function scaleElement(el: WhiteboardElement, anchor: [number, number], sx: number, sy: number): WhiteboardElement {
  const ax = anchor[0];
  const ay = anchor[1];
  const mapX = (v: number) => ax + (v - ax) * sx;
  const mapY = (v: number) => ay + (v - ay) * sy;
  switch (el.type) {
    case "rect":
      return { ...el, x: mapX(el.x ?? 0), y: mapY(el.y ?? 0), w: (el.w ?? 0) * sx, h: (el.h ?? 0) * sy };
    case "ellipse":
      return { ...el, cx: mapX(el.cx ?? 0), cy: mapY(el.cy ?? 0), rx: (el.rx ?? 0) * sx, ry: (el.ry ?? 0) * sy };
    case "line":
      return { ...el, points: (el.points ?? []).map(([x, y]) => [mapX(x), mapY(y)]) };
    case "arrow": {
      const [fx, fy] = el.from_pos ?? [0, 0];
      const [tx, ty] = el.to_pos ?? [0, 0];
      return { ...el, from_pos: [mapX(fx), mapY(fy)], to_pos: [mapX(tx), mapY(ty)] };
    }
    case "text": {
      const f = Math.max(0.05, Math.sqrt(sx * sy));
      return { ...el, x: mapX(el.x ?? 0), y: mapY(el.y ?? 0), fontSize: Math.max(1, Math.round((el.fontSize ?? 18) * f)) };
    }
    default:
      return el;
  }
}

export function unionBounds(els: WhiteboardElement[]): Bounds | null {
  if (!els.length) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const el of els) {
    const b = elementBounds(el);
    minX = Math.min(minX, b.x);
    minY = Math.min(minY, b.y);
    maxX = Math.max(maxX, b.x + b.w);
    maxY = Math.max(maxY, b.y + b.h);
  }
  if (!Number.isFinite(minX)) return null;
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

export function intersects(a: Bounds, b: Bounds): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}