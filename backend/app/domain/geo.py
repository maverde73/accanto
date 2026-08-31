"""Geography: distance, geofence containment, and precision reduction."""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_008.8

COARSE_DECIMALS = 2
"""Rounding applied to `location:coarse` holders.

Two decimal places is roughly 1.1 km of latitude -- enough to say "she is in
this part of town" and not enough to say "she is at this address". Longitude
cells shrink towards the poles, which only makes the result coarser in metres,
never finer.
"""


@dataclass(frozen=True, slots=True)
class Point:
    lat: float
    lon: float


def haversine_m(a: Point, b: Point) -> float:
    """Great-circle distance in metres."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def inside(point: Point, center: Point, radius_m: float) -> bool:
    return haversine_m(point, center) <= radius_m


def coarsen(point: Point, decimals: int = COARSE_DECIMALS) -> Point:
    """Reduce precision for a caregiver who may not see the exact position.

    Applied server-side, always. Sending the precise value and hiding it in the
    client would not be a permission, only a suggestion.
    """
    return Point(lat=round(point.lat, decimals), lon=round(point.lon, decimals))


def coarse_accuracy_m(decimals: int = COARSE_DECIMALS) -> float:
    """Uncertainty implied by rounding, so the map can draw an honest circle."""
    return 111_320.0 * (10.0**-decimals) / 2.0
