"""Vector embedding service for semantic search of fixes."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from openai import OpenAI
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import FixEmbedding

logger = logging.getLogger(__name__)

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class EmbeddingService:
    """Service for generating and querying fix embeddings."""

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self.client = OpenAI(
            base_url=_OPENROUTER_BASE_URL,
            api_key=api_key or settings.OPENROUTER_API_KEY,
            default_headers={
                "HTTP-Referer": settings.FRONTEND_URL or "https://zroky.com",
                "X-Title": settings.APP_NAME or "Zroky AI",
            },
        )
        self.model = "text-embedding-3-small"
        self.dimensions = 1536

    def generate_embedding(self, text: str) -> list[float] | None:
        """Generate embedding for text using OpenAI API."""
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning("Failed to generate embedding: %s", e)
            return None

    def prepare_embedding_text(
        self,
        diagnosis_type: str,
        error_message: str | None,
        code_snippet: str | None,
        fix_diff: str | None,
    ) -> str:
        """Prepare text for embedding from fix components."""
        parts = [f"Diagnosis: {diagnosis_type}"]
        
        if error_message:
            parts.append(f"Error: {error_message}")
        if code_snippet:
            parts.append(f"Code: {code_snippet[:2000]}")
        if fix_diff:
            parts.append(f"Fix: {fix_diff[:3000]}")
        
        return "\n\n".join(parts)

    def store_fix_embedding(
        self,
        db: Session,
        project_id: str,
        diagnosis_id: str,
        fix_id: str,
        diagnosis_type: str,
        embedding_text: str,
        confidence: float = 0.0,
    ) -> FixEmbedding | None:
        """Generate and store embedding for a fix."""
        embedding_vector = self.generate_embedding(embedding_text)
        
        if embedding_vector is None:
            return None

        # Check if embedding already exists
        existing = db.execute(
            select(FixEmbedding).where(
                FixEmbedding.project_id == project_id,
                FixEmbedding.fix_id == fix_id,
            )
        ).scalar_one_or_none()

        if existing:
            existing.embedding_text = embedding_text
            existing.embedding = embedding_vector
            existing.embedding_model = self.model
            existing.diagnosis_type = diagnosis_type
            existing.confidence = confidence
            db.commit()
            return existing

        fix_embedding = FixEmbedding(
            project_id=project_id,
            diagnosis_id=diagnosis_id,
            fix_id=fix_id,
            embedding_text=embedding_text,
            embedding=embedding_vector,
            embedding_model=self.model,
            diagnosis_type=diagnosis_type,
            confidence=confidence,
        )
        db.add(fix_embedding)
        db.commit()
        return fix_embedding

    def find_similar_fixes(
        self,
        db: Session,
        project_id: str,
        query_text: str,
        diagnosis_type: str | None = None,
        limit: int = 5,
        min_similarity: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Find similar fixes using vector similarity search."""
        query_embedding = self.generate_embedding(query_text)
        
        if query_embedding is None:
            return []

        # Convert to numpy array for pgvector cosine similarity
        query_vector = np.array(query_embedding)
        
        # Use pgvector <=> operator for cosine distance (1 - cosine_similarity)
        # Cosine similarity = 1 - cosine_distance
        sql = """
            SELECT 
                id,
                diagnosis_id,
                fix_id,
                diagnosis_type,
                confidence,
                embedding_text,
                1 - (embedding <=> :query_vector) as similarity
            FROM fix_embeddings
            WHERE project_id = :project_id
            AND 1 - (embedding <=> :query_vector) >= :min_similarity
        """
        
        params = {
            "query_vector": query_vector.tolist(),
            "project_id": project_id,
            "min_similarity": min_similarity,
        }
        
        if diagnosis_type:
            sql += " AND diagnosis_type = :diagnosis_type"
            params["diagnosis_type"] = diagnosis_type
        
        sql += " ORDER BY similarity DESC LIMIT :limit"
        params["limit"] = limit

        result = db.execute(text(sql), params)
        
        similar_fixes = []
        for row in result:
            similar_fixes.append({
                "id": row.id,
                "diagnosis_id": row.diagnosis_id,
                "fix_id": row.fix_id,
                "diagnosis_type": row.diagnosis_type,
                "confidence": row.confidence,
                "embedding_text": row.embedding_text[:500],  # Truncated for preview
                "similarity": float(row.similarity),
            })
        
        return similar_fixes

    def get_embedding_stats(self, db: Session, project_id: str) -> dict[str, Any]:
        """Get statistics about stored embeddings for a project."""
        total = db.execute(
            select(func.count()).select_from(FixEmbedding)
            .where(FixEmbedding.project_id == project_id)
        ).scalar() or 0

        rows = db.execute(
            select(FixEmbedding.diagnosis_type, func.count().label("cnt"))
            .where(FixEmbedding.project_id == project_id)
            .group_by(FixEmbedding.diagnosis_type)
        ).all()
        by_type = {row.diagnosis_type: row.cnt for row in rows}

        return {
            "total_embeddings": total,
            "by_diagnosis_type": by_type,
            "model": self.model,
            "dimensions": self.dimensions,
        }


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get or create embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
