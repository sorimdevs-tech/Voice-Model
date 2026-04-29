"""
VOXA Backend — Automotive Agent (Layer 6: AI Agent Layer)
Orchestrates: Intent Detection → Data Retrieval → LLM Response Generation

This is the brain of the assistant. It:
1. Detects user intent from the query
2. Pulls relevant data from DuckDB
3. Builds context for the LLM
4. Generates rich markdown responses with tables, summaries, and insights
"""

import logging
import re
from typing import AsyncGenerator, Dict, Any
from datetime import datetime, date, timedelta

from services.data_service import get_data_service
from services import llm_service

logger = logging.getLogger("voxa.agent")

# ── Intent Categories ──
INTENTS = {
    "weekly_schedule": {
        "keywords": ["schedule", "this week", "weekly", "week's schedule", "production schedule",
                      "what's happening", "planned", "upcoming"],
        "description": "Plant schedule for the current/upcoming week",
    },
    "quarter_comparison": {
        "keywords": ["quarter", "quarterly", "q1", "q2", "q3", "q4", "compared to last quarter",
                      "qoq", "quarter over quarter", "this quarter", "last quarter", "previous quarter"],
        "description": "Quarter-over-quarter performance comparison",
    },
    "week_broadcast": {
        "keywords": ["broadcast", "next week", "previous week", "week over week", "wow",
                      "compared to last week", "week comparison", "weekly comparison", "weekly trend"],
        "description": "Week-over-week data comparison and broadcast",
    },
    "sales_by_model": {
        "keywords": ["model", "vehicle", "car", "top selling", "best seller", "worst",
                      "which model", "suv", "sedan", "hatchback", "variant"],
        "description": "Vehicle model-specific sales analysis",
    },
    "sales_by_plant": {
        "keywords": ["plant", "factory", "location", "facility", "which plant",
                      "plant performance", "production", "output", "capacity"],
        "description": "Plant-level production and sales data",
    },
    "sales_by_region": {
        "keywords": ["region", "country", "india", "usa", "europe", "city", "geography",
                      "where", "market", "territory"],
        "description": "Regional sales breakdown",
    },
    "revenue_analysis": {
        "keywords": ["revenue", "income", "profit", "earnings", "money", "financial",
                      "total sales", "turnover", "growth"],
        "description": "Revenue and financial analysis",
    },
    "trend_analysis": {
        "keywords": ["trend", "over time", "growth", "decline", "pattern", "forecast",
                      "prediction", "projection", "historically"],
        "description": "Trend analysis and patterns",
    },
    "comparison": {
        "keywords": ["compare", "versus", "vs", "difference", "better", "worse",
                      "against", "benchmark"],
        "description": "Comparative analysis between entities",
    },
    "general": {
        "keywords": [],
        "description": "General automotive/plant question",
    },
}

METRIC_SYNONYMS = {
    "units": "units",
    "unit": "units",
    "production": "units",
    "output": "units",
    "revenue": "revenue",
    "sales": "revenue",
    "forecast_units": "forecast_units",
    "forecast revenue": "forecast_revenue",
    "forecast_revenue": "forecast_revenue",
    "affected_units": "affected_units",
    "alerts": "alerts",
    "issues": "alerts",
    "quality issues": "alerts",
}

AGGREGATION_SYNONYMS = {
    "average": "avg",
    "avg": "avg",
    "mean": "avg",
    "total": "sum",
    "sum": "sum",
    "count": "count",
    "number": "count",
    "maximum": "max",
    "max": "max",
    "minimum": "min",
    "min": "min",
    "highest": "max",
    "lowest": "min",
    "trend": "trend",
    "change": "change",
    "difference": "change",
}

GROUP_BY_SYNONYMS = {
    "plant": "plant",
    "department": "department",
    "model": "model",
    "issue type": "issue_type",
    "status": "status",
    "week": "week",
    "quarter": "quarter",
    "month": "month",
    "date": "date",
}

TIME_KEYWORDS = {
    "this month": "this_month",
    "last month": "last_month",
    "this quarter": "this_quarter",
    "last quarter": "last_quarter",
    "this week": "this_week",
    "last week": "last_week",
    "this year": "this_year",
    "last year": "last_year",
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def detect_intent(query: str) -> str:
    """
    Simple keyword-based intent detection.
    Returns the best matching intent category.
    """
    query_lower = query.lower()
    scores = {}

    for intent_name, intent_data in INTENTS.items():
        if intent_name == "general":
            continue
        score = sum(1 for kw in intent_data["keywords"] if kw in query_lower)
        if score > 0:
            scores[intent_name] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)


def _normalize_text(query: str) -> str:
    return re.sub(r"[^a-z0-9\s-]", " ", query.lower())


def _parse_time_range(query: str) -> dict | None:
    query_lower = query.lower()
    now = datetime.now()

    for phrase, token in TIME_KEYWORDS.items():
        if phrase in query_lower:
            if token == "this_month":
                return {"type": "month", "month": now.month, "year": now.year, "requested": "this month"}
            if token == "last_month":
                last_month = (now.replace(day=1) - timedelta(days=1))
                return {"type": "month", "month": last_month.month, "year": last_month.year, "requested": "last month"}
            if token == "this_quarter":
                quarter = (now.month - 1) // 3 + 1
                return {"type": "quarter", "quarter": quarter, "year": now.year, "requested": "this quarter"}
            if token == "last_quarter":
                quarter = (now.month - 1) // 3
                year = now.year
                if quarter == 0:
                    quarter = 4
                    year -= 1
                return {"type": "quarter", "quarter": quarter, "year": year, "requested": "last quarter"}
            if token == "this_week":
                return {"type": "week", "week": now.isocalendar()[1], "year": now.year, "requested": "this week"}
            if token == "last_week":
                last_week_date = now - timedelta(days=7)
                return {"type": "week", "week": last_week_date.isocalendar()[1], "year": last_week_date.year, "requested": "last week"}
            if token == "this_year":
                return {"type": "year", "year": now.year, "requested": "this year"}
            if token == "last_year":
                return {"type": "year", "year": now.year - 1, "requested": "last year"}

    month_year_match = re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})\b", query_lower)
    if month_year_match:
        month_name, year = month_year_match.groups()
        return {"type": "month", "month": MONTHS[month_name], "year": int(year), "requested": f"{month_name.title()} {year}"}

    quarter_match = re.search(r"\bq([1-4])(?:\s+(\d{4}))?\b", query_lower)
    if quarter_match:
        quarter = int(quarter_match.group(1))
        year = int(quarter_match.group(2) or now.year)
        return {"type": "quarter", "quarter": quarter, "year": year, "requested": f"Q{quarter} {year}"}

    year_match = re.search(r"\b(20\d{2})\b", query_lower)
    if year_match:
        year = int(year_match.group(1))
        return {"type": "year", "year": year, "requested": str(year)}

    return None


def _parse_filters(query: str, table_name: str) -> dict:
    query_lower = query.lower()
    filters = {}
    data_svc = get_data_service()
    candidate_columns = ["plant", "department", "model", "issue_type", "status"]

    for column in candidate_columns:
        try:
            values = data_svc.get_column_values(table_name, column)
        except Exception:
            continue
        for value in values:
            if value is None:
                continue
            value_text = str(value).lower()
            if value_text and value_text in query_lower:
                filters[column] = value
                break
    return filters


def _choose_time_clause(table_name: str, time_range: dict | None) -> tuple[str | None, dict]:
    if time_range is None:
        return None, {"used": None, "requested": None}

    expr = None
    requested = time_range.get("requested")
    if time_range["type"] == "month":
        expr = f"EXTRACT(month FROM CAST(date AS DATE)) = {time_range['month']} AND EXTRACT(year FROM CAST(date AS DATE)) = {time_range['year']}"
    elif time_range["type"] == "quarter":
        expr = f"LOWER(quarter) = 'q{time_range['quarter']}' AND EXTRACT(year FROM CAST(date AS DATE)) = {time_range['year']}"
    elif time_range["type"] == "week":
        expr = f"LOWER(week) = 'w{time_range['week']:02d}' AND EXTRACT(year FROM CAST(date AS DATE)) = {time_range['year']}"
    elif time_range["type"] == "year":
        expr = f"EXTRACT(year FROM CAST(date AS DATE)) = {time_range['year']}"
    else:
        return None, {"used": requested, "requested": requested}

    data_svc = get_data_service()
    count_sql = f"SELECT COUNT(*) AS cnt FROM {table_name} WHERE {expr}"
    row_count = data_svc.execute_query(count_sql).iloc[0, 0]
    if row_count > 0:
        return expr, {"used": requested, "requested": requested, "available_rows": int(row_count)}

    latest_sql = f"SELECT MAX(CAST(date AS DATE)) AS latest_date FROM {table_name}"
    latest_row = data_svc.execute_query(latest_sql)
    if latest_row.empty or latest_row.iloc[0, 0] is None:
        return expr, {"used": requested, "requested": requested, "available_rows": 0}

    latest_date = latest_row.iloc[0, 0]
    used_month = int(latest_date.strftime("%m"))
    used_year = int(latest_date.strftime("%Y"))
    used = latest_date.strftime("%B %Y")
    fallback_expr = f"EXTRACT(month FROM CAST(date AS DATE)) = {used_month} AND EXTRACT(year FROM CAST(date AS DATE)) = {used_year}"
    return fallback_expr, {"requested": requested, "used": used, "available_rows": int(data_svc.execute_query(f"SELECT COUNT(*) AS cnt FROM {table_name} WHERE {fallback_expr}").iloc[0, 0])}


def _choose_table(metric: str) -> str:
    if metric in {"forecast_units", "forecast_revenue"}:
        return "forecast_data"
    if metric in {"alerts", "affected_units"}:
        return "alerts_quality"
    return "production_data"


def _parse_structured_intent(query: str) -> dict | None:
    query_lower = query.lower()
    raw = _normalize_text(query_lower)
    metric = None
    aggregation = None
    group_by = None

    for phrase, field in METRIC_SYNONYMS.items():
        if phrase in query_lower:
            metric = field
            break

    for phrase, agg in AGGREGATION_SYNONYMS.items():
        if phrase in query_lower:
            aggregation = agg
            break

    for phrase, group in GROUP_BY_SYNONYMS.items():
        if phrase in query_lower:
            group_by = group
            break

    if metric is None:
        if any(token in query_lower for token in ["alert", "issue"]):
            metric = "alerts"
        elif any(token in query_lower for token in ["revenue", "sales"]):
            metric = "revenue"
        elif any(token in query_lower for token in ["unit", "production", "output"]):
            metric = "units"

    if aggregation is None:
        if "average" in query_lower or "avg" in query_lower or "mean" in query_lower:
            aggregation = "avg"
        elif "total" in query_lower or "sum" in query_lower or "overall" in query_lower:
            aggregation = "sum"
        elif "count" in query_lower or "how many" in query_lower:
            aggregation = "count"
        elif "maximum" in query_lower or "highest" in query_lower or "biggest" in query_lower:
            aggregation = "max"
        elif "minimum" in query_lower or "lowest" in query_lower or "smallest" in query_lower:
            aggregation = "min"

    if metric is None or aggregation is None:
        return None

    table_name = _choose_table(metric)
    filters = _parse_filters(query_lower, table_name)
    time_range = _parse_time_range(query)
    return {
        "metric": metric,
        "aggregation": aggregation,
        "group_by": group_by,
        "filters": filters,
        "time_range": time_range,
        "table_name": table_name,
    }


def _build_sql_for_intent(intent: dict) -> tuple[str, dict] | None:
    metric = intent["metric"]
    aggregation = intent["aggregation"]
    group_by = intent["group_by"]
    filters = intent["filters"]
    table_name = intent["table_name"]

    select_clauses = []
    group_clause = ""
    where_clauses = []

    if metric == "alerts":
        metric_expr = "COUNT(*)"
        col_label = "issue_count"
    elif metric == "affected_units":
        metric_expr = "SUM(affected_units)"
        col_label = "affected_units"
    else:
        metric_expr = metric
        col_label = metric

    if aggregation == "avg" and metric not in {"alerts", "count"}:
        select_clauses.append(f"SUM({metric_expr}) AS total_{col_label}")
        select_clauses.append("COUNT(DISTINCT CAST(date AS DATE)) AS record_days")
        select_clauses.append(f"ROUND(SUM({metric_expr}) / NULLIF(COUNT(DISTINCT CAST(date AS DATE)), 0), 2) AS average_{col_label}")
    elif aggregation == "sum":
        select_clauses.append(f"SUM({metric_expr}) AS total_{col_label}")
    elif aggregation == "count" or metric == "alerts":
        select_clauses.append(f"COUNT(*) AS total_{col_label}")
    elif aggregation == "max":
        select_clauses.append(f"MAX({metric_expr}) AS max_{col_label}")
    elif aggregation == "min":
        select_clauses.append(f"MIN({metric_expr}) AS min_{col_label}")
    else:
        select_clauses.append(f"SUM({metric_expr}) AS total_{col_label}")

    if group_by and group_by != "date":
        select_clauses.insert(0, group_by)
        group_clause = f"GROUP BY {group_by} ORDER BY {group_by}"

    if filters:
        for key, value in filters.items():
            safe = str(value).replace("'", "''")
            where_clauses.append(f"LOWER({key}) = LOWER('{safe}')")

    time_expr, time_meta = _choose_time_clause(table_name, intent["time_range"])
    if time_expr:
        where_clauses.append(time_expr)

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    sql = f"SELECT {', '.join(select_clauses)} FROM {table_name} {where_clause} {group_clause}".strip()
    return sql, time_meta


def _build_result_context(df, sql: str, time_meta: dict, intent: dict) -> str:
    rows = []
    if df is not None and not df.empty:
        rows.append(f"SQL: {sql}")
        rows.append(f"Requested time: {time_meta.get('requested') or 'N/A'}")
        rows.append(f"Used time: {time_meta.get('used') or time_meta.get('requested') or 'N/A'}")
        rows.append(f"Available rows in selected range: {time_meta.get('available_rows', 'N/A')}")
        rows.append("")
        rows.append("### Results")
        rows.append(df.to_markdown(index=False))
    else:
        rows.append(f"SQL: {sql}")
        rows.append("### Results")
        rows.append("No data found for the selected criteria.")
    return "\n".join(rows)


def _execute_structured_intent(intent: dict) -> tuple[str, dict] | None:
    data_svc = get_data_service()
    sql, time_meta = _build_sql_for_intent(intent)
    df = data_svc.execute_query(sql)
    if df.empty and time_meta.get("available_rows", 0) == 0:
        return None
    return _build_result_context(df, sql, time_meta, intent), {"intent": intent, "results": df, "time_meta": time_meta}


def detect_structured_query(query: str) -> str | None:
    """Detect whether the question can be answered with a structured data query."""
    query_lower = query.lower()

    if "plant" in query_lower and any(k in query_lower for k in ["highest", "most", "max", "top"]) and any(k in query_lower for k in ["issue", "issues", "alert", "alerts"]):
        return "highest_issues_by_plant"

    return None


def execute_structured_query(query: str) -> str | None:
    """Run a safe structured query for supported data-first requests."""
    intent_key = detect_structured_query(query)
    if intent_key == "highest_issues_by_plant":
        data_svc = get_data_service()
        sql = """
            SELECT plant,
                   SUM(CASE WHEN LOWER(status) = 'active' THEN 1 ELSE 0 END) AS active_issues,
                   COUNT(*) AS total_issues
            FROM alerts_quality
            GROUP BY plant
            ORDER BY active_issues DESC, total_issues DESC
        """
        df = data_svc.execute_query(sql)
        if df.empty:
            return None

        top = df.iloc[0]

        headers = [str(col) for col in df.columns]
        rows = df.values.tolist()
        table_lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        for row in rows:
            table_lines.append("| " + " | ".join(str(item) for item in row) + " |")
        table_md = "\n".join(table_lines)

        response = [
            f"SUMMARY The plant with the highest number of active issues is **{top['plant']}**, with **{int(top['active_issues'])}** active issue(s) and **{int(top['total_issues'])}** total issue(s).",
            "",
            "### Quality issues by plant",
            table_md,
            "",
            "Key Takeaways:",
            f"- **{top['plant']}** has the most active issues in the `alerts_quality` dataset.",
            "- This answer is based directly on the actual dataset and not on invented values.",
        ]
        return "\n".join(response)

    structured_intent = _parse_structured_intent(query)
    if structured_intent is None:
        return None

    result_context, result_meta = _execute_structured_intent(structured_intent)
    if result_context is None:
        return None

    # Use LLM only to explain the already computed result.
    data_context = build_data_context(
        intent=detect_intent(query),
        query=query,
        computed_results=result_context,
        signals=compute_cross_dataset_signals(),
    )
    return llm_service.generate_explanation(
        user_query=query,
        result_context=result_context,
        data_context=data_context,
    )


def compute_cross_dataset_signals() -> dict:
    data_svc = get_data_service()
    signals = {
        "alerts_spike": False,
        "production_drop": False,
        "affected_departments": [],
        "correlation_summary": "No clear cross-dataset relationship found.",
    }

    try:
        production = data_svc.execute_query(
            "SELECT week, SUM(units) AS total_units FROM production_data GROUP BY week ORDER BY week"
        )
        alerts = data_svc.execute_query(
            "SELECT week, COUNT(*) AS issue_count, SUM(affected_units) AS affected_units FROM alerts_quality GROUP BY week ORDER BY week"
        )
    except Exception:
        return signals

    if production.empty or alerts.empty:
        return signals

    latest_prod = production.iloc[-1]
    prev_prod = production.iloc[-2] if len(production) > 1 else None
    latest_alert = alerts.iloc[-1]
    prev_alert = alerts.iloc[-2] if len(alerts) > 1 else None

    if prev_alert is not None and prev_alert["issue_count"] > 0:
        signals["alerts_spike"] = latest_alert["issue_count"] >= prev_alert["issue_count"] * 1.2
    if prev_prod is not None and prev_prod["total_units"] > 0:
        signals["production_drop"] = latest_prod["total_units"] <= prev_prod["total_units"] * 0.9

    dept_rows = data_svc.execute_query(
        "SELECT department, SUM(CASE WHEN LOWER(status) = 'active' THEN 1 ELSE 0 END) AS active_issues "
        "FROM alerts_quality GROUP BY department ORDER BY active_issues DESC LIMIT 3"
    )
    signals["affected_departments"] = [str(row["department"]) for _, row in dept_rows.iterrows() if row["active_issues"] > 0]

    if signals["alerts_spike"] and signals["production_drop"]:
        signals["correlation_summary"] = (
            f"Recent data shows alerts increasing while production fell. "
            f"The latest week had {int(latest_alert['issue_count'])} issues and {int(latest_prod['total_units'])} production units, "
            "suggesting a potential link between quality/alerts and output."
        )

    return signals


def build_data_context(intent: str, query: str, computed_results: str | None = None, signals: dict | None = None) -> str:
    """
    Build the data context string based on detected intent.
    Pulls relevant data from DuckDB and formats it for the LLM.
    """
    data_svc = get_data_service()
    context_parts = []

    try:
        context_parts.append("## Data Schema")
        context_parts.append(data_svc.get_table_schemas_text())
        now = datetime.now()
        context_parts.append(f"\n## Time Context")
        context_parts.append(f"- Current date: {now.strftime('%Y-%m-%d (%A)')}")
        context_parts.append(f"- Current week: Week {now.isocalendar()[1]} of {now.year}")
        context_parts.append(f"- Current quarter: Q{(now.month - 1) // 3 + 1} {now.year}")
        context_parts.append(f"- Previous quarter: Q{((now.month - 4) // 3 + 1) if now.month > 3 else 4} {now.year if now.month > 3 else now.year - 1}")
        context_parts.append(f"\n## Detected Intent: {intent}")
        if intent in INTENTS:
            context_parts.append(f"Description: {INTENTS[intent]['description']}")
        if computed_results:
            context_parts.append("\n## Computed Results")
            context_parts.append(computed_results)
        if signals:
            context_parts.append("\n## Cross-Dataset Signals")
            context_parts.append("- alerts_spike: {}".format(signals.get("alerts_spike", False)))
            context_parts.append("- production_drop: {}".format(signals.get("production_drop", False)))
            context_parts.append("- affected_departments: {}".format(signals.get("affected_departments", [])))
            context_parts.append(f"- correlation_summary: {signals.get('correlation_summary', '')}")

        context_parts.append("\n## Response Guidance")
        context_parts.append("- Use the provided computed data; do not recalculate.")
        context_parts.append("- Always explain results clearly and avoid asking the user to load data.")
        context_parts.append("- If there is available data, summarize what exists rather than saying it is unavailable.")

    except Exception as e:
        logger.error(f"Error building data context: {e}")
        context_parts.append(f"\n⚠️ Error loading data context: {str(e)}")

    return "\n".join(context_parts)


async def process_query(
    query: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """
    Full pipeline: Intent → Data → LLM → Response (non-streaming).
    """
    intent = detect_intent(query)
    logger.info(f"Query: '{query[:60]}...' → Intent: {intent}")

    structured_response = execute_structured_query(query)
    if structured_response is not None:
        logger.info("Returning structured response for supported query")
        return structured_response

    data_context = build_data_context(intent, query)

    response = llm_service.generate_response(
        user_query=query,
        data_context=data_context,
        conversation_history=conversation_history,
    )

    return response


async def stream_query(
    query: str,
    conversation_history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Full pipeline: Intent → Data → LLM → Streaming Response.
    Yields tokens as they arrive from the LLM.
    """
    intent = detect_intent(query)
    logger.info(f"Streaming query: '{query[:60]}...' → Intent: {intent}")

    structured_response = execute_structured_query(query)
    if structured_response is not None:
        logger.info("Returning structured response for supported stream query")
        yield structured_response
        return

    data_context = build_data_context(intent, query)

    async for token in llm_service.stream_response(
        user_query=query,
        data_context=data_context,
        conversation_history=conversation_history,
    ):
        yield token
