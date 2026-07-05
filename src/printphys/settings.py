# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""Print settings: the slicer parameters that determine mass distribution."""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Patterns for which the voxel backend can model the actual geometry of the
# infill (density *distribution*, not just the average). Others fall back to a
# uniform effective density, which is still mass-exact.
GEOMETRY_AWARE_PATTERNS = frozenset({"gyroid", "grid", "lines", "rectilinear"})

KNOWN_PATTERNS = GEOMETRY_AWARE_PATTERNS | frozenset(
    {"triangles", "cubic", "honeycomb", "concentric", "uniform"}
)


@dataclass
class PrintSettings:
    """FDM print settings relevant to mass distribution. Lengths in mm."""

    infill_percent: float = 20.0
    pattern: str = "grid"
    wall_count: int = 2
    line_width: float = 0.4
    layer_height: float = 0.2
    top_layers: int = 4
    bottom_layers: int = 4

    def __post_init__(self) -> None:
        if not 0.0 <= self.infill_percent <= 100.0:
            raise ValueError(f"infill_percent must be in [0, 100], got {self.infill_percent}")
        self.pattern = self.pattern.lower()
        if self.pattern not in KNOWN_PATTERNS:
            raise ValueError(
                f"unknown pattern {self.pattern!r}; expected one of {sorted(KNOWN_PATTERNS)}"
            )
        if self.wall_count < 0:
            raise ValueError(f"wall_count must be >= 0, got {self.wall_count}")
        if self.line_width <= 0:
            raise ValueError(f"line_width must be > 0, got {self.line_width}")
        if self.layer_height <= 0:
            raise ValueError(f"layer_height must be > 0, got {self.layer_height}")
        if self.top_layers < 0 or self.bottom_layers < 0:
            raise ValueError("top_layers and bottom_layers must be >= 0")

    @property
    def infill_fraction(self) -> float:
        return self.infill_percent / 100.0

    @property
    def wall_thickness(self) -> float:
        """Total lateral wall thickness in mm."""
        return self.wall_count * self.line_width

    @property
    def top_thickness(self) -> float:
        return self.top_layers * self.layer_height

    @property
    def bottom_thickness(self) -> float:
        return self.bottom_layers * self.layer_height

    def to_dict(self) -> dict:
        return asdict(self)
