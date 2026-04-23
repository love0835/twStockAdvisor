"""Abstract base class for analyzers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from twadvisor.models import AnalysisRequest, AnalysisResponse


class BaseAnalyzer(ABC):
    """Common interface for AI analyzers."""

    @abstractmethod
    async def analyze(self, req: AnalysisRequest) -> AnalysisResponse:
        """Run analysis for a single request."""

    @abstractmethod
    def build_prompt(self, req: AnalysisRequest) -> tuple[str, str]:
        """Return the system and user prompts."""
