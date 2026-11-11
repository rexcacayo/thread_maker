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

Placement works like Fusion's Coil command, and it also understands existing geometry.

**Where**

- **Planar face or construction plane.** The thread comes out perpendicular to it, at the centre of the face. Untick *centre on the face* to start it where you clicked.
- **Cylindrical face or circular edge of a shaft.** The thread is carved into the existing shaft, starting at the end nearest to your click. Diameter and length are taken from the model. Bores and other features of the shaft are kept.
- **Cylindrical face or circular edge of a hole.** The thread is carved into the existing hole.
- **Curved face.** The thread comes out normal to the surface at the point you clicked.
- **Several points.** With a planar face selected, pick vertices, sketch points or circular edges: one thread is made at each. Circular edges of existing holes are threaded in place.
- **Nothing selected.** The thread is built at the origin along X, Y or Z.

**Length and direction**

Drag the arrow in the viewport to set the thread length. Drag it to the other side to flip the direction.

**Options**

- Male or female. With a body selected and *join / drill into the part* ticked, a male thread is joined to it and a female thread is cut into it as a threaded hole with a countersink. Otherwise you get a new body (for female, a test bushing).
- Standard (metric, G pipe, UNC) or free measurements: crest diameter, root diameter, pitch and flank angle. Presets hold the nominal male values.
- *Use the selected diameter*: copies the diameter and length of the shaft, hole or edge you picked.
- *Smooth shank / extra hole depth*: for a male thread, an unthreaded length between the part and the thread; for a threaded hole, plain hole depth beyond the thread.
- Radial clearance, number of starts, handedness and chamfer.

**Info box.** Says what will be built, groove depth, crest and root flats, estimated time and printing warnings. OK is disabled when the profile is impossible.

**Preview.** A plain cylinder with the diameter and length of the thread at each position. The real thread is computed when you press OK, because it takes several seconds.

**Fixing a mistake.** The whole thread is one undo step and one collapsed group in the timeline. The dialog remembers the last values, so undo, reopen, change the number and press OK.

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
- **Bodies inside a moved or rotated component are not supported yet.** The add-in stops with a message. Thread the part in the root component, or before moving the component.
- A thread cannot be edited afterwards as a single feature. Undo and redo it; the dialog keeps your values.
- The preview is a plain cylinder, not the thread itself.
- On curved faces the thread base is flat, so the countersink and the joint follow the tangent plane, not the surface.
- No tapered threads yet (BSPT, NPT).
- Crests and roots are flat. Rounded Whitworth crests are not modelled.

## Roadmap

1. ~~Core: custom-profile male and female thread on a plane.~~ Done.
2. ~~Place on a plane or face, join to a body, cut a threaded hole, thread existing shafts and holes, several positions at once.~~ Done. Still to do: bodies inside moved components.
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
