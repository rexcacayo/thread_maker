# Printing threads in FDM: what has worked

These are results from real prints on one machine (Flashforge Adventurer 5M Pro, OrcaSlicer). Treat them as starting points, not rules: your printer, material and nozzle will move the numbers.

## Measuring a thread you want to copy

Take three measurements with calipers and a thread gauge, plus the length:

1. **Crest diameter** (outside of the male thread).
2. **Root diameter** (bottom of the groove). Do not skip this one.
3. **Pitch**, and whether the 55° or the 60° gauge seats better.

Inferring the root from the diameter and pitch assuming a 60° standard profile has failed more than once: on one part the inferred groove was 1.25 mm deep and the real one was 0.55 mm, and nothing fitted.

Other things to check:

- Do not assume a standard. A tripod-style thread turned out to be 6 mm with 1.5 mm pitch, not 1/4"-20.
- Calipers read small in small threaded holes. Trust the male measurement more.
- Count the starts at the end of the thread. Caps and jars usually have more than one.
- Measure the diameter at two points along the thread. If it changes, the thread is tapered.

## Identifying an unknown female thread

When you cannot measure the root, print a tester instead of the whole part: a few short male stubs (a knob plus 4.5 mm of thread), each with a candidate thread and a number of notches to tell them apart. It prints in about 20 minutes.

Example: an airbrush air inlet that downloadable models describe as G 1/16. The hole measured 6.15 mm with calipers, which is the minor diameter of M7 x 0.75, not G 1/16 (6.56 mm). A tester with both candidates confirmed M7 x 0.75. The printed male that fitted perfectly was 6.85 mm crest, 5.95 mm root (PLA, 0.4 mm nozzle, 0.12 mm layers).

## Clearance

- Calibrate the printer first, so a 10 mm cylinder measures 10 mm. Then the thread clearance is a small, nearly constant number.
- Printed against printed: start at 0.2 to 0.25 mm radial.
- Printed female on a metal male (G 1/16, 28 TPI, PLA, 0.4 mm nozzle, 0.12 mm layers): fitted well with no added clearance.
- Printed male into a metal female (1/4"-20 UNC, 0.6 mm nozzle): 0.20 mm radial clearance worked; 0.10 and 0.15 did not go in properly.
- Search in 0.1 mm steps near a value that almost works, not in 0.5 mm steps.

## Flank angle

For threads where both parts are printed, 45° flanks with 0.25 mm radial clearance printed cleanly (PETG, 0.6 mm nozzle, 0.2 mm layers). The same thread at 60° with 0.12 mm clearance did not work.

When one side is an existing metal thread, keep its real angle.

## Nozzle and pitch

The tooth cannot be narrower than the extrusion line.

- Pitch 1 mm with a 0.6 mm nozzle failed: the slicer rounded the tooth, the thread came out about 0.7 mm undersize and slipped under load.
- Pitch 0.9 mm (28 TPI) with a 0.4 mm nozzle and 0.12 mm layers worked.
- For pitch of 1 mm or less, use a 0.4 mm nozzle or smaller.

## Slicer settings that worked

Coarse threads, PETG, 0.6 mm nozzle:

- 0.2 mm layers (0.36 mm layers failed), Arachne walls, 3 walls, outer wall at 40 mm/s, 5 mm brim, printed upright with no supports.

Fine threads (28 TPI), PLA, 0.4 mm nozzle:

- 0.12 mm layers, 4 walls, classic walls with precise outer wall, outer wall first at 40 mm/s, elephant foot compensation 0.1 mm, no XY compensation.

General:

- Thread axis vertical.
- No supports inside the thread.
- Check that the filament profile matches the loaded filament. PLA printed with a PETG profile gave correct dimensions but heavy stringing.

## Small threads

Below about M6 to M8, a printed thread is rarely worth it for parts that take load. Use a heat-set insert, a captive nut, or a self-tapping screw.
