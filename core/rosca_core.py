# Nucleo del generador de roscas para Fusion (fase 1).
# Rosca de perfil propio como solido nativo: dos helices (trayectoria + guia) y barrido de corte.
# Unidades de entrada en mm; la API de Fusion trabaja en cm.
import math
import adsk.core
import adsk.fusion

MM = 0.1
MIN_PLANO = 0.05      # plano minimo de cresta/fondo (mm): una V en punta no se puede barrer ni imprimir
SOBRANTE = 0.3        # cuanto sale la herramienta de corte por fuera del material (mm)


class RoscaError(Exception):
    pass


def perfil(cresta_d, fondo_d, paso, angulo, holgura=0.0, hembra=False, reparto_fondo=2.0 / 3.0):
    """Calcula el perfil del surco.

    cresta_d / fondo_d: diametros medidos de la rosca MACHO de referencia (exterior y fondo).
    Para hembra se usan los mismos dos diametros: el agujero queda en fondo_d y el surco llega a cresta_d.
    holgura: radial, en mm. Macho encoge, hembra crece.
    Devuelve dict con radios y anchos del surco de corte.
    """
    if cresta_d <= fondo_d:
        raise RoscaError("El diametro de cresta debe ser mayor que el de fondo")
    h = math.radians(angulo / 2.0)
    r_ext = cresta_d / 2.0
    r_int = fondo_d / 2.0
    prof = r_ext - r_int
    vano = 2.0 * math.tan(h) * prof           # lo que abren los dos flancos
    resto = paso - vano                       # a repartir entre plano de fondo y plano de cresta
    if resto < 2 * MIN_PLANO:
        prof_max = (paso - 2 * MIN_PLANO) / (2.0 * math.tan(h))
        raise RoscaError(
            "Surco demasiado profundo para este paso y angulo: maximo %.2f mm de profundidad (pedido %.2f)"
            % (prof_max, prof))
    # macho: el surco tiene el plano estrecho en el fondo (r_int) y la boca en r_ext
    # hembra: el surco tiene el plano estrecho en r_ext y la boca en el agujero (r_int)
    if not hembra:
        plano_fondo = max(MIN_PLANO, resto * reparto_fondo)
        plano_cresta = resto - plano_fondo
        r_fondo = r_int - holgura
        r_boca = r_ext - holgura
    else:
        plano_fondo = max(MIN_PLANO, resto * (1.0 - reparto_fondo))
        plano_cresta = resto - plano_fondo
        r_fondo = r_ext + holgura
        r_boca = r_int + holgura
    return {
        "hembra": hembra, "paso": paso, "angulo": angulo, "prof": prof,
        "r_fondo": r_fondo, "r_boca": r_boca,
        "w_fondo": plano_fondo, "w_boca": paso - plano_cresta,
        "plano_fondo": plano_fondo, "plano_cresta": plano_cresta,
    }


def cortar_rosca(comp, cuerpo, pf, z_ini, z_fin, entradas=1, izquierda=False, ox=0.0, sal_ini=True, sal_fin=True):
    """Corta el surco helicoidal en `cuerpo`. Eje paralelo a Z pasando por (ox, 0). Devuelve las features."""
    tm = adsk.fusion.TemporaryBRepManager.get()
    paso = pf["paso"]
    avance = paso * entradas
    r_f = pf["r_fondo"]
    r_b = pf["r_boca"]
    # sobrante: macho hacia fuera (+), hembra hacia dentro (-)
    r_s = r_b + (SOBRANTE if not pf["hembra"] else -SOBRANTE)
    if r_s <= 0.2:
        r_s = max(0.2, r_b * 0.5)
    # sal_ini / sal_fin: el surco sale por ese extremo (extremo libre). Si hay un hombro, se queda dentro.
    margen = pf["w_boca"] / 2.0 + 0.02
    z_bajo = z_ini - avance if sal_ini else z_ini + margen
    z_alto = z_fin + avance if sal_fin else z_fin - margen
    vueltas = (z_alto - z_bajo) / avance
    lejos_libre = sal_ini if izquierda else sal_fin
    eje_p = adsk.core.Point3D.create(ox * MM, 0, 0)
    eje_v = adsk.core.Vector3D.create(0, 0, 1)
    feats = []
    helices = []
    for k in range(entradas):
        if not izquierda:
            z0 = z_bajo + k * paso
            pitch = avance * MM
        else:
            z0 = z_alto - k * paso
            pitch = -avance * MM
        vk = vueltas if lejos_libre else vueltas - k * paso / avance
        bf = comp.features.baseFeatures.add()
        bf.startEdit()
        for r in (r_f, r_s):
            w = tm.createHelixWire(eje_p, eje_v, adsk.core.Point3D.create((ox + r) * MM, 0, z0 * MM), pitch, vk, 0)
            comp.bRepBodies.add(w, bf)
        bf.finishEdit()
        hb = [bf.bodies.item(i) for i in range(bf.bodies.count)]
        helices.extend(hb)
        camino = comp.features.createPath(hb[0].edges.item(0), False)
        guia = comp.features.createPath(hb[1].edges.item(0), False)

        sk = comp.sketches.add(comp.xZConstructionPlane)

        def pt(r, z):
            return sk.modelToSketchSpace(adsk.core.Point3D.create((ox + r) * MM, 0, z * MM))

        wf = pf["w_fondo"] / 2.0
        wb = pf["w_boca"] / 2.0
        # fondo -> flancos hasta la boca -> tramo recto hasta el sobrante (nunca supera el paso)
        pts = [pt(r_f, z0 - wf), pt(r_f, z0 + wf), pt(r_b, z0 + wb), pt(r_s, z0 + wb), pt(r_s, z0 - wb), pt(r_b, z0 - wb)]
        ln = sk.sketchCurves.sketchLines
        for i in range(len(pts)):
            ln.addByTwoPoints(pts[i], pts[(i + 1) % len(pts)])
        si = comp.features.sweepFeatures.createInput(sk.profiles.item(0), camino, adsk.fusion.FeatureOperations.CutFeatureOperation)
        si.guideRail = guia
        si.participantBodies = [cuerpo]
        feats.append(comp.features.sweepFeatures.add(si))
    for h in helices:
        h.isLightBulbOn = False
    return feats


def _cilindro(comp, r, z_ini, z_fin, ox, op, participantes=None):
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(ox * MM, 0, 0), r * MM)
    ei = comp.features.extrudeFeatures.createInput(sk.profiles.item(0), op)
    ei.startExtent = adsk.fusion.OffsetStartDefinition.create(adsk.core.ValueInput.createByReal(z_ini * MM))
    ei.setDistanceExtent(False, adsk.core.ValueInput.createByReal((z_fin - z_ini) * MM))
    if participantes:
        ei.participantBodies = participantes
    return comp.features.extrudeFeatures.add(ei)


def _chaflan_circulos(comp, cuerpo, radio, dist, tol=0.02, z=None):
    col = adsk.core.ObjectCollection.create()
    for e in cuerpo.edges:
        g = e.geometry
        if g.curveType == adsk.core.Curve3DTypes.Circle3DCurveType and abs(g.radius / MM - radio) < tol and (z is None or abs(g.center.z / MM - z) < tol):
            col.add(e)
    if col.count == 0:
        return None
    ci = comp.features.chamferFeatures.createInput2()
    ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(col, adsk.core.ValueInput.createByReal(dist * MM), False)
    return comp.features.chamferFeatures.add(ci)


def rosca_macho(comp, cresta_d, fondo_d, paso, angulo, largo, holgura=0.0, entradas=1, izquierda=False,
                chaflan=True, ox=0.0, nombre=None):
    pf = perfil(cresta_d, fondo_d, paso, angulo, holgura, hembra=False)
    ext = _cilindro(comp, pf["r_boca"], 0.0, largo, ox, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    cuerpo = ext.bodies.item(0)
    if chaflan:
        _chaflan_circulos(comp, cuerpo, pf["r_boca"], pf["prof"])
    cortar_rosca(comp, cuerpo, pf, 0.0, largo, entradas, izquierda, ox)
    if nombre:
        cuerpo.name = nombre
    return cuerpo, pf


def rosca_hembra(comp, cresta_d, fondo_d, paso, angulo, largo, holgura=0.0, entradas=1, izquierda=False,
                 chaflan=True, ox=0.0, exterior_d=None, nombre=None):
    """Casquillo cilindrico con rosca hembra (para probar el nucleo; la colocacion en un cuerpo existente es fase 2)."""
    pf = perfil(cresta_d, fondo_d, paso, angulo, holgura, hembra=True)
    if exterior_d is None:
        exterior_d = cresta_d + 2 * holgura + 8.0
    ext = _cilindro(comp, exterior_d / 2.0, 0.0, largo, ox, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    cuerpo = ext.bodies.item(0)
    _cilindro(comp, pf["r_boca"], 0.0, largo, ox, adsk.fusion.FeatureOperations.CutFeatureOperation, [cuerpo])
    if chaflan:
        _chaflan_circulos(comp, cuerpo, pf["r_boca"], pf["prof"])
    cortar_rosca(comp, cuerpo, pf, 0.0, largo, entradas, izquierda, ox)
    if nombre:
        cuerpo.name = nombre
    return cuerpo, pf
