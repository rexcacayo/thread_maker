# thread_maker

Fusion add-in that builds printable threads with a custom profile: fasteners and pipe threads, male and female, any pitch, angle and groove depth, with FDM clearance built in.

> **Status: early development.** The add-in has a working dialog: pick a plane or face, type the measurements, and it builds the thread as a new body, joins a male thread to your part, or cuts a threaded hole into it. See [Roadmap](#roadmap).

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

## Install

1. Download this repository and copy the `ThreadMaker` folder into Fusion's add-ins folder:
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`
2. In Fusion, open `Utilities > Add-Ins > Scripts and Add-Ins`, select **ThreadMaker** in the Add-Ins tab and press **Run**.
3. The **Thread Maker** button appears in the `Solid > Create` panel.

## Using the dialog

It works like Fusion's Coil command:

1. Select a planar face or a construction plane. The thread comes out perpendicular to it, at the centre of the face. Untick *centre on the face* to start it where you clicked, or pick a vertex or sketch point.
2. Drag the arrow in the viewport to set the length. Drag it to the other side to flip the direction.
3. With no selection, the thread is built at the origin along the axis you choose (X, Y or Z).
4. Choose male or female. With a face selected and *join / drill into the part* ticked, a male thread is joined to that body and a female thread is cut into it as a threaded hole with a countersink. Otherwise you get a new body (for female, a test bushing with the outer diameter you set).
5. Pick a standard (metric, G pipe, UNC) to fill in the numbers, or leave it on free and type your own crest diameter, root diameter, pitch and flank angle. Presets hold the nominal male values.
6. Set radial clearance, number of starts, handedness and chamfer.
7. Read the info box: what will be built, groove depth, crest and root flats, estimated time and printing warnings. OK is disabled when the profile is impossible.

The preview is a plain cylinder with the diameter and length of the thread. The real thread is computed when you press OK, because it takes several seconds.

The dialog text is in Spanish for now.

## Using the core from a script

```python
import rosca_core as rc

# M10 x 1.5 male, 20 mm long, 0.2 mm radial clearance
body, profile = rc.rosca_macho(root_component, cresta_d=10.0, fondo_d=8.376,
                               paso=1.5, angulo=60, largo=20, holgura=0.2)
```

Units are millimetres. Function and parameter names are currently in Spanish (`cresta` = crest, `fondo` = root, `paso` = pitch, `angulo` = angle, `largo` = length, `holgura` = clearance, `entradas` = starts, `izquierda` = left-hand). They will move to English before the first release. `examples/airbrush_thread_tester.py` shows a thread that stops at a shoulder.

## Known limits

- **Slow.** About 1.4 s per thread turn. A long fine thread can take over a minute.
- Threading an existing cylindrical face (a shaft or a plain hole already in the model) is not done yet. Use a planar face instead.
- The preview is a plain cylinder, not the thread itself.
- No tapered threads yet (BSPT, NPT).
- Crests and roots are flat. Rounded Whitworth crests are not modelled.

## Roadmap

1. ~~Core: custom-profile male and female thread on a plane.~~ Done.
2. ~~Place on a plane or face, join to a body, cut a threaded hole.~~ Done. Still to do: thread an existing cylindrical face.
3. Recognise the thread from measurements (metric, UNC/UNF, BSW, BSP) and warn when nozzle or layer height cannot resolve the pitch.
4. Pipe threads: parallel (G) and tapered (BSPT, NPT).
5. Complete parts (hex nut, bolt, fittings), a clearance calibration test, in-dialog help, English UI.

Done so far besides the core: the add-in dialog with presets, info box and warnings.

## Printing threads

Notes from real prints are in [docs/printing_threads.md](docs/printing_threads.md).

## Contributing

Issues and pull requests are welcome, especially test results: which thread, material, nozzle, layer height and clearance worked for you.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
