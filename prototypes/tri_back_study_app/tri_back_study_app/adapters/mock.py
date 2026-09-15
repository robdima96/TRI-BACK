"""Offline mock adapter for UI development without bot/."""

from __future__ import annotations

from tri_back_study_app.adapters.base import ChatTurnResult


class MockAdapter:
    async def send_message(self, session_id: str, message: str) -> ChatTurnResult:
        return ChatTurnResult(
            session_id=session_id,
            response=(
                "Thank you for sharing. Based on what you described, "
                "conservative management is often appropriate, but I need a few more details."
            ),
            citations=[
                {
                    "source": "r_1",
                    "snippet": "Mock evidence snippet for offline UI testing.",
                    "score": 0.8,
                    "chunk_id": "r_1",
                }
            ],
            question_mode=True,
            round_trip_ms=120.0,
        )
