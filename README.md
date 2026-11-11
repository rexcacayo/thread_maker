# thread_maker

Fusion add-in that builds printable threads with a custom profile: fasteners and pipe threads, male and female, any pitch, angle and groove depth, with FDM clearance built in.

> **Status: early development.** The geometry core works and is validated inside Fusion. There is no dialog or toolbar button yet, so today it is a Python module you call from a script. See [Roadmap](#roadmap).

## Why

Fusion's built-in thread feature gives you the textbook profile of a standard and nothing else. That is rarely what you need when you are 3D printing or copying a part:

- A nominal ISO thread printed in FDM usually does not screw in. It needs clearance, and often a different flank angle.
- Real parts are not always standard. Copying a thread from a broken part means working from what you measured: crest, root and pitch.
- You cannot make the groove deeper, change the angle, or add starts.

thread_maker models the thread from measurements instead of from a standard name, and produces a native Fusion solid (not a mesh).

## What the core does today

- Male and female threads from four numbers: crest diameter, root diameter, pitch and included flank angle.
- Any angle (60°, 55°, 45° for printing, or anything else).
- Radial clearance: the male shrinks, the female grows.
- Multi-start threads and left-hand threads.
- Lead-in chamfer.
- Threads that stop at a shoulder or run out at a free end.
- Refuses impossible profiles and tells you the maximum groove depth for that pitch and angle.

Tested in Fusion with: M10x1.5 male and female, M6x1, BSW 1/2"-12 at 55°, a left-hand M10, a two-start 20 mm thread with 2 mm pitch, and a 45° printable profile.

## How it works

Sweeping a profile along a single helix in Fusion self-intersects after the first turn. The core avoids that by building two helices with `TemporaryBRepManager.createHelixWire`, one at the groove root (the sweep path) and one outside the material (the guide rail), and cutting the groove with a guided sweep. The cutting profile follows the flanks up to the surface and then continues straight, so it never overlaps the next turn.

## Using it now

There is no installer yet. To try it:

1. Clone or download this repository.
2. In Fusion, open `Utilities > Add-Ins > Scripts and Add-Ins`, add `examples/airbrush_thread_tester.py` as a script and run it on an empty design.

Calling the core from your own script:

```python
import rosca_core as rc

# M10 x 1.5 male, 20 mm long, 0.2 mm radial clearance
body, profile = rc.rosca_macho(root_component, cresta_d=10.0, fondo_d=8.376,
                               paso=1.5, angulo=60, largo=20, holgura=0.2)
```

Units are millimetres. The function and parameter names are currently in Spanish (`cresta` = crest, `fondo` = root, `paso` = pitch, `angulo` = angle, `largo` = length, `holgura` = clearance, `entradas` = starts, `izquierda` = left-hand). They will move to English before the first release.

## Known limits

- **Slow.** About 1.4 s per thread turn. A long fine thread can take over a minute.
- The female helper only makes a test bushing. Cutting a thread into an existing body or onto an existing cylindrical face is not done yet.
- No tapered threads yet (BSPT, NPT).
- Crests and roots are flat. Rounded Whitworth crests are not modelled.

## Roadmap

1. ~~Core: custom-profile male and female thread on a plane.~~ Done.
2. Thread an existing cylindrical face, and cut a female thread inside an existing body.
3. Recognise the thread from measurements (metric, UNC/UNF, BSW, BSP) and warn when nozzle or layer height cannot resolve the pitch.
4. Pipe threads: parallel (G) and tapered (BSPT, NPT).
5. Complete parts (hex nut, bolt, fittings), a clearance calibration test, in-dialog help, and the add-in dialog itself.

## Printing threads

Notes from real prints are in [docs/printing_threads.md](docs/printing_threads.md).

## Contributing

Issues and pull requests are welcome, especially test results: which thread, material, nozzle, layer height and clearance worked for you.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
