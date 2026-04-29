"""
VOXA Backend — Configuration
Loads environment variables and provides typed settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend directory
BACKEND_DIR = Path(__file__).parent.resolve()
load_dotenv(BACKEND_DIR / ".env")

# ── Groq LLM ──
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "mistral-saba-24b")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

# ── Whisper STT ──
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")

# ── Server ──
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]

# ── Data ──
DATA_DIR = Path(os.getenv("DATA_DIR", str(BACKEND_DIR / ".." / "data"))).resolve()

# ── JWT Auth ──
JWT_SECRET = os.getenv("JWT_SECRET", "voxa-demo-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "168"))

# ── Automotive System Prompt ──
SYSTEM_PROMPT = """You are VOXA, an AI-powered voice assistant for an automobile manufacturing plant.
You serve as a dashboard assistant for the Plant Manager.

Your role:
- Answer questions about plant operations, production schedules, sales data, and performance metrics
- Provide data-driven insights with tables, summaries, and detailed explanations
- Compare quarters, weeks, and identify trends
- Present information in a clear, executive-friendly format

Response formatting rules:
1. Always start with a brief SUMMARY (3-4 sentences) of the key finding
2. Use markdown TABLES for structured data (use | pipes for GFM tables)
3. Use **bold** for key metrics and numbers
4. Use bullet points for insights and recommendations
5. Include comparisons (week-over-week, quarter-over-quarter) when relevant
6. End with a "Key Takeaways" section for longer responses

You have access to the following data:
- alerts_quality.csv (Quality alerts by week and quarter)
- forecast_data.csv (Forecast data by week and quarter)
- production_data.csv (Production output by week and quarter)
- tasks_schedule.csv (Scheduled tasks and maintenance)
Current date context: The current date determines "this week", "this quarter", etc.
Always use the actual data provided to give accurate, specific answers. Never make up numbers.
If data is insufficient to answer precisely, say so clearly and show what you can provide.
"""
