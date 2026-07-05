# Case study: Xbox One controller bumper (LB04.stl)

A small, thin, wall-dominated part — a good stress test for the voxel backend,
and the first real print-and-weigh datapoint recorded for `printphys`.

## Source and license

- **Design**: [LB RB replacements for Xbox One controller (day one edition)](https://cults3d.com/en/3d-model/gadget/lb-rb-replacements-for-xbox-one-controller-day-one-edition-1537)
- **Author**: [raffosan](https://cults3d.com/en/users/raffosan)
- **Platform**: Cults3D (originally published to Thingiverse, January 2017)
- **License**: CC BY-SA — credit the author, share derivatives under the same license
- **File used**: `LB04.stl` (one of four variants; "04" = hole diameter increased by
  0.4 mm to compensate for the designer's printer under-sizing small holes)

The STL is **not** included in this repository — download it from the link
above if you want to reproduce these numbers.

The designer's own suggested settings were **50% infill, 2 shells, with
supports**. We tested with different settings (below); this is a valid
comparison of *our estimate vs. the print we actually made*, just not a
comparison against the designer's recommendation.

## The part

```text
extents:  21.5 x 16.0 x 40.8 mm   (X x Y x Z)
volume:   1934.6 mm^3
watertight: yes
```

It's small, and it isn't a simple box — it has a mounting hole and a lever arm
thinner than a couple of wall-widths in places. That combination (small overall
size + wall thickness that's a large fraction of every cross-section) is exactly
where a voxel-based estimate is expected to be least confident.

## Settings used

```bash
printphys LB04.stl --material pla --infill 15 --pattern grid --walls 3
```

Everything else at CLI defaults: `layer_height=0.2mm`, `line_width=0.4mm`,
`top_layers=4`, `bottom_layers=4`. Printed on a Bambu Lab printer, sliced in
Bambu Studio, generic PLA (density assumed 1.24 g/cm^3).

## Results

| Source | Mass | Error vs. measured |
|---|---|---|
| `printphys`, default voxel pitch (~0.212 mm) | 1.928 g | **-6.9%** |
| `printphys`, finer voxel pitch (`--pitch 0.1`) | 1.972 g | **-4.8%** |
| Bambu Studio (post-slice plate estimate) | 2.39 g | **+15.5%** |
| **Measured on a scale** | **2.07 g** | — ground truth |

## Why the gap

**This part is dominated by walls and skins, not infill.** Running the same
settings at 0% and 100% infill brackets how much the infill setting can even
matter here:

| Infill | Mass | Effective density |
|---|---|---|
| 0% (walls + top/bottom skin only) | 1.845 g | 0.95 g/cm^3 (77% of solid) |
| 15% (as printed) | 1.928 g | 1.00 g/cm^3 |
| 50% | 2.122 g | 1.10 g/cm^3 |
| 100% (fully solid) | 2.399 g | 1.24 g/cm^3 |

Three walls (3 x 0.4 mm = 1.2 mm) eat into a cross-section that's only
16-21.5 mm wide to begin with, so most of the volume is classified as solid
wall/skin regardless of the infill %. That's consistent with how a real
slicer behaves on a part this size — but it also means the *voxel grid
resolution* matters more here than it would on a bigger part, because the
wall band (1.2 mm) is being measured in units of a voxel pitch that's not much
smaller than it.

**Voxel pitch sensitivity confirms this.** Re-running at 15% infill with
different voxel sizes:

| Voxel pitch | Mass |
|---|---|
| 0.8 mm | 1.683 g |
| 0.4 mm | 1.687 g |
| 0.2 mm | 1.863 g |
| ~0.212 mm (auto default) | 1.928 g |
| 0.1 mm | 1.972 g |

That's a real ~17% spread across pitches, and it isn't perfectly monotonic
(0.2 mm gives a lower mass than the slightly coarser auto-default of 0.212 mm)
— a sign of grid-alignment sensitivity on this part's small features, not
smooth, predictable convergence. Halving the pitch from the default closes
about a third of the gap to the measured mass (-6.9% to -4.8%), which says the
*discretization* is a real, but not the only, contributor.

**A residual ~4-5% gap remains even at fine resolution.** That's consistent
with normal real-world sources this project doesn't model: PLA density
tolerance across brands/spools (+-2-4% is typical), first-layer squish adding
slightly more material than nominal, and extrusion flow calibration on the
specific printer.

**Bambu Studio's post-slice number (2.39 g) was the outlier, not `printphys`.**
It's suspiciously close to this part's fully-solid mass (2.399 g) — most
likely it includes plate extras (skirt/purge) beyond the part itself, or
reflects a different effective infill than intended. It shouldn't be read as
"ground truth" just because it came from a slicer.

## Reproducing this

```bash
# after downloading LB04.stl from the source link above
printphys LB04.stl --material pla --infill 15 --pattern grid --walls 3 --format json

# calibrate to the measured weight
printphys LB04.stl --material pla --infill 15 --pattern grid --walls 3 \
    --weighed-mass 2.07g --format json

# see the pitch sensitivity for yourself
printphys LB04.stl --material pla --infill 15 --pattern grid --walls 3 --pitch 0.1
```

## Takeaways

- For small, thin, wall-dominated parts, don't trust the default voxel
  resolution blindly — try a finer `--pitch` and see if the answer moves.
- `--weighed-mass` exists exactly for cases like this: it can't fix
  discretization error, but it cancels out the *systematic* part of the gap
  (density tolerance, flow calibration) once you have a real measurement.
- A slicer's displayed weight isn't automatically ground truth — it can
  include more than just the part you're studying.
