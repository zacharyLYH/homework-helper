import ast
import operator

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
def route(category: RouteCategory) -> str:
    """Classify the user message into a category. Call this to route the conversation."""
    return category.value


# --- Tool collections ---

REAL_TOOLS = [calculator, word_count, text_stats]
ALL_TOOLS = REAL_TOOLS + [route]
