"""Parser and compiler for the ``bank.csv`` signal reference.

``rules/bank.csv`` is the single source of truth of the trading system: it is a
list of ``if <condition>: add_signal(i, "<name>", "<action>", w1, w2, w3)``
blocks. This module turns that file into executable rules without rewriting any
of them by hand, so editing the reference file changes the traded system.

Two evaluation forms are produced per rule:

* ``vector_code`` - condition with ``and``/``or``/``not`` rewritten to the
  elementwise ``&``/``|``/``~`` so it can run over a whole feature frame at
  once;
* ``scalar_code`` - the original condition, evaluated per bar for rules that
  depend on the state of an open position.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from types import CodeType

# Variables produced by the rule engine itself rather than by the feature engine.
SCORE_VARS = frozenset(
    {
        "EntryScore",
        "ExitScore",
        "BlockScore",
        "SignalCount",
        "SignalDensity",
        "EntryScoreFalling",
        "ExitScoreRising",
    }
)
# Variables that only exist while a position is open.
POSITION_VARS = frozenset({"Profit", "OppositeSignals"})

PHASE_MARKET = "market"
PHASE_SCORE = "score"
PHASE_POSITION = "position"


@dataclass(frozen=True)
class Rule:
    """A single ``if ...: add_signal(...)`` block from the reference file."""

    name: str
    action: str
    weights: tuple[int, int, int]
    phase: str
    source: str
    lineno: int
    variables: frozenset[str]
    vector_code: CodeType = field(repr=False)
    scalar_code: CodeType = field(repr=False)

    @property
    def strength(self) -> float:
        """Confidence of the rule, 0-100, as written in the reference file."""
        return float(self.weights[0])


class RuleParseError(ValueError):
    pass


def load_rules(path: str | Path) -> list[Rule]:
    """Parse the reference file into rules, preserving file order."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_rules(text)


def parse_rules(text: str) -> list[Rule]:
    tree = ast.parse(_clean(text))
    rules: list[Rule] = []
    for node in tree.body:
        if not isinstance(node, ast.If):
            raise RuleParseError(f"line {node.lineno}: expected an 'if' block")
        rules.append(_build_rule(node))
    if not rules:
        raise RuleParseError("no rules found")
    return rules


def _clean(text: str) -> str:
    """Drop markdown fences and stray separator lines from the reference file."""
    keep = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in {".", "```", "```python"}:
            continue
        keep.append(line)
    return "\n".join(keep)


def _build_rule(node: ast.If) -> Rule:
    if len(node.body) != 1 or not isinstance(node.body[0], ast.Expr):
        raise RuleParseError(f"line {node.lineno}: expected a single add_signal call")
    call = node.body[0].value
    if (
        not isinstance(call, ast.Call)
        or not isinstance(call.func, ast.Name)
        or call.func.id != "add_signal"
    ):
        raise RuleParseError(f"line {node.lineno}: body must call add_signal")
    if len(call.args) != 6:
        raise RuleParseError(
            f"line {node.lineno}: add_signal expects 6 arguments, got {len(call.args)}"
        )

    name = _literal(call.args[1], node.lineno)
    action = _literal(call.args[2], node.lineno)
    weights = tuple(int(_literal(a, node.lineno)) for a in call.args[3:6])

    variables = frozenset(
        n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)
    )
    if variables & POSITION_VARS:
        phase = PHASE_POSITION
    elif variables & SCORE_VARS:
        phase = PHASE_SCORE
    else:
        phase = PHASE_MARKET

    return Rule(
        name=name,
        action=str(action).upper(),
        weights=weights,  # type: ignore[arg-type]
        phase=phase,
        source=ast.unparse(node.test),
        lineno=node.lineno,
        variables=variables,
        vector_code=_compile(_Vectorise().visit(ast.parse(ast.unparse(node.test), mode="eval"))),
        scalar_code=compile(ast.Expression(node.test), "<bank.csv>", "eval"),
    )


def _literal(node: ast.expr, lineno: int) -> str | int:
    if not isinstance(node, ast.Constant):
        raise RuleParseError(f"line {lineno}: add_signal arguments must be literals")
    return node.value


def _compile(expr: ast.Expression) -> CodeType:
    ast.fix_missing_locations(expr)
    return compile(expr, "<bank.csv:vector>", "eval")


class _Vectorise(ast.NodeTransformer):
    """Rewrite boolean operators to their elementwise equivalents."""

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.expr:  # noqa: N802
        op = ast.BitAnd() if isinstance(node.op, ast.And) else ast.BitOr()
        values = [self.visit(v) for v in node.values]
        expr = values[0]
        for right in values[1:]:
            expr = ast.BinOp(left=expr, op=op, right=right)
        return expr

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.expr:  # noqa: N802
        if isinstance(node.op, ast.Not):
            return ast.UnaryOp(op=ast.Invert(), operand=self.visit(node.operand))
        return self.generic_visit(node)


def required_variables(rules: list[Rule]) -> frozenset[str]:
    return frozenset().union(*(r.variables for r in rules))
