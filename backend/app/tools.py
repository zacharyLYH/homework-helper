import ast
import operator

import httpx
from langchain_core.tools import tool

from app.schemas import RouteCategory


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


# --- Tools ---


@tool
def calculator(expression: str) -> str:
    """Evaluate a math expression. Supports +, -, *, /, //, %, ** and parentheses."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _safe_eval(tree)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


@tool
def word_count(text: str) -> str:
    """Count the number of words in a piece of text."""
    return str(len(text.split()))


@tool
def text_stats(text: str) -> str:
    """Get word count, character count, and approximate sentence count."""
    words = text.split()
    sentences = max(1, text.count(".") + text.count("!") + text.count("?"))
    return f"Words: {len(words)}, Characters: {len(text)}, Sentences: ~{sentences}"


@tool
def web_search(query: str) -> str:
    """Search the web using DuckDuckGo. Call this tool ANY TIME the user asks about current events, news, recent developments, specific people/places/things, or any factual topic you're not fully confident about. Always search before guessing or making up information."""
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

            return "\n".join(parts[:20]).strip()
    except httpx.HTTPError as e:
        return f"Web search error: {e}"
    except Exception as e:
        return f"Web search error: {e}"


@tool
def route(category: RouteCategory) -> str:
    """Classify the user message into a category. Call this to route the conversation."""
    return category.value


# --- Tool collections ---

REAL_TOOLS = [calculator, word_count, text_stats, web_search]
ALL_TOOLS = REAL_TOOLS + [route]
