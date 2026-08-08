import ast
import json
import operator

import httpx
from langchain_core.tools import tool

from app.logging import structured_log
from app.schemas import EdgeSpec, ElementSpec, NodeSpec, RouteCategory


# --- Safe math evaluator (no eval) ---

SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in SAFE_OPS:
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return SAFE_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_OPS:
        return SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


# --- Whiteboard helpers ---

CANVAS_H = 1000.0
NODE_W = 160.0
NODE_H = 80.0
GAP_X = 80.0
GAP_Y = 100.0


def _layout_diagram(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> list[ElementSpec]:
    """Simple layered auto-layout. Assigns x/y to each node, resolves edges to coords."""
    # Assign layers via BFS from nodes with no incoming edges.
    incoming: dict[str, int] = {n.id: 0 for n in nodes}
    for e in edges:
        incoming[e.to_id] = incoming.get(e.to_id, 0) + 1

    layer: dict[str, int] = {}
    queue = [n.id for n in nodes if incoming.get(n.id, 0) == 0]
    for n in nodes:
        if n.id not in layer:
            queue.append(n.id)
    while queue:
        nid = queue.pop(0)
        layer[nid] = layer.get(nid, 0)
        for e in edges:
            if e.from_id == nid and e.to_id not in layer:
                layer[e.to_id] = layer[nid] + 1
                queue.append(e.to_id)

    # Group nodes by layer, stack vertically.
    by_layer: dict[int, list[NodeSpec]] = {}
    for n in nodes:
        by_layer.setdefault(layer.get(n.id, 0), []).append(n)

    elements: list[ElementSpec] = []
    positions: dict[str, tuple[float, float]] = {}

    for lvl, col in by_layer.items():
        col_h = len(col) * (NODE_H + GAP_Y) - GAP_Y
        start_y = (CANVAS_H - col_h) / 2
        for i, n in enumerate(col):
            x = 100 + lvl * (NODE_W + GAP_X)
            y = start_y + i * (NODE_H + GAP_Y)
            positions[n.id] = (x, y)
            elements.append(ElementSpec(
                type="rect", id=n.id, x=x, y=y, w=NODE_W, h=NODE_H,
                label=n.label, kind=n.kind, stroke="#3b82f6", strokeWidth=2,
            ))

    for e in edges:
        fx, fy = positions.get(e.from_id, (0, 0))
        tx, ty = positions.get(e.to_id, (0, 0))
        elements.append(ElementSpec(
            type="arrow", id=f"edge-{e.from_id}-{e.to_id}",
            from_pos=[fx + NODE_W / 2, fy + NODE_H / 2],
            to_pos=[tx + NODE_W / 2, ty + NODE_H / 2],
            label=e.label, directed=e.directed, stroke="#94a3b8", strokeWidth=2,
        ))

    return elements


# --- Tools ---


@tool
def calculator(expression: str) -> str:
    """Evaluate a math expression. Supports +, -, *, /, //, %, ** and parentheses."""
    structured_log("tool_input", tool="calculator", expression=expression)
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _safe_eval(tree)
        structured_log("tool_output", tool="calculator", result=result)
        return str(result)
    except Exception as e:
        structured_log("tool_output", tool="calculator", error=str(e))
        return f"Error: {e}"


@tool
def word_count(text: str) -> str:
    """Count the number of words in a piece of text."""
    structured_log("tool_input", tool="word_count", text_length=len(text))
    result = str(len(text.split()))
    structured_log("tool_output", tool="word_count", count=len(text.split()))
    return result


@tool
def text_stats(text: str) -> str:
    """Get word count, character count, and approximate sentence count."""
    structured_log("tool_input", tool="text_stats", text_length=len(text))
    words = text.split()
    sentences = max(1, text.count(".") + text.count("!") + text.count("?"))
    result = f"Words: {len(words)}, Characters: {len(text)}, Sentences: ~{sentences}"
    structured_log("tool_output", tool="text_stats", word_count=len(words), char_count=len(text), sentence_count=sentences)
    return result


@tool
def web_search(query: str) -> str:
    """Search the web using DuckDuckGo. Call this tool ANY TIME the user asks about current events, news, recent developments, specific people/places/things, or any factual topic you're not fully confident about. Always search before guessing or making up information."""
    structured_log("tool_input", tool="web_search", query=query)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; SearchBot/1.0)",
        }
        with httpx.Client(timeout=10.0, headers=headers) as client:
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()

            parts = []

            abstract = data.get("AbstractText", "")
            if abstract:
                source = data.get("AbstractSource", "")
                url = data.get("AbstractURL", "")
                parts.append(f"Featured snippet: {abstract}")
                if source:
                    parts.append(f"Source: {source} ({url})")
                parts.append("")

            heading = data.get("Heading", "")
            definition = data.get("Definition", "")
            if heading and definition:
                parts.append(f"{heading}: {definition}")
                parts.append("")

            answer = data.get("Answer", "")
            answer_type = data.get("AnswerType", "")
            if answer:
                parts.append(f"Answer: {answer}")
                if answer_type:
                    parts.append(f"Type: {answer_type}")
                parts.append("")

            results = data.get("Results", [])
            if results:
                parts.append("Results:")
                for i, r in enumerate(results[:8], 1):
                    text = r.get("Text", "")
                    result_url = r.get("FirstURL", "")
                    if text:
                        parts.append(f"  {i}. {text}")
                    if result_url:
                        parts.append(f"     {result_url}")
                parts.append("")

            for topic in data.get("RelatedTopics", []):
                if "Text" in topic:
                    parts.append(f"- {topic['Text']}")
                elif "Topics" in topic:
                    for t in topic["Topics"][:3]:
                        text = t.get("Text", "")
                        if text:
                            parts.append(f"- {text}")

            if not parts:
                return f"No results found for '{query}'."

            result = "\n".join(parts[:20]).strip()
            structured_log("tool_output", tool="web_search", query=query, result_length=len(result), num_results=len(parts))
            return result
    except httpx.HTTPError as e:
        structured_log("tool_output", tool="web_search", error=str(e))
        return f"Web search error: {e}"
    except Exception as e:
        structured_log("tool_output", tool="web_search", error=str(e))
        return f"Web search error: {e}"


def _serialize(elements: list[ElementSpec], tool: str) -> str:
    payload = json.dumps([e.model_dump() for e in elements])
    structured_log("tool_output", tool=tool, element_count=len(elements))
    return payload


@tool
def create_diagram(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> str:
    """Create a diagram from semantic nodes and edges. Layout is automatic — you never specify coordinates.
    nodes: {id, label, kind (box|ellipse|diamond)}. edges: {from_id, to_id, label?, directed?}.
    The result renders on the student's canvas automatically."""
    structured_log(
        "tool_input",
        tool="create_diagram",
        node_count=len(nodes),
        edge_count=len(edges),
        node_kinds={k: sum(1 for n in nodes if n.kind == k) for k in {n.kind for n in nodes}},
        edge_directed=sum(1 for e in edges if e.directed),
        node_labels=[n.label for n in nodes],
        edge_labels=[e.label for e in edges if e.label],
    )
    return _serialize(_layout_diagram(nodes, edges), "create_diagram")


@tool
def draw_elements(elements: list[ElementSpec]) -> str:
    """Draw arbitrary primitives at explicit positions. For freehand sketches, plots, geometry, and function graphs.
    element types: line (points), arrow (from_pos,to_pos), rect (x,y,w,h), ellipse (cx,cy,rx,ry), path (d), text (x,y,text).
    The result renders on the student's canvas automatically."""
    structured_log(
        "tool_input",
        tool="draw_elements",
        element_count=len(elements),
        element_types={t: sum(1 for el in elements if el.type == t) for t in {el.type for el in elements}},
    )
    return _serialize(elements, "draw_elements")


@tool
def route(category: RouteCategory) -> str:
    """Classify the user message into a category. Call this to route the conversation."""
    structured_log("tool_input", tool="route", category=category.value)
    structured_log("tool_output", tool="route", result=category.value)
    return category.value


# --- Tool collections ---

REAL_TOOLS = [calculator, word_count, text_stats, web_search]
WHITEBOARD_TOOLS = [create_diagram, draw_elements]
ALL_TOOLS = REAL_TOOLS + WHITEBOARD_TOOLS + [route]
WHITEBOARD_TOOL_NAMES = {t.name for t in WHITEBOARD_TOOLS}
