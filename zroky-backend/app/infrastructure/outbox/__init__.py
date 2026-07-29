"""Transactional outbox infrastructure boundary."""

from app.db.models import FinalDomainOutboxJob

__all__ = ["FinalDomainOutboxJob"]

