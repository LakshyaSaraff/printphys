# printphys

**Accurate URDF physics for 3D-printed parts.**

CAD exporters compute inertia as if your part were a solid block of plastic. A printed
part is dense walls and skins around sparse infill — often 40–70% lighter than solid,
with a different mass distribution. `printphys` closes that gap: mesh + print settings
in, simulation-ready `<inertial>` out.

```bash
pip install git+https://github.com/LakshyaSaraff/printphys.git
printphys part.stl --material pla --infill 20 --pattern gyroid --walls 3
```

## What you get

- **Mass, COM, full inertia tensor** in SI units, about the COM, mesh-frame axes.
- **URDF / SDF / MJCF snippets**, or in-place patching of a link in an existing URDF.
- **Effective density** to feed back into CAD exporters (SolidWorks, Fusion, Onshape).
- **Validation loop**: pass `--weighed-mass` from a kitchen scale and printphys
  rescales outputs and reports its own estimation error.

## Where to go next

- [Quickstart](quickstart.md) — install, CLI, Python API.
- [Accuracy methodology](accuracy.md) — how each backend works and what errors to expect.

---

Copyright (c) 2026 Lakshya Saraf. Licensed under the [MIT License](../LICENSE).
