"""Decide whether the POI layer returns points or grouped counts.

A Jakarta-wide viewport holds 27,114 POIs across all thirty categories, and all
of Jabodetabek holds 43,282. Two obvious approaches both fail:

  Return everything      27,000 DOM markers is unusable, and the browser stalls
                         before the map is readable.
  Truncate to a limit    The map then looks complete while missing most of its
                         content, which is worse than showing nothing.

So the layer aggregates instead. Below the row limit every point comes back
individually. Above it, points are snapped to a grid and each cell reports its
own count, so the numbers on screen still sum to the number in the viewport.
Nothing is dropped, and the response says which mode produced it so the client
can render counts rather than pretending they are places.

Zooming in shrinks the viewport, which lowers the count, which switches the
layer back to individual points. The transition needs no client logic.
"""
from __future__ import annotations

#: Roughly how many cluster cells to lay across the viewport's width. Chosen so
#: a zoomed-out map shows a legible scatter of counts: much lower and the whole
#: city becomes one blob, much higher and the clusters are as dense as the
#: points they replace.
CLUSTER_TARGET = 28

#: Fallback span for a degenerate viewport. parse_bbox already rejects west ==
#: east, but a zero cell size would reach ST_SnapToGrid and divide by zero deep
#: inside Postgres, which is a much harder error to trace back than this.
_MIN_SPAN = 0.001


def should_cluster(pois_in_viewport: int, limit: int) -> bool:
    """True when returning individual points would hit the row limit.

    Tied to the limit rather than to a separate threshold: clustering exists
    precisely because the limit would otherwise cut the layer, so one number
    should govern both and they cannot drift apart.
    """
    return pois_in_viewport > limit


def cluster_cell_size(west: float, east: float) -> float:
    """Grid cell size in degrees, scaled to the viewport's width.

    A fixed size would give one enormous blob when zoomed out and one cluster
    per point when zoomed in. Following the span on screen keeps the visual
    density roughly constant at every zoom level.

    Longitude only: at Jabodetabek's latitude a degree of longitude and a degree
    of latitude differ by about 0.6%, far below the precision this needs, and a
    square cell in degrees is what ST_SnapToGrid expects anyway.
    """
    span = abs(east - west) or _MIN_SPAN
    return span / CLUSTER_TARGET
