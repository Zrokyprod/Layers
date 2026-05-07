"""API routes for AI integration features."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id, require_tenant_role
from app.db.session import get_db_session
from app.services.embedding_service import get_embedding_service
from app.services.nl_analytics import get_nl_analytics_service
from app.services.predictive_cost import get_predictive_cost_service

router = APIRouter(prefix="/ai", tags=["AI Integration"])


@router.post("/embeddings/index-fix")
async def index_fix_for_search(
    diagnosis_id: str,
    fix_id: str,
    diagnosis_type: str,
    error_message: str | None = None,
    code_snippet: str | None = None,
    fix_diff: str | None = None,
    confidence: float = 0.0,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, Any]:
    """Index a fix for semantic search."""
    project_id = tenant_id
    
    embedding_service = get_embedding_service()
    
    # Prepare embedding text
    embedding_text = embedding_service.prepare_embedding_text(
        diagnosis_type=diagnosis_type,
        error_message=error_message,
        code_snippet=code_snippet,
        fix_diff=fix_diff,
    )
    
    # Store embedding
    result = embedding_service.store_fix_embedding(
        db=db,
        project_id=project_id,
        diagnosis_id=diagnosis_id,
        fix_id=fix_id,
        diagnosis_type=diagnosis_type,
        embedding_text=embedding_text,
        confidence=confidence,
    )
    
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate embedding",
        )
    
    return {
        "status": "indexed",
        "embedding_id": result.id,
        "fix_id": fix_id,
        "diagnosis_type": diagnosis_type,
    }


@router.get("/embeddings/similar-fixes")
async def find_similar_fixes(
    query: str = Query(..., description="Error message or code snippet to search for"),
    diagnosis_type: str | None = Query(None, description="Filter by diagnosis type"),
    limit: int = Query(5, ge=1, le=20),
    min_similarity: float = Query(0.7, ge=0.0, le=1.0),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, Any]:
    """Find similar fixes using semantic search."""
    project_id = tenant_id
    
    embedding_service = get_embedding_service()
    
    similar_fixes = embedding_service.find_similar_fixes(
        db=db,
        project_id=project_id,
        query_text=query,
        diagnosis_type=diagnosis_type,
        limit=limit,
        min_similarity=min_similarity,
    )
    
    return {
        "query": query,
        "count": len(similar_fixes),
        "fixes": similar_fixes,
    }


@router.get("/embeddings/stats")
async def get_embedding_stats(
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, Any]:
    """Get statistics about indexed embeddings."""
    project_id = tenant_id
    
    embedding_service = get_embedding_service()
    stats = embedding_service.get_embedding_stats(db, project_id)
    
    return stats


@router.get("/cost/anomaly-risk")
async def get_cost_anomaly_risk(
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, Any]:
    """Get predictive cost anomaly risk assessment."""
    project_id = tenant_id
    
    cost_service = get_predictive_cost_service()
    risk = cost_service.detect_anomaly_risk(db, project_id)
    
    return risk


@router.get("/cost/forecast")
async def get_cost_forecast(
    hours_ahead: int = Query(4, ge=1, le=24),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, Any]:
    """Get cost forecast for the next N hours."""
    project_id = tenant_id
    
    cost_service = get_predictive_cost_service()
    hourly_data = cost_service.get_hourly_cost_data(db, project_id, hours_back=168)
    forecast = cost_service.forecast_cost(hourly_data, hours_ahead=hours_ahead)
    
    return forecast


@router.post("/analytics/natural-language")
async def natural_language_query(
    query: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, Any]:
    """Execute a natural language analytics query."""
    project_id = tenant_id
    
    nl_service = get_nl_analytics_service()
    
    # Parse the query
    parsed = nl_service.parse_query(query, db=db)

    if "error" in parsed:
        return {
            "status": "parse_error",
            "error": parsed["error"],
            "original_query": query,
        }

    # Execute the query
    results = nl_service.execute_query(db, project_id, parsed)

    # Generate natural language response
    response = nl_service.generate_response(query, results, db=db)
    
    return {
        "status": "success",
        "query": query,
        "parsed": parsed,
        "answer": response["answer"],
        "data": response["data"],
    }
