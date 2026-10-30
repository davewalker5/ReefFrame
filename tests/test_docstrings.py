"""Keep function and method interface documentation complete."""

import ast
import re
from pathlib import Path


def test_function_docstrings():
    """Require summaries, parameter descriptions and documented return values."""
    root = Path(__file__).resolve().parents[1]
    failures = []
    for directory in ("src", "scripts", "tests"):
        for path in (root / directory).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                location = f"{path.relative_to(root)}:{node.lineno} {node.name}"
                docstring = ast.get_docstring(node)
                if not docstring:
                    failures.append(f"{location}: missing docstring")
                    continue
                parameters = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                if node.args.vararg:
                    parameters.append(node.args.vararg)
                if node.args.kwarg:
                    parameters.append(node.args.kwarg)
                for parameter in parameters:
                    if parameter.arg in ("self", "cls"):
                        continue
                    field = rf"(?m)^:param {re.escape(parameter.arg)}:\s*\S"
                    if not re.search(field, docstring):
                        failures.append(f"{location}: missing :param {parameter.arg}:")
                returns_value = (
                    node.returns is not None and ast.unparse(node.returns) != "None"
                ) or any(
                    isinstance(child, ast.Return)
                    and child.value is not None
                    and not (isinstance(child.value, ast.Constant) and child.value.value is None)
                    for child in ast.walk(node)
                )
                if returns_value and not re.search(r"(?m)^:return:\s*\S", docstring):
                    failures.append(f"{location}: missing :return:")
                yields_value = any(
                    isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node)
                )
                if yields_value and not re.search(r"(?m)^:yields:\s*\S", docstring):
                    failures.append(f"{location}: missing :yields:")
    assert not failures, "\n".join(failures)
