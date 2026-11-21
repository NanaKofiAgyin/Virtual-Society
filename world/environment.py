"""World clock and environment state: 24h day, 7-day seasons, and weather."""

from __future__ import annotations

import random
from enum import Enum
from typing import Any


class TimeOfDay(str, Enum):
    """Coarse phases of the 24-hour day/night cycle."""

    DAWN = "dawn"
    DAY = "day"
    DUSK = "dusk"
    NIGHT = "night"


class Season(str, Enum):
    """Four-season yearly cycle (7 days each)."""

    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"


class Weather(str, Enum):
    """Simple world weather states."""

    CLEAR = "clear"
    RAIN = "rain"
    STORM = "storm"


SEASON_ORDER: tuple[Season, ...] = (
    Season.SPRING,
    Season.SUMMER,
    Season.AUTUMN,
    Season.WINTER,
)

# Relative probabilities for (CLEAR, RAIN, STORM) per season
SEASON_WEATHER_WEIGHTS: dict[Season, tuple[float, float, float]] = {
    Season.SPRING: (0.50, 0.40, 0.10),
    Season.SUMMER: (0.70, 0.20, 0.10),
    Season.AUTUMN: (0.45, 0.40, 0.15),
    Season.WINTER: (0.55, 0.25, 0.20),
}

# Winter is slow; summer is fast
SEASON_REGROW_MULTIPLIERS: dict[Season, float] = {
    Season.SPRING: 1.2,
    Season.SUMMER: 1.5,
    Season.AUTUMN: 0.8,
    Season.WINTER: 0.2,
}

WEATHER_REGROW_MODIFIERS: dict[Weather, float] = {
    Weather.CLEAR: 0.0,
    Weather.RAIN: 0.2,
    Weather.STORM: -0.1,
}


class Environment:
    """Tracks world time (1 tick = 1 hour), 7-day seasons, and 6-tick weather."""

    def __init__(
        self,
        seed: int | None = None,
        rng: random.Random | None = None,
        hours_per_day: int = 24,
        days_per_season: int = 7,
        weather_check_interval: int = 6,
    ) -> None:
        """Initialize clock at Day 1, 06:00 (Dawn), Spring, Clear."""
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

    @property
    def season(self) -> Season:
        """Return the current season."""
        return SEASON_ORDER[self.season_index]

    @property
    def time_of_day(self) -> TimeOfDay:
        """Return the current phase of the 24-hour day/night cycle."""
        if 5 <= self.hour <= 6:
            return TimeOfDay.DAWN
        if 7 <= self.hour <= 17:
            return TimeOfDay.DAY
        if 18 <= self.hour <= 19:
            return TimeOfDay.DUSK
        return TimeOfDay.NIGHT

    @property
    def is_day(self) -> bool:
        """Return True during daylight hours (dawn, day, or dusk)."""
        return self.time_of_day is not TimeOfDay.NIGHT

    @property
    def is_night(self) -> bool:
        """Return True during night hours."""
        return self.time_of_day is TimeOfDay.NIGHT

    def regrow_multiplier(self) -> float:
        """Return combined resource regrowth multiplier for current season & weather."""
        base = SEASON_REGROW_MULTIPLIERS[self.season]
        modifier = WEATHER_REGROW_MODIFIERS[self.weather]
        return max(0.1, round(base + modifier, 2))

    def advance_time(self, hours: int = 1) -> None:
        """Advance clock by `hours` (1 tick = 1 hour), rolling days/seasons/weather."""
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

    def _update_weather(self) -> None:
        """Sample a new weather state using season-weighted probabilities."""
        weights = SEASON_WEATHER_WEIGHTS[self.season]
        self.weather = self.rng.choices(
            population=[Weather.CLEAR, Weather.RAIN, Weather.STORM],
            weights=weights,
            k=1,
        )[0]

    def to_dict(self) -> dict[str, Any]:
        """Serialize environment state to a JSON-friendly dictionary."""
        return {
            "tick": self.tick,
            "year": self.year,
            "season": self.season.value,
            "day": self.day,
            "hour": self.hour,
            "time_of_day": self.time_of_day.value,
            "is_day": self.is_day,
            "weather": self.weather.value,
            "regrow_multiplier": self.regrow_multiplier(),
        }
