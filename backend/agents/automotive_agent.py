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
from typing import AsyncGenerator
from datetime import datetime

from services.data_service import get_data_service
from services import llm_service

logger = logging.getLogger("voxa.agent")

# ── Intent Categories (Recipes) ──
INTENTS = {
    "weekly_dashboard": {
        "keywords": ["dashboard", "weekly", "this week", "week's report", "how are we doing this week"],
        "description": "Weekly operational health check",
    },
    "forecast_dashboard": {
        "keywords": ["forecast", "next week", "planned", "targets", "projection"],
        "description": "Production and revenue forecast",
    },
    "quarterly_dashboard": {
        "keywords": ["quarter", "last quarter", "q1", "q2", "q3", "q4", "quarterly"],
        "description": "Quarterly performance review",
    },
    "production_summary": {
        "keywords": ["production summary", "units summary", "revenue summary", "total units", "output"],
        "description": "Deep dive into production metrics",
    },
    "plant_performance": {
        "keywords": ["highest production", "best plant", "worst plant", "plant ranking", "top plant"],
        "description": "Plant-level performance ranking",
    },
    "department_performance": {
        "keywords": ["best department", "performing best", "department-wise", "dept"],
        "description": "Department-level performance analysis",
    },
    "model_performance": {
        "keywords": ["model-wise", "which model", "best selling model", "f-150", "mustang"],
        "description": "Vehicle model production analysis",
    },
    "trend_analysis": {
        "keywords": ["trend", "over time", "historically", "growth", "decline"],
        "description": "Performance trends over periods",
    },
    "task_management": {
        "keywords": ["tasks", "scheduled", "today's tasks", "pending", "assigned", "priority"],
        "description": "Task and operation schedule",
    },
    "alerts_quality": {
        "keywords": ["alerts", "issues", "severity", "quality", "problem", "high severity"],
        "description": "Quality issues and critical alerts",
    },
    "comparison_analysis": {
        "keywords": ["compare", "vs", "versus", "comparison", "forecast vs actual"],
        "description": "Comparative analysis between periods or datasets",
    },
    "general": {
        "keywords": [],
        "description": "General plant dashboard query",
    },
}


def detect_intent(query: str) -> str:
    """
    Enhanced intent detection for the 20 recipe types.
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


def build_data_context(intent: str, query: str) -> str:
    """
    Build the data context string based on detected intent.
    Pulls relevant data from all 4 DuckDB tables.
    """
    data_svc = get_data_service()
    context_parts = []

    try:
        # Table Schema Context
        context_parts.append("## Data Schema")
        context_parts.append(data_svc.get_table_schemas_text())

        # Full Data Context (for all 4 tables)
        context_parts.append("\n## Data Records")
        context_parts.append(data_svc.get_full_data_dump())

        # Time Context
        # Using 2024-05-15 as 'today' for consistency with sample data
        today = datetime(2024, 5, 15) 
        context_parts.append(f"\n## Time Context")
        context_parts.append(f"- Current date (Simulated): {today.strftime('%Y-%m-%d (%A)')}")
        context_parts.append(f"- Current week: W{today.isocalendar()[1]}")
        context_parts.append(f"- Current month: {today.month}")
        context_parts.append(f"- Current quarter: Q{(today.month - 1) // 3 + 1}")

        # Relationship Context
        context_parts.append("\n## Operational Context & Relationships")
        context_parts.append("- Link `alerts_quality` to `production_data` by Department and Week.")
        context_parts.append("- Link `tasks_schedule` to `production_data` by Department and Week.")
        context_parts.append("- Correlate High Severity alerts with production dips if applicable.")

    except Exception as e:
        logger.error(f"Error building data context: {e}")
        context_parts.append(f"\n⚠️ Error loading data: {str(e)}")

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

    data_context = build_data_context(intent, query)

    async for token in llm_service.stream_response(
        user_query=query,
        data_context=data_context,
        conversation_history=conversation_history,
    ):
        yield token
