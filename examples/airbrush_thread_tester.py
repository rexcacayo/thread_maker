# Example: thread tester for identifying an unknown female thread.
# Builds four short male stubs (4.5 mm of thread on a 12 mm knob), each with a
# candidate thread. The number of notches on the knob rim identifies the stub.
#
# Run it as a Fusion script (Utilities > Add-Ins > Scripts) on an empty design.
import math
import os
import sys

import adsk.core
import adsk.fusion

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
import rosca_core as rc  # noqa: E402

MM = 0.1

# (notches, crest diameter, root diameter, pitch, included angle)
CANDIDATES = [
    (1, 7.00, 6.10, 0.75, 60),          # M7 x 0.75
    (2, 6.85, 5.95, 0.75, 60),          # M7 x 0.75, looser
    (3, 7.72, 6.46, 25.4 / 28, 55),     # G 1/16 (28 TPI)
    (4, 7.55, 6.30, 25.4 / 28, 55),     # G 1/16, looser
]


def tester(comp, notches, ox, crest, root, pitch, angle, knob_d=12.0, knob_h=5.0, thread_h=4.5):
    ops = adsk.fusion.FeatureOperations
    pf = rc.perfil(crest, root, pitch, angle)
    body = rc._cilindro(comp, knob_d / 2, 0, knob_h, ox, ops.NewBodyFeatureOperation).bodies.item(0)
    rc._cilindro(comp, pf["r_boca"], knob_h, knob_h + thread_h, ox, ops.JoinFeatureOperation, [body])
    rc._chaflan_circulos(comp, body, pf["r_boca"], pf["prof"], z=knob_h + thread_h)
    # the thread stops at the knob shoulder (sal_ini=False) and runs out at the free tip
    rc.cortar_rosca(comp, body, pf, knob_h, knob_h + thread_h, ox=ox, sal_ini=False, sal_fin=True)
    sk = comp.sketches.add(comp.xYConstructionPlane)
    for i in range(notches):
        a = math.radians(90 + (i - (notches - 1) / 2.0) * 28)
        c = adsk.core.Point3D.create((ox + knob_d / 2 * math.cos(a)) * MM, knob_d / 2 * math.sin(a) * MM, 0)
        sk.sketchCurves.sketchCircles.addByCenterRadius(c, 0.9 * MM)
    col = adsk.core.ObjectCollection.create()
    for i in range(sk.profiles.count):
        col.add(sk.profiles.item(i))
    ei = comp.features.extrudeFeatures.createInput(col, ops.CutFeatureOperation)
    ei.setDistanceExtent(False, adsk.core.ValueInput.createByReal(knob_h * MM))
    ei.participantBodies = [body]
    comp.features.extrudeFeatures.add(ei)
    body.name = "%d - D%.2f P%.3f %ddeg" % (notches, crest, pitch, angle)
    return body


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        comp = design.rootComponent
        for i, (n, crest, root, pitch, angle) in enumerate(CANDIDATES):
            tester(comp, n, 16.0 * i, crest, root, pitch, angle)
    except Exception as e:  # noqa: BLE001
        if ui:
            ui.messageBox("Thread tester failed:\n%s" % e)
