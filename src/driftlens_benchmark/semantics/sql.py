"""Recognize complete relational shapes, extract parameters, and abstain otherwise.

No SQL templates, source labels, alternate definitions or database values are read.
Every accepted SELECT/condition/join must be consumed by a supported grammar rule.
"""

from datetime import date, timedelta
from fractions import Fraction

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify

SLOTS = (
    "grain",
    "aggregation",
    "population",
    "measure",
    "conditions",
    "time_semantics",
    "null_policy",
    "unit",
)
SCHEMA = {
    "orders": {
        k: "TEXT" if k.endswith("id") or k == "ordered_at" else "INT"
        for k in (
            "order_id",
            "customer_id",
            "ordered_at",
            "location_id",
            "subtotal_cents",
            "tax_paid_cents",
            "order_total_cents",
        )
    },
    "order_items": {k: "TEXT" for k in ("order_item_id", "order_id", "product_id")},
    "products": {
        k: "TEXT"
        for k in ("product_id", "product_type", "product_name", "product_description", "product_price_cents")
    },
}


class UnknownSQL(ValueError):
    """A parseable query whose complete semantics are outside this grammar."""


def bare(node):
    """Discard presentation-only nodes, never SQL predicates or casts."""
    while isinstance(node, (exp.Paren, exp.Alias)):
        node = node.this
    return node


def terms(node):
    """AND order is irrelevant, but OR remains an unrecognized whole expression."""
    node = bare(node)
    return terms(node.this) + terms(node.expression) if isinstance(node, exp.And) else [node]


def col(node, alias, name):
    node = bare(node)
    return isinstance(node, exp.Column) and node.table == alias and node.name == name


def number(node):
    node = bare(node)
    if isinstance(node, exp.Neg):
        return -number(node.this)
    if isinstance(node, exp.Literal) and not node.is_string:
        return Fraction(node.this)
    raise UnknownSQL("not_numeric_literal")


def comparison(node):
    """Canonicalize reversed comparisons without changing strictness."""
    node = bare(node)
    if not isinstance(node, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
        raise UnknownSQL("unsupported_predicate")
    return type(node), bare(node.this), bare(node.expression)


def text_value(node):
    node = bare(node)
    if isinstance(node, exp.Literal) and node.is_string:
        return node.this
    raise UnknownSQL("not_text_literal")


def day_value(node, *, full_timestamp=False):
    """Recognize concrete midnight bounds and the explicit prior-week shift."""
    node = bare(node)
    if isinstance(node, exp.Literal) and node.is_string:
        value = node.this
        if (len(value) == 10 and not full_timestamp) or (len(value) == 19 and value[10:] == "T00:00:00"):
            return date.fromisoformat(value[:10])
    if isinstance(node, exp.DPipe) and text_value(node.expression) == "T00:00:00":
        left = bare(node.this)
        if isinstance(left, (exp.Date, exp.Anonymous)) or (
            isinstance(left, exp.Literal) and left.is_string and len(left.this) == 10
        ):
            return day_value(left)
    if full_timestamp:
        # ordered_at stores YYYY-MM-DDTHH:MM:SS. A same-day midnight compares
        # greater than a date-only string, so that cannot prove incompleteness.
        raise UnknownSQL("timestamp_completeness_bound_required")
    if isinstance(node, exp.Date) and node.args.get("zone") and text_value(node.args["zone"]) == "-7 days":
        return day_value(node.this) - timedelta(days=7)
    # SQLGlot represents SQLite DATE(s, '-7 days') as an anonymous function.
    if isinstance(node, exp.Anonymous) and node.name.lower() == "date" and len(node.expressions) == 2:
        if text_value(node.expressions[1]) == "-7 days":
            return day_value(node.expressions[0]) - timedelta(days=7)
    raise UnknownSQL("unsupported_date_bound")


def window_terms(nodes, alias, start, end, *, column="ordered_at"):
    """Consume exactly >= start and < end, leaving business predicates for callers."""
    found, rest = set(), []
    for node in nodes:
        try:
            op, left, right = comparison(node)
            if col(right, alias, column):
                left, right = right, left
                op = {
                    exp.GT: exp.LT,
                    exp.GTE: exp.LTE,
                    exp.LT: exp.GT,
                    exp.LTE: exp.GTE,
                    exp.EQ: exp.EQ,
                    exp.NEQ: exp.NEQ,
                }[op]
            if col(left, alias, column) and (
                (op is exp.GTE and day_value(right) == start) or (op is exp.LT and day_value(right) == end)
            ):
                if op in found:
                    raise UnknownSQL("duplicate_time_predicate")
                found.add(op)
                continue
        except (UnknownSQL, ValueError):
            pass
        rest.append(node)
    if found != {exp.GTE, exp.LT}:
        raise UnknownSQL("incomplete_reporting_window")
    return rest


def select(node):
    """Reject any unconsumed query clause instead of inspecting only familiar tokens."""
    node = bare(node)
    if isinstance(node, exp.Subquery):
        node = node.this
    if not isinstance(node, exp.Select):
        raise UnknownSQL("select_required")
    allowed = {"expressions", "from_", "joins", "where", "group", "having"}
    if any(value and key not in allowed for key, value in node.args.items()):
        raise UnknownSQL("unsupported_select_clause")
    return node


def source(query):
    query = select(query)
    if not query.args.get("from_"):
        raise UnknownSQL("missing_source")
    return query.args["from_"].this


def simple(query, table="orders"):
    """A single table scan with no grouping, joins or other relational operations."""
    query = select(query)
    table_node = source(query)
    if (
        not isinstance(table_node, exp.Table)
        or table_node.name != table
        or table_node.db
        or table_node.catalog
        or query.args.get("joins")
        or query.args.get("group")
        or query.args.get("having")
    ):
        raise UnknownSQL("simple_scan_required")
    return table_node.alias_or_name


def where(query):
    clause = query.args.get("where")
    return terms(clause.this) if clause else []


def projection(query):
    if len(query.expressions) != 1:
        raise UnknownSQL("single_scalar_required")
    return bare(query.expressions[0])


def count_orders(node, alias, *, distinct=False, field="order_id"):
    node = bare(node)
    if not isinstance(node, exp.Count) or node.expressions:
        return False
    inner = node.this
    if distinct:
        return (
            isinstance(inner, exp.Distinct)
            and len(inner.expressions) == 1
            and col(inner.expressions[0], alias, field)
        )
    return isinstance(inner, exp.Star) or col(inner, alias, field)


def money(node, alias):
    """Linear monetary identities rely on the public, validated non-null schema."""
    node = bare(node)
    if isinstance(node, exp.Column) and node.table == alias:
        if node.name == "subtotal_cents":
            return (Fraction(1), Fraction(0))
        if node.name == "tax_paid_cents":
            return (Fraction(0), Fraction(1))
        if node.name == "order_total_cents":
            return (Fraction(1), Fraction(1))
    if isinstance(node, (exp.Add, exp.Sub)):
        a, b = money(node.this, alias), money(node.expression, alias)
        sign = 1 if isinstance(node, exp.Add) else -1
        return tuple(x + sign * y for x, y in zip(a, b, strict=True))
    if isinstance(node, exp.Mul):
        for x, y in ((node.this, node.expression), (node.expression, node.this)):
            try:
                n = number(x)
                return tuple(n * v for v in money(y, alias))
            except UnknownSQL:
                pass
    raise UnknownSQL("unsupported_money_expression")


def meaning(
    *,
    grain="order",
    aggregation="count_distinct",
    population="all",
    measure="order_id",
    conditions="none",
    time_semantics="week",
    null_policy="zero",
    unit="count",
):
    return dict(
        zip(
            SLOTS,
            (grain, aggregation, population, measure, conditions, time_semantics, null_policy, unit),
            strict=True,
        )
    )


def ratio(node):
    """Require floating arithmetic; SQLite integer division is a different meaning."""
    node = bare(node)
    if not isinstance(node, exp.Div):
        raise UnknownSQL("ratio_required")
    numerator, denominator = bare(node.this), bare(node.expression)
    real = False
    if isinstance(denominator, exp.Cast) and denominator.args["to"].sql() in {"FLOAT", "DOUBLE"}:
        denominator = bare(denominator.this)
        real = True
    for side in ("left", "right"):
        value = numerator if side == "left" else denominator
        if isinstance(value, exp.Mul):
            for a, b in ((value.this, value.expression), (value.expression, value.this)):
                try:
                    if number(a) == 1 and "." in a.sql():
                        if side == "left":
                            numerator = bare(b)
                        else:
                            denominator = bare(b)
                        real = True
                        break
                except UnknownSQL:
                    pass
    if not real:
        raise UnknownSQL("integer_division")
    return numerator, denominator


def joins(query):
    """Only the key-preserving orders/items/products join graph is admitted."""
    table_nodes = [source(query)]
    predicates = []
    for join in query.args.get("joins", []):
        if (
            join.args.get("side")
            or join.args.get("kind") not in (None, "", "INNER")
            or not join.args.get("on")
            or join.args.get("using")
        ):
            raise UnknownSQL("unsupported_join")
        table_nodes.append(join.this)
        predicates += terms(join.args["on"])
    aliases = {}
    for table in table_nodes:
        if (
            not isinstance(table, exp.Table)
            or table.db
            or table.catalog
            or table.name not in {"orders", "order_items", "products"}
            or table.name in aliases
        ):
            raise UnknownSQL("unsupported_join_source")
        aliases[table.name] = table.alias_or_name
    if len(set(aliases.values())) != len(aliases):
        raise UnknownSQL("ambiguous_join_alias")
    expected = []
    if "orders" in aliases and "order_items" in aliases:
        expected.append({(aliases["orders"], "order_id"), (aliases["order_items"], "order_id")})
    if "products" in aliases and "order_items" in aliases:
        expected.append({(aliases["products"], "product_id"), (aliases["order_items"], "product_id")})
    actual = []
    for predicate in predicates:
        op, a, b = comparison(predicate)
        if op is not exp.EQ or not isinstance(a, exp.Column) or not isinstance(b, exp.Column):
            raise UnknownSQL("non_key_join")
        actual.append({(a.table, a.name), (b.table, b.name)})
    if len(actual) != len(expected) or any(x not in actual for x in expected):
        raise UnknownSQL("incomplete_join_graph")
    return aliases


def item_predicate(query, outer_alias=None):
    """Consume a correlated item existence test including every correlation/filter."""
    query = select(query)
    if query.args.get("group") or query.args.get("having"):
        raise UnknownSQL("unsupported_item_group")
    # EXISTS projection cannot affect existence, but prohibit nested side operations.
    if len(query.expressions) != 1 or not isinstance(projection(query), (exp.Literal, exp.Star, exp.Column)):
        raise UnknownSQL("unsupported_exists_projection")
    aliases = joins(query)
    if set(aliases) != {"order_items", "products"}:
        raise UnknownSQL("item_sources")
    if outer_alias in aliases.values():
        raise UnknownSQL("shadowed_correlation")
    rest = where(query)
    kind = None
    correlated = outer_alias is None
    unequal = False
    for predicate in rest:
        op, a, b = comparison(predicate)
        if isinstance(a, exp.Literal):
            a, b = b, a
        if col(a, aliases["products"], "product_type") and op in (exp.EQ, exp.NEQ) and kind is None:
            kind = text_value(b)
            unequal = op is exp.NEQ
        elif (
            op is exp.EQ
            and outer_alias is not None
            and not correlated
            and (
                (col(a, aliases["order_items"], "order_id") and col(b, outer_alias, "order_id"))
                or (col(b, aliases["order_items"], "order_id") and col(a, outer_alias, "order_id"))
            )
        ):
            correlated = True
        else:
            raise UnknownSQL("unconsumed_item_predicate")
    if kind is None or not correlated:
        raise UnknownSQL("incomplete_item_predicate")
    return kind, unequal, aliases


def threshold(node, aggregate):
    """Extract an arbitrary integer minimum; do not enumerate known drift thresholds."""
    op, a, b = comparison(node)
    if aggregate(b):
        a, b = b, a
        op = {exp.LT: exp.GT, exp.LTE: exp.GTE}.get(op)
    if not aggregate(a) or op not in (exp.GT, exp.GTE):
        raise UnknownSQL("unsupported_count_threshold")
    n = number(b)
    if n.denominator != 1 or n < 0:
        raise UnknownSQL("unsupported_count_threshold")
    return int(n) + (op is exp.GT)


def extract(sql, concept_id, window):
    """Return a complete meaning or None; never derive meaning from reported numbers."""
    try:
        statements = sqlglot.parse(sql, read="sqlite")
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            return None
        root = qualify(
            statements[0], dialect="sqlite", schema=SCHEMA, quote_identifiers=False, identify=False
        )
        # Clauses attached below SELECT (for example TABLESAMPLE or GROUP ROLLUP)
        # also affect meaning. Reject modifiers that the relational rules do not
        # consume, including SQLite's scalar multi-argument MIN.
        for node in root.walk():
            allowed = {
                exp.Table: {"this", "db", "catalog", "alias"},
                exp.Group: {"expressions"},
                exp.Join: {"this", "on", "side", "kind", "using"},
                exp.From: {"this"},
                exp.Subquery: {"this", "alias"},
                exp.Min: {"this"},
            }.get(type(node))
            if allowed is not None and any(value and key not in allowed for key, value in node.args.items()):
                raise UnknownSQL("unsupported_relational_modifier")
        ctes = {}
        with_clause = root.args.get("with_")
        if with_clause:
            if with_clause.args.get("recursive"):
                return None
            for cte in with_clause.expressions:
                expanded = cte.this.copy()
                for table in list(expanded.find_all(exp.Table)):
                    if table.name in ctes:
                        table.replace(
                            exp.Subquery(this=ctes[table.name].copy(), alias=table.args.get("alias"))
                        )
                ctes[cte.alias_or_name] = expanded
            root.set("with_", None)
            for table in list(root.find_all(exp.Table)):
                if table.name in ctes:
                    table.replace(exp.Subquery(this=ctes[table.name].copy(), alias=table.args.get("alias")))
        query = select(root)
        start, end = (date.fromisoformat(window[k][:10]) for k in ("start", "end"))
        if concept_id in {"sa_order_value_avg", "sa_tax_rate_avg"}:
            alias = simple(query)
            if window_terms(where(query), alias, start, end):
                raise UnknownSQL("extra_filter")
            value = projection(query)
            if concept_id == "sa_order_value_avg":
                if isinstance(value, exp.Avg):
                    vector = money(value.this, alias)
                else:
                    top, bottom = ratio(value)
                    if not isinstance(top, exp.Sum) or not count_orders(bottom, alias):
                        raise UnknownSQL("average_required")
                    vector = money(top.this, alias)
                measure = {
                    (1, 0): "subtotal_cents",
                    (1, 1): "order_total_cents",
                    (0, 1): "tax_paid_cents",
                }.get(vector)
                if measure is None:
                    raise UnknownSQL("unknown_measure")
                return meaning(
                    aggregation="average", measure=measure, null_policy="empty_is_null", unit="cents"
                )
            top, bottom = ratio(value)
            if not isinstance(top, exp.Sum) or not isinstance(bottom, exp.Sum):
                raise UnknownSQL("weighted_ratio_required")
            if money(top.this, alias) != (0, 1) or money(bottom.this, alias) != (1, 0):
                raise UnknownSQL("unknown_ratio_basis")
            return meaning(
                aggregation="ratio_of_sums",
                measure="tax_paid_cents/subtotal_cents",
                null_policy="zero_denominator",
                unit="ratio",
            )
        if concept_id in {"sa_food_orders", "sa_drink_orders"}:
            return food(query, start, end)
        if concept_id == "sa_customers_active":
            return active(query, start, end)
        if concept_id == "sa_customers_new":
            return new_customers(query, start, end)
        if concept_id == "sa_revenue_growth_wow":
            return growth(query, start, end)
    except (
        UnknownSQL,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RecursionError,
        OverflowError,
        sqlglot.errors.SqlglotError,
    ):
        return None
    return None


def food(query, start, end):
    """Orders with matching items: EXISTS, grouped joins, or distinct item order IDs."""
    first = source(query)
    value = projection(query)
    if isinstance(first, exp.Table) and first.name == "orders" and not query.args.get("joins"):
        alias = simple(query)
        if not count_orders(value, alias):
            raise UnknownSQL("order_count_required")
        rest = window_terms(where(query), alias, start, end)
        included = excluded = None
        for predicate in rest:
            neg = isinstance(predicate, exp.Not)
            node = bare(predicate.this) if neg else predicate
            if not isinstance(node, exp.Exists):
                raise UnknownSQL("existence_required")
            kind, unequal, _ = item_predicate(node.this, alias)
            if neg and unequal and excluded is None:
                excluded = kind
            elif not neg and not unequal and included is None:
                included = kind
            else:
                raise UnknownSQL("unsupported_item_logic")
        if included is None or (excluded is not None and excluded != included):
            raise UnknownSQL("incomplete_item_logic")
        return meaning(population=("only:" if excluded else "contains:") + included)
    if isinstance(first, exp.Subquery):
        if (
            where(query)
            or query.args.get("joins")
            or query.args.get("group")
            or query.args.get("having")
            or not count_orders(value, first.alias_or_name)
        ):
            raise UnknownSQL("outer_order_count_required")
        inner = select(first.this)
        aliases = joins(inner)
        if set(aliases) != {"orders", "order_items", "products"}:
            raise UnknownSQL("three_way_join_required")
        o, p = aliases["orders"], aliases["products"]
        if (
            window_terms(where(inner), o, start, end)
            or len(inner.expressions) != 1
            or not col(projection(inner), o, "order_id")
        ):
            raise UnknownSQL("grouped_order_required")
        if (
            not inner.args.get("group")
            or len(inner.args["group"].expressions) != 1
            or not col(inner.args["group"].expressions[0], o, "order_id")
        ):
            raise UnknownSQL("order_group_required")
        included = excluded = None
        if not inner.args.get("having"):
            raise UnknownSQL("item_having_required")
        for predicate in terms(inner.args["having"].this):
            op, a, b = comparison(predicate)
            if not isinstance(a, exp.Sum):
                raise UnknownSQL("boolean_sum_required")
            inner_op, c, d = comparison(a.this)
            if isinstance(c, exp.Literal):
                c, d = d, c
            if not col(c, p, "product_type"):
                raise UnknownSQL("product_type_required")
            kind = text_value(d)
            if (
                inner_op is exp.EQ
                and ((op is exp.GT and number(b) == 0) or (op is exp.GTE and number(b) == 1))
                and included is None
            ):
                included = kind
            elif inner_op is exp.NEQ and op is exp.EQ and number(b) == 0 and excluded is None:
                excluded = kind
            else:
                raise UnknownSQL("unknown_having")
        if included is None or (excluded is not None and excluded != included):
            raise UnknownSQL("incomplete_having")
        return meaning(population=("only:" if excluded else "contains:") + included)
    aliases = joins(query)
    if (
        set(aliases) != {"orders", "order_items", "products"}
        or query.args.get("group")
        or query.args.get("having")
    ):
        raise UnknownSQL("distinct_order_join_required")
    o, i, p = (aliases[t] for t in ("orders", "order_items", "products"))
    if not (count_orders(value, i, distinct=True) or count_orders(value, o, distinct=True)):
        raise UnknownSQL("distinct_order_required")
    included = excluded = None
    for node in window_terms(where(query), o, start, end):
        if isinstance(node, exp.Not) and isinstance(bare(node.this), exp.In) and excluded is None:
            test = bare(node.this)
            if not col(test.this, i, "order_id"):
                raise UnknownSQL("wrong_excluded_id")
            kind, unequal, inner_alias = item_predicate(test.args["query"])
            iq = select(test.args["query"])
            if not unequal or not col(projection(iq), inner_alias["order_items"], "order_id"):
                raise UnknownSQL("non_null_item_id_required")
            excluded = kind
        else:
            op, a, b = comparison(node)
            if isinstance(a, exp.Literal):
                a, b = b, a
            if op is not exp.EQ or not col(a, p, "product_type") or included is not None:
                raise UnknownSQL("extra_item_filter")
            included = text_value(b)
    if included is None or (excluded is not None and excluded != included):
        raise UnknownSQL("incomplete_distinct_items")
    return meaning(population=("only:" if excluded else "contains:") + included)


def active(query, start, end):
    """Count customer groups satisfying an arbitrary weekly order-count minimum."""
    first = source(query)
    value = projection(query)
    null_policy = "zero"
    if isinstance(first, exp.Table):
        alias = simple(query)
        if not count_orders(value, alias, distinct=True, field="customer_id"):
            raise UnknownSQL("customer_count_required")
        rest = window_terms(where(query), alias, start, end)
        if not rest:
            minimum = 1
        elif len(rest) == 1 and isinstance(rest[0], exp.In) and col(rest[0].this, alias, "customer_id"):
            inner = select(rest[0].args["query"])
            table = source(inner)
            if not isinstance(table, exp.Table) or table.name != "orders" or inner.args.get("joins"):
                raise UnknownSQL("weekly_customers_required")
            ia = table.alias_or_name
            if (
                window_terms(where(inner), ia, start, end)
                or len(inner.expressions) != 1
                or not col(projection(inner), ia, "customer_id")
            ):
                raise UnknownSQL("weekly_customers_required")
            group = inner.args.get("group")
            if (
                not group
                or len(group.expressions) != 1
                or not col(group.expressions[0], ia, "customer_id")
                or not inner.args.get("having")
            ):
                raise UnknownSQL("weekly_customer_group_required")
            minimum = threshold(inner.args["having"].this, lambda x: count_orders(x, ia))
        else:
            raise UnknownSQL("extra_customer_filter")
    elif isinstance(first, exp.Subquery):
        if query.args.get("joins") or query.args.get("group") or query.args.get("having"):
            raise UnknownSQL("customer_count_outer")
        inner = select(first.this)
        table = source(inner)
        if not isinstance(table, exp.Table) or table.name != "orders" or inner.args.get("joins"):
            raise UnknownSQL("customer_orders_required")
        alias = table.alias_or_name
        if window_terms(where(inner), alias, start, end):
            raise UnknownSQL("extra_weekly_filter")
        group = inner.args.get("group")
        if not group or len(group.expressions) != 1 or not col(group.expressions[0], alias, "customer_id"):
            raise UnknownSQL("customer_group_required")
        count_alias = None
        customer_seen = False
        for item in inner.expressions:
            if col(bare(item), alias, "customer_id") and not customer_seen:
                customer_seen = True
            elif count_orders(bare(item), alias) and count_alias is None:
                count_alias = item.alias_or_name
            else:
                raise UnknownSQL("unconsumed_customer_projection")
        if not customer_seen:
            raise UnknownSQL("customer_projection_missing")
        h = inner.args.get("having")
        outer = where(query)
        if h and not outer and count_orders(value, first.alias_or_name):
            minimum = threshold(h.this, lambda x: count_orders(x, alias))
        elif not h and len(outer) == 1 and count_alias and count_orders(value, first.alias_or_name):
            minimum = threshold(outer[0], lambda x: col(x, first.alias_or_name, count_alias))
        elif not h and not outer and count_alias and isinstance(value, exp.Sum):
            minimum = threshold(value.this, lambda x: col(x, first.alias_or_name, count_alias))
            null_policy = "empty_is_null"
        else:
            raise UnknownSQL("unconsumed_customer_threshold")
    else:
        raise UnknownSQL("unsupported_customer_source")
    return meaning(
        grain="customer",
        measure="customer_id",
        conditions=f"min_orders:{max(1, minimum)}",
        null_policy=null_policy,
    )


def new_customers(query, start, end):
    """Require a brand-wide first order, with no location grouping or time prefilter."""
    first = source(query)
    value = projection(query)
    if isinstance(first, exp.Subquery):
        if (
            query.args.get("joins")
            or query.args.get("group")
            or query.args.get("having")
            or not count_orders(value, first.alias_or_name)
        ):
            raise UnknownSQL("first_customer_count_required")
        inner = select(first.this)
        table = source(inner)
        if (
            not isinstance(table, exp.Table)
            or table.name != "orders"
            or inner.args.get("joins")
            or where(inner)
        ):
            raise UnknownSQL("full_history_required")
        alias = table.alias_or_name
        group = inner.args.get("group")
        if not group or len(group.expressions) != 1 or not col(group.expressions[0], alias, "customer_id"):
            raise UnknownSQL("brand_customer_group_required")
        first_alias = None
        for item in inner.expressions:
            v = bare(item)
            if col(v, alias, "customer_id"):
                continue
            if isinstance(v, exp.Min) and col(v.this, alias, "ordered_at") and first_alias is None:
                first_alias = item.alias_or_name
            else:
                raise UnknownSQL("unsupported_first_projection")
        having = inner.args.get("having")
        if having and not where(query) and first_alias is None:
            predicates = []
            for node in terms(having.this):
                _, left, right = comparison(node)
                # SQLite permits a bare grouped column in HAVING, but that is an
                # arbitrary row's date, not the customer's first-ever order.
                if not any(
                    isinstance(value, exp.Min) and col(value.this, alias, "ordered_at")
                    for value in (left, right)
                ):
                    raise UnknownSQL("first_order_aggregate_required")
                n = node.copy()
                for aggregate in list(n.find_all(exp.Min)):
                    if not col(aggregate.this, alias, "ordered_at"):
                        raise UnknownSQL("wrong_first_measure")
                    aggregate.replace(exp.column("ordered_at", table=alias))
                predicates.append(n)
            if window_terms(predicates, alias, start, end):
                raise UnknownSQL("extra_first_filter")
        elif first_alias and not having:
            if window_terms(where(query), first.alias_or_name, start, end, column=first_alias):
                raise UnknownSQL("extra_first_filter")
        else:
            raise UnknownSQL("first_window_missing")
    else:
        alias = simple(query)
        if not count_orders(value, alias, distinct=True, field="customer_id"):
            raise UnknownSQL("new_distinct_required")
        rest = window_terms(where(query), alias, start, end)
        if (
            len(rest) != 1
            or not isinstance(rest[0], exp.Not)
            or not isinstance(bare(rest[0].this), exp.Exists)
        ):
            raise UnknownSQL("prior_exclusion_required")
        inner = select(bare(rest[0].this).this)
        previous = simple(inner)
        if previous == alias:
            raise UnknownSQL("shadowed_customer_correlation")
        if len(inner.expressions) != 1 or not isinstance(projection(inner), exp.Literal):
            raise UnknownSQL("exists_literal_required")
        matched = set()
        for node in where(inner):
            op, a, b = comparison(node)
            if op is exp.EQ and (
                (col(a, previous, "customer_id") and col(b, alias, "customer_id"))
                or (col(b, previous, "customer_id") and col(a, alias, "customer_id"))
            ):
                matched.add("customer")
            elif op is exp.LT and col(a, previous, "ordered_at") and day_value(b) == start:
                matched.add("past")
            else:
                raise UnknownSQL("extra_prior_filter")
        if matched != {"customer", "past"} or len(where(inner)) != 2:
            raise UnknownSQL("incomplete_prior_exclusion")
    return meaning(grain="customer", measure="customer_id", time_semantics="first_ever_in_week")


def growth(query, start, end):
    """Follow aggregate lineage through CTEs/subqueries to current/prior totals."""
    prior = start - timedelta(days=7)
    empty_current_zero = False
    if len(query.expressions) != 1:
        raise UnknownSQL("growth_single_scalar_required")

    def query_values(q):
        """Lower a complete ungrouped scalar relation; no filters are discarded."""
        q = select(q)
        if len({item.alias_or_name for item in q.expressions}) != len(q.expressions):
            raise UnknownSQL("growth_ambiguous_projection")
        if q.args.get("joins") or q.args.get("group") or q.args.get("having"):
            raise UnknownSQL("growth_ungrouped_required")
        env = {}
        alias = None
        domain = None
        if q.args.get("from_"):
            src = source(q)
            if isinstance(src, exp.Table) and src.name == "orders" and not src.db and not src.catalog:
                alias = src.alias_or_name
                if not where(q):
                    domain = (None, None)
                else:
                    for candidate in ((start, end), (prior, start), (prior, end)):
                        try:
                            if not window_terms(where(q), alias, *candidate):
                                domain = candidate
                                break
                        except UnknownSQL:
                            pass
                    if domain is None:
                        raise UnknownSQL("growth_extra_filter")
            elif isinstance(src, exp.Subquery) and not where(q):
                values = query_values(src.this)
                env = {(src.alias_or_name, k): v for k, v in values.items()}
            else:
                raise UnknownSQL("growth_source")
        elif where(q):
            raise UnknownSQL("growth_scalar_filter")
        return {item.alias_or_name: lower(bare(item), env, alias, domain) for item in q.expressions}

    def row_bucket(node, alias, domain):
        """A CASE contribution must cover exactly one requested week's subtotal."""
        nonlocal empty_current_zero
        node = bare(node)
        if not isinstance(node, exp.Case) or node.this is not None or len(node.args.get("ifs", [])) != 1:
            raise UnknownSQL("growth_case_required")
        branch = node.args["ifs"][0]
        if money(branch.args["true"], alias) != (1, 0):
            raise UnknownSQL("growth_measure")
        default = node.args.get("default")
        if default is not None and not isinstance(default, exp.Null) and number(default) != 0:
            raise UnknownSQL("growth_case_default")
        low, high = domain
        seen = set()
        for predicate in terms(branch.this):
            op, a, b = comparison(predicate)
            if not col(a, alias, "ordered_at"):
                raise UnknownSQL("growth_case_column")
            bound = day_value(b)
            if op is exp.GTE and op not in seen:
                low = max(low, bound) if low is not None else bound
            elif op is exp.LT and op not in seen:
                high = min(high, bound) if high is not None else bound
            else:
                raise UnknownSQL("growth_case_predicate")
            seen.add(op)
        bucket = {(start, end): "cur", (prior, start): "prev"}.get((low, high))
        if bucket is None:
            raise UnknownSQL("growth_case_window")
        if bucket == "cur" and default is not None and not isinstance(default, exp.Null):
            empty_current_zero = True
        return ("row", bucket)

    def lower(node, env, alias, domain):
        """Interpret only scalar operations required for complete growth lineage."""
        node = bare(node)
        if isinstance(node, exp.Column) and (node.table, node.name) in env:
            return env[node.table, node.name]
        if isinstance(node, exp.Subquery):
            values = query_values(node.this)
            if len(values) != 1:
                raise UnknownSQL("growth_scalar_subquery")
            return next(iter(values.values()))
        if isinstance(node, exp.Literal) and not node.is_string:
            return number(node)
        if isinstance(node, exp.Null):
            return None
        if isinstance(node, (exp.Date, exp.Anonymous)) or (isinstance(node, exp.Literal) and node.is_string):
            return day_value(node)
        if isinstance(node, exp.Min):
            if alias and col(node.this, alias, "ordered_at") and domain == (None, None):
                return "first"
            if lower(node.this, env, alias, domain) == "first":
                return "first"
            raise UnknownSQL("growth_first_history")
        if isinstance(node, exp.Sum):
            if alias:
                try:
                    if money(node.this, alias) == (1, 0):
                        return {(start, end): "cur", (prior, start): "prev"}[domain]
                except (UnknownSQL, KeyError):
                    pass
                return row_bucket(node.this, alias, domain)[1]
            value = lower(node.this, env, alias, domain)
            if isinstance(value, tuple) and value[0] == "row":
                return value[1]
            raise UnknownSQL("growth_double_aggregate")
        if isinstance(node, exp.Case):
            if alias:
                return row_bucket(node, alias, domain)
            if node.this is not None or len(node.args.get("ifs", [])) != 1:
                raise UnknownSQL("growth_guard_required")
            branch = node.args["ifs"][0]
            op, a, b = comparison(branch.this)
            if (
                op is not exp.GT
                or lower(a, env, alias, domain) != "first"
                or day_value(b, full_timestamp=True) != prior
                or not isinstance(branch.args["true"], exp.Null)
            ):
                raise UnknownSQL("growth_completeness_guard")
            formula = lower(node.args["default"], env, alias, domain)
            if formula not in {
                ("div", ("sub", "cur", "prev"), "prev"),
                ("sub", ("div", "cur", "prev"), Fraction(1)),
            }:
                raise UnknownSQL("growth_formula")
            return "growth"
        if isinstance(node, exp.Div):
            # Promotion must happen before this division. Multiplying its result
            # by 1.0 or subtracting 1.0 afterwards cannot undo integer truncation.
            top, bottom = ratio(node)
            return ("div", lower(top, env, alias, domain), lower(bottom, env, alias, domain))
        if isinstance(node, (exp.Sub, exp.Add, exp.Mul)):
            a, b = lower(node.this, env, alias, domain), lower(node.expression, env, alias, domain)
            if isinstance(node, exp.Mul) and a == 1:
                return b
            if isinstance(node, exp.Mul) and b == 1:
                return a
            return ({exp.Sub: "sub", exp.Add: "add", exp.Mul: "mul"}[type(node)], a, b)
        raise UnknownSQL("growth_unknown_expression")

    values = query_values(query)
    if len(values) != 1 or next(iter(values.values())) != "growth":
        raise UnknownSQL("growth_result_required")
    return meaning(
        grain="week",
        aggregation="relative_change",
        measure="subtotal_cents",
        time_semantics="week_over_week",
        null_policy="incomplete_prior_week_or_zero_current_empty_as_zero"
        if empty_current_zero
        else "incomplete_prior_week_or_zero",
        unit="ratio",
    )
