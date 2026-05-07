"""Realtime broadcast layer (WebSocket hub) for live dashboard updates."""

from app.realtime.hub import RealtimeHub, get_hub

__all__ = ["RealtimeHub", "get_hub"]
