from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    profiles_count: int
    dataset_version: str


class OptionsResponse(BaseModel):
    cities: list[str]
    categories: list[str]
    event_types: list[str]
    languages: list[str]
    date_min: Date
    date_max: Date
    dataset_version: str


class Contractor(BaseModel):
    id: str
    anon_name: str
    categories: list[str]
    city: str
    city_imputed: bool
    synthetic: bool
    price_from_kzt: int
    price_imputed: bool
    event_formats: list[str]
    languages: list[str]
    max_hours: float | None
    busy_dates: list[Date]
    description: str


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    city: str = Field(min_length=1, max_length=200)
    date: Date
    event_type: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=200)
    budget_kzt: int = Field(gt=0, le=9007199254740991, strict=True)
    duration_hours: float | None = Field(default=None, gt=0, allow_inf_nan=False, strict=True)
    language: str | None = Field(default=None, min_length=1, max_length=200)
    preferences: str = Field(default="", max_length=1000)


class SelectedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(min_length=1)


class RankingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_mode: Literal["ai", "fallback"]
    selected: list[SelectedCandidate]


class RecommendationCard(BaseModel):
    id: str
    name: str
    categories: list[str]
    city: str
    price_from_kzt: int
    reason: str
    evidence_ids: list[str]
    synthetic: bool
    city_imputed: bool
    price_imputed: bool


class ExcludedCounts(BaseModel):
    date: int = 0
    budget: int = 0
    event_type: int = 0
    duration: int = 0
    language: int = 0


class RecommendationResponse(BaseModel):
    status: Literal["matched", "category_absent", "no_matches"]
    message: str
    cards: list[RecommendationCard]
    total_in_city_category: int
    eligible_count: int
    excluded_counts: ExcludedCounts
    selection_mode: Literal["ai", "fallback"] | None
    cache_hit: bool
    dataset_version: str
    recommendation_version: str
