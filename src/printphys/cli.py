# Copyright (c) 2026 Lakshya Saraf
# SPDX-License-Identifier: MIT

"""Command-line interface.

The requested artifact (URDF/SDF/MJCF snippet or JSON report) goes to stdout
so it can be piped; the human-readable summary goes to stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from printphys.analyze import analyze
from printphys.materials import available_materials
from printphys.settings import KNOWN_PATTERNS, PrintSettings

_MASS_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(kg|g|mg)?\s*$", re.IGNORECASE)
_MASS_FACTORS = {"kg": 1.0, "g": 1e-3, "mg": 1e-6}


def parse_mass_to_kg(text: str) -> float:
    """Parse '42.1g', '0.0421kg', or bare grams ('42.1') to kg."""
    m = _MASS_RE.match(text)
    if not m:
        raise argparse.ArgumentTypeError(f"could not parse mass {text!r} (try '42.1g')")
    value, unit = float(m.group(1)), (m.group(2) or "g").lower()
    return value * _MASS_FACTORS[unit]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="printphys",
        description="Accurate URDF physics (mass, COM, inertia) for 3D-printed parts.",
        epilog="Example: printphys part.stl --material pla --infill 20 --pattern gyroid",
    )
    parser.add_argument("mesh", nargs="?", help="mesh file (STL/3MF/OBJ/PLY)")
    parser.add_argument(
        "--gcode",
        metavar="FILE",
        help="analyze a sliced G-code file instead of the mesh (high accuracy)",
    )

    mat = parser.add_argument_group("material and print settings")
    mat.add_argument(
        "--material",
        default="pla",
        help=f"bundled material name or YAML path (bundled: {', '.join(available_materials())})",
    )
    mat.add_argument("--infill", type=float, default=20.0, metavar="PCT", help="infill percent")
    mat.add_argument(
        "--pattern",
        default="grid",
        choices=sorted(KNOWN_PATTERNS),
        help="infill pattern",
    )
    mat.add_argument("--walls", type=int, default=2, help="perimeter/wall count")
    mat.add_argument("--line-width", type=float, default=0.4, metavar="MM")
    mat.add_argument("--layer-height", type=float, default=0.2, metavar="MM")
    mat.add_argument("--top-layers", type=int, default=4)
    mat.add_argument("--bottom-layers", type=int, default=4)

    acc = parser.add_argument_group("accuracy and validation")
    acc.add_argument(
        "--weighed-mass",
        type=parse_mass_to_kg,
        metavar="MASS",
        help="measured mass of the printed part, e.g. '42.1g'; rescales the "
        "output and reports the estimation error",
    )
    acc.add_argument("--units", default="mm", choices=["mm", "cm", "m", "in"], help="mesh units")
    acc.add_argument("--pitch", type=float, metavar="MM", help="voxel size override")
    acc.add_argument(
        "--no-pattern-aware",
        action="store_true",
        help="use uniform interior density instead of modeling the infill pattern",
    )
    acc.add_argument(
        "--filament-diameter", type=float, default=1.75, metavar="MM", help="for --gcode"
    )

    out = parser.add_argument_group("output")
    out.add_argument(
        "--format",
        default="urdf",
        choices=["urdf", "sdf", "mjcf", "json"],
        help="output format (default: urdf)",
    )
    out.add_argument("--output", "-o", metavar="FILE", help="write output to file")
    out.add_argument(
        "--patch-urdf", metavar="URDF", help="patch the <inertial> of a link in this URDF file"
    )
    out.add_argument("--link", help="link name for --patch-urdf")
    out.add_argument("--precision", type=int, default=9, help="significant digits")
    out.add_argument("--quiet", "-q", action="store_true", help="suppress the summary on stderr")
    return parser


def _summary(result) -> str:
    props = result.props
    lines = [
        f"material:  {result.material.display_name} "
        f"({result.material.density_g_cm3} g/cm^3)",
        f"backend:   {result.meta.get('backend', '?')}",
        f"mass:      {props.mass * 1000:.3f} g",
        f"com:       [{props.com[0]:.6f}, {props.com[1]:.6f}, {props.com[2]:.6f}] m",
        f"inertia:   ixx={props.ixx:.4e} iyy={props.iyy:.4e} izz={props.izz:.4e} kg*m^2",
    ]
    eff = result.meta.get("effective_density_g_cm3")
    if eff:
        lines.append(
            f"effective density: {eff:.4f} g/cm^3 "
            "(use as custom material density in CAD exporters)"
        )
    if result.validation:
        err = result.validation["estimate_error_percent"]
        lines.append(
            f"validation: estimate was {err:+.2f}% vs weighed mass; outputs rescaled"
        )
    if not props.is_physically_valid():
        lines.append("WARNING: inertia violates the triangle inequality (numerical issue?)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.mesh and not args.gcode:
        parser.error("provide a mesh file or --gcode FILE")
    if args.patch_urdf and not args.link:
        parser.error("--patch-urdf requires --link")

    try:
        settings = PrintSettings(
            infill_percent=args.infill,
            pattern=args.pattern,
            wall_count=args.walls,
            line_width=args.line_width,
            layer_height=args.layer_height,
            top_layers=args.top_layers,
            bottom_layers=args.bottom_layers,
        )
        result = analyze(
            mesh_path=args.mesh,
            settings=settings,
            material=args.material,
            gcode_path=args.gcode,
            units=args.units,
            pitch=args.pitch,
            pattern_aware=not args.no_pattern_aware,
            weighed_mass_kg=args.weighed_mass,
            filament_diameter_mm=args.filament_diameter,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        output = json.dumps(result.to_report(), indent=2)
    elif args.format == "urdf":
        output = result.to_urdf(precision=args.precision)
    elif args.format == "sdf":
        output = result.to_sdf(precision=args.precision)
    else:
        output = result.to_mjcf(precision=args.precision)

    if args.patch_urdf:
        from printphys.export.urdf import patch_urdf

        written = patch_urdf(
            args.patch_urdf, args.link, result.props, precision=args.precision
        )
        if not args.quiet:
            print(f"patched link {args.link!r} in {written}", file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output + "\n")
    else:
        print(output)

    if not args.quiet:
        print(_summary(result), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
