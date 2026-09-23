from datetime import date
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    profiles_count: int
    dataset_version: str


class CalendarWindow(BaseModel):
    start: date
    end: date


class OptionsResponse(BaseModel):
    cities: list[str]
    categories: list[str]
    event_types: list[str]
    languages: list[str]
    calendar_window: CalendarWindow
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
    busy_dates: list[date]
    description: str
