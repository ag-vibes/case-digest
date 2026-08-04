from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Region(str, Enum):
    RU = "ru"
    INTL = "intl"


class SourceKind(str, Enum):
    RSS = "rss"
    SITEMAP = "sitemap"
    GOOGLE_NEWS = "google_news"
    TELEGRAM = "telegram"


class SourceConfig(BaseModel):
    id: str
    name: str
    region: Region
    kind: SourceKind
    url: str | None = None
    query: str | None = None
    allowed_domain: str | None = None
    include_pattern: str | None = None
    username: str | None = None


class Candidate(BaseModel):
    source_id: str
    source_name: str
    source_kind: SourceKind
    region: Region
    title: str
    url: str
    published_at: datetime | None = None
    summary: str = ""
    full_text: str = ""
    views: int | None = None
    reactions: int | None = None
    discovery_score: float = 0.0
    extraction_method: str | None = None


class CaseAssessment(BaseModel):
    candidate_url: str
    is_case: bool = False
    brand: str = ""
    market: str = ""
    campaign: str = ""
    agency: str = ""
    activation_type: str = ""
    mechanism: str = ""
    why_interesting: str = ""
    cultural_insight: str = ""
    evidence: str = ""
    novelty: float = Field(default=0, ge=0, le=10)
    insight: float = Field(default=0, ge=0, le=10)
    clarity: float = Field(default=0, ge=0, le=10)
    execution: float = Field(default=0, ge=0, le=10)
    evidence_quality: float = Field(default=0, ge=0, le=10)
    confidence: float = Field(default=0, ge=0, le=1)
    exclusion_reason: str = ""

    @property
    def weighted_score(self) -> float:
        return round(
            self.novelty * 0.30
            + self.insight * 0.25
            + self.clarity * 0.20
            + self.execution * 0.15
            + self.evidence_quality * 0.10,
            2,
        )


class SelectedCase(BaseModel):
    candidate: Candidate
    assessment: CaseAssessment


class SourceHealth(BaseModel):
    source_id: str
    source_name: str
    status: str
    candidates: int = 0
    detail: str = ""


class RunReport(BaseModel):
    started_at: datetime
    finished_at: datetime
    period_start: datetime
    period_end: datetime
    source_health: list[SourceHealth]
    collected_count: int
    extracted_count: int
    deduplicated_count: int
    assessed_count: int
    feedback_examples_count: int
    selected: list[SelectedCase]
    rejected: list[dict]
