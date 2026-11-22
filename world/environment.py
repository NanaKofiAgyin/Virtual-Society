"""World clock, seasonal climate shifts, tides, and data-driven world events."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

DEFAULT_EVENTS_PATH = Path(__file__).resolve().parent.parent / "data" / "events.json"


class TimeOfDay(str, Enum):
    DAWN = "dawn"
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"


class Season(str, Enum):
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"


class Weather(str, Enum):
    CLEAR = "clear"
    RAIN = "rain"
    STORM = "storm"


SEASON_ORDER: tuple[Season, ...] = (Season.SPRING, Season.SUMMER, Season.AUTUMN, Season.WINTER)
SEASON_WEATHER_WEIGHTS: dict[Season, tuple[float, float, float]] = {
    Season.SPRING: (0.50, 0.40, 0.10),
    Season.SUMMER: (0.70, 0.20, 0.10),
    Season.AUTUMN: (0.45, 0.40, 0.15),
    Season.WINTER: (0.55, 0.25, 0.20),
}
SEASON_REGROW_MULTIPLIERS: dict[Season, float] = {
    Season.SPRING: 1.2, Season.SUMMER: 1.5, Season.AUTUMN: 0.8, Season.WINTER: 0.2,
}
SEASON_TEMP_OFFSETS: dict[Season, float] = {
    Season.SPRING: 0.0, Season.SUMMER: 0.18, Season.AUTUMN: -0.02, Season.WINTER: -0.22,
}
SEASON_RAIN_OFFSETS: dict[Season, float] = {
    Season.SPRING: 0.10, Season.SUMMER: -0.05, Season.AUTUMN: 0.08, Season.WINTER: -0.05,
}
WEATHER_REGROW_MODIFIERS: dict[Weather, float] = {
    Weather.CLEAR: 0.0, Weather.RAIN: 0.2, Weather.STORM: -0.1,
}


@dataclass(frozen=True)
class WorldEventSpec:
    """Data-driven disaster/climate event loaded from `data/events.json`."""

    name: str
    chance: float
    duration: int
    temp_delta: float
    moisture_delta: float
    regrow_multiplier: float
    disease_multiplier: float
    description: str


def load_events(path: Path | str = DEFAULT_EVENTS_PATH) -> dict[str, WorldEventSpec]:
    """Load world event definitions from JSON."""
    raw: dict[str, dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        name: WorldEventSpec(
            name=name, chance=float(c["chance"]), duration=int(c["duration"]),
            temp_delta=float(c["temp_delta"]), moisture_delta=float(c["moisture_delta"]),
            regrow_multiplier=float(c["regrow_multiplier"]),
            disease_multiplier=float(c["disease_multiplier"]),
            description=str(c["description"]),
        )
        for name, c in raw.items()
    }


class Environment:
    """Tracks clock, 7-day seasons, temperature/rainfall shifts, tides, and events."""

    def __init__(
        self,
        seed: int | None = None,
        rng: random.Random | None = None,
        hours_per_day: int = 24,
        days_per_season: int = 7,
        weather_check_interval: int = 6,
        events_path: Path | str = DEFAULT_EVENTS_PATH,
    ) -> None:
        if hours_per_day <= 0 or days_per_season <= 0 or weather_check_interval <= 0:
            raise ValueError("Clock intervals must be positive integers")
        self.rng: random.Random = rng if rng is not None else random.Random(seed)
        self.hours_per_day = hours_per_day
        self.days_per_season = days_per_season
        self.weather_check_interval = weather_check_interval

        self.tick: int = 0
        self.hour: int = 6
        self.day: int = 1
        self.season_index: int = 0
        self.year: int = 1
        self.weather: Weather = Weather.CLEAR

        self.event_specs: dict[str, WorldEventSpec] = load_events(events_path)
        self.active_event: WorldEventSpec | None = None
        self.event_ticks_left: int = 0

    @property
    def season(self) -> Season:
        return SEASON_ORDER[self.season_index]

    @property
    def time_of_day(self) -> TimeOfDay:
        if 5 <= self.hour <= 6:
            return TimeOfDay.DAWN
        if 7 <= self.hour <= 17:
            return TimeOfDay.DAY
        if 18 <= self.hour <= 19:
            return TimeOfDay.DUSK
        return TimeOfDay.NIGHT

    @property
    def is_day(self) -> bool:
        return self.time_of_day is not TimeOfDay.NIGHT

    @property
    def is_night(self) -> bool:
        return self.time_of_day is TimeOfDay.NIGHT

    def temp_offset(self) -> float:
        """Combined temperature shift from current season and active event."""
        ev = self.active_event.temp_delta if self.active_event else 0.0
        return round(SEASON_TEMP_OFFSETS[self.season] + ev, 3)

    def rain_offset(self) -> float:
        """Combined moisture/rainfall shift from season, weather, and active event."""
        w = 0.12 if self.weather is Weather.RAIN else (0.20 if self.weather is Weather.STORM else 0.0)
        ev = self.active_event.moisture_delta if self.active_event else 0.0
        return round(SEASON_RAIN_OFFSETS[self.season] + w + ev, 3)

    def tide_level(self) -> float:
        """Sinusoidal 12-hour ocean tide level in [-1.0, 1.0]."""
        return round(math.sin((2.0 * math.pi * self.tick) / 12.0), 3)

    def disease_multiplier(self) -> float:
        return self.active_event.disease_multiplier if self.active_event else 1.0

    def regrow_multiplier(self) -> float:
        base = SEASON_REGROW_MULTIPLIERS[self.season] + WEATHER_REGROW_MODIFIERS[self.weather]
        ev_mult = self.active_event.regrow_multiplier if self.active_event else 1.0
        return max(0.05, round(base * ev_mult, 2))

    def advance_time(self, hours: int = 1) -> None:
        if hours < 0:
            raise ValueError("hours must be non-negative")
        for _ in range(hours):
            self.tick += 1
            self.hour += 1
            if self.hour >= self.hours_per_day:
                self.hour = 0
                self.day += 1
                if self.day > self.days_per_season:
                    self.day = 1
                    self.season_index += 1
                    if self.season_index >= len(SEASON_ORDER):
                        self.season_index = 0
                        self.year += 1

            if self.tick % self.weather_check_interval == 0:
                self._update_weather()
            self._step_events()

    def _update_weather(self) -> None:
        weights = SEASON_WEATHER_WEIGHTS[self.season]
        self.weather = self.rng.choices(
            population=[Weather.CLEAR, Weather.RAIN, Weather.STORM], weights=weights, k=1
        )[0]

    def _step_events(self) -> None:
        if self.active_event is not None:
            self.event_ticks_left -= 1
            if self.event_ticks_left <= 0:
                self.active_event = None
            return
        for spec in self.event_specs.values():
            if self.rng.random() < spec.chance:
                self.active_event = spec
                self.event_ticks_left = spec.duration
                break

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick, "year": self.year, "season": self.season.value,
            "day": self.day, "hour": self.hour, "time_of_day": self.time_of_day.value,
            "is_day": self.is_day, "weather": self.weather.value,
            "temp_offset": self.temp_offset(), "rain_offset": self.rain_offset(),
            "tide_level": self.tide_level(),
            "active_event": self.active_event.name if self.active_event else None,
            "regrow_multiplier": self.regrow_multiplier(),
        }
