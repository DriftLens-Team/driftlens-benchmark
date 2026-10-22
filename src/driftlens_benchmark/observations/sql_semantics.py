"""Conservative AST recognition, not a general SQL equivalence solver.

Recognizes only COUNT over orders with a weekly range and a nonnegative integer
amount threshold. Unsupported syntax returns None, rather than guessing intent.
"""

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class CountMeaning:
    start: str
    end: str
    threshold: int


def active_only(node, allowed):
    return all(
        key in allowed or value is None or value is False or value == [] for key, value in node.args.items()
    )


def unparen(node):
    while isinstance(node, exp.Paren):
        node = node.this
    return node


def meaning(sql):
    if type(sql) is not str or len(sql) > 10000:
        return None
    try:
        trees = sqlglot.parse(sql, read="sqlite")
        if len(trees) != 1:
            return None
        tree = trees[0]
        if not isinstance(tree, exp.Select) or not active_only(tree, {"expressions", "from_", "where"}):
            return None
        table = tree.args["from_"].this
        if (
            not isinstance(table, exp.Table)
            or table.name.lower() != "orders"
            or not active_only(table, {"this", "alias"})
        ):
            return None
        qualifiers = {"", "orders", table.alias.lower()}

        def column(node, name):
            return (
                isinstance(node, exp.Column)
                and node.name.lower() == name
                and node.table.lower() in qualifiers
                and not node.db
                and not node.catalog
            )

        if len(tree.expressions) != 1:
            return None
        aggregate = tree.expressions[0]
        if isinstance(aggregate, exp.Alias):
            aggregate = aggregate.this
        if not isinstance(aggregate, exp.Count) or not active_only(aggregate, {"this", "big_int"}):
            return None
        arg = aggregate.this
        if isinstance(arg, exp.Distinct):
            if len(arg.expressions) != 1 or not column(arg.expressions[0], "order_id"):
                return None
        elif not (
            isinstance(arg, exp.Star)
            or column(arg, "order_id")
            or isinstance(arg, exp.Literal)
            and not arg.is_string
            and arg.this == "1"
        ):
            return None

        def terms(node):
            node = unparen(node)
            return terms(node.this) + terms(node.expression) if isinstance(node, exp.And) else [node]

        predicates = terms(tree.args["where"].this)
        if len(predicates) != 3:
            return None
        found = {}
        reverse = {exp.GTE: exp.LTE, exp.LT: exp.GT, exp.LTE: exp.GTE, exp.GT: exp.LT}
        for predicate in predicates:
            op = type(predicate)
            if op not in reverse:
                return None
            left, right = unparen(predicate.this), unparen(predicate.expression)
            if isinstance(left, exp.Literal) and isinstance(right, exp.Column):
                left, right, op = right, left, reverse[op]
            if not isinstance(right, exp.Literal):
                return None
            if (
                column(left, "ordered_at")
                and right.is_string
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", right.this)
            ):
                key = {exp.GTE: "start", exp.LT: "end"}.get(op)
                value = right.this
            elif (
                column(left, "order_total_cents")
                and op == exp.GTE
                and not right.is_string
                and re.fullmatch(r"\d+", right.this)
            ):
                key, value = "threshold", int(right.this)
            else:
                return None
            if key is None or key in found:
                return None
            found[key] = value
        return CountMeaning(**found) if set(found) == {"start", "end", "threshold"} else None
    except (sqlglot.errors.SqlglotError, KeyError, AttributeError, TypeError, ValueError, RecursionError):
        return None


def render_reference(sql, start, end):
    tree = sqlglot.parse_one(sql, read="sqlite")
    values = {"start": start, "end": end}
    return tree.transform(
        lambda node: exp.Literal.string(values[node.this]) if isinstance(node, exp.Placeholder) else node
    ).sql(dialect="sqlite")
