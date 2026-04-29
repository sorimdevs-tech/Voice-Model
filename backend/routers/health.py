"""
VOXA Backend — Health Router
"""

from fastapi import APIRouter
from services.llm_service import check_llm_health

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Check the health of the backend and its services.
    """
    llm_health = check_llm_health()
    
    return {
        "status": "healthy",
        "version": "1.0.0",
        "services": {
            "llm": llm_health
        }
    }
