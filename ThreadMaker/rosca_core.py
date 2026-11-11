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


def cortar_rosca(comp, cuerpo, pf, z_ini, z_fin, entradas=1, izquierda=False, ox=0.0, sal_ini=True, sal_fin=True,
                 herramienta=False, sobrante=None):
    """Corta el surco helicoidal en `cuerpo`. Eje paralelo a Z pasando por (ox, 0). Devuelve las features.
    Con herramienta=True no corta nada: devuelve los cuerpos del surco, para restarlos despues donde haga falta."""
    tm = adsk.fusion.TemporaryBRepManager.get()
    paso = pf["paso"]
    avance = paso * entradas
    r_f = pf["r_fondo"]
    r_b = pf["r_boca"]
    # sobrante: macho hacia fuera (+), hembra hacia dentro (-)
    sob = SOBRANTE if sobrante is None else sobrante
    r_s = r_b + (sob if not pf["hembra"] else -sob)
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
        ops = adsk.fusion.FeatureOperations
        si = comp.features.sweepFeatures.createInput(
            sk.profiles.item(0), camino, ops.NewBodyFeatureOperation if herramienta else ops.CutFeatureOperation)
        si.guideRail = guia
        if not herramienta:
            si.participantBodies = [cuerpo]
        f = comp.features.sweepFeatures.add(si)
        feats.append(f.bodies.item(0) if herramienta else f)
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


# ---------------------------------------------------------------------------
# Colocacion: la rosca se construye en el origen (eje Z) y despues se lleva
# al plano elegido y, si se pide, se une o se resta al cuerpo de destino.
# ---------------------------------------------------------------------------

def _marco(origen, eje):
    """Matriz que lleva el sistema de construccion (origen, eje Z) a un punto y una direccion (cm)."""
    z = eje.copy()
    z.normalize()
    ref = adsk.core.Vector3D.create(1, 0, 0)
    if abs(z.dotProduct(ref)) > 0.9:
        ref = adsk.core.Vector3D.create(0, 1, 0)
    y = z.crossProduct(ref)
    y.normalize()
    x = y.crossProduct(z)
    x.normalize()
    m = adsk.core.Matrix3D.create()
    m.setWithCoordinateSystem(origen, x, y, z)
    return m


def _es_identidad(origen, eje):
    z = eje.copy()
    z.normalize()
    return origen.distanceTo(adsk.core.Point3D.create(0, 0, 0)) < 1e-7 and z.dotProduct(adsk.core.Vector3D.create(0, 0, 1)) > 1 - 1e-9


def _mover(comp, cuerpo, origen, eje):
    if origen is None or eje is None or _es_identidad(origen, eje):
        return None
    col = adsk.core.ObjectCollection.create()
    col.add(cuerpo)
    mi = comp.features.moveFeatures.createInput2(col)
    mi.defineAsFreeMove(_marco(origen, eje))
    return comp.features.moveFeatures.add(mi)


def _combinar(comp, destino, herramienta, operacion):
    col = adsk.core.ObjectCollection.create()
    for h in (herramienta if isinstance(herramienta, (list, tuple)) else [herramienta]):
        col.add(h)
    ci = comp.features.combineFeatures.createInput(destino, col)
    ci.operation = operacion
    ci.isKeepToolBodies = False
    return comp.features.combineFeatures.add(ci)


def macho_en(comp, cresta_d, fondo_d, paso, angulo, largo, holgura=0.0, entradas=1, izquierda=False,
             chaflan=True, origen=None, eje=None, unir_a=None, nombre=None, liso=0.0, solape=None):
    """Rosca macho que sale de un plano. origen (Point3D, cm) y eje (Vector3D) situan la base.
    Si unir_a es un cuerpo, la rosca se une a el y el surco muere en el plano (hombro).
    liso: tramo sin rosca entre el plano y el comienzo del filete.
    solape: cuanto entra el macho en la pieza para unirse (mas en caras curvas)."""
    pf = perfil(cresta_d, fondo_d, paso, angulo, holgura, hembra=False)
    if solape is None:
        solape = 0.3
    solape = solape if unir_a else 0.0
    hombro = bool(unir_a) or liso > 0
    alto = liso + largo
    ext = _cilindro(comp, pf["r_boca"], -solape, alto, 0.0, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    cuerpo = ext.bodies.item(0)
    if chaflan:
        _chaflan_circulos(comp, cuerpo, pf["r_boca"], pf["prof"], z=(alto if hombro else None))
    cortar_rosca(comp, cuerpo, pf, liso, alto, entradas, izquierda, 0.0, sal_ini=not hombro, sal_fin=True)
    _mover(comp, cuerpo, origen, eje)
    if unir_a:
        _combinar(comp, unir_a, cuerpo, adsk.fusion.FeatureOperations.JoinFeatureOperation)
        return unir_a, pf
    if nombre:
        cuerpo.name = nombre
    return cuerpo, pf


def hembra_en(comp, destino, cresta_d, fondo_d, paso, angulo, largo, holgura=0.0, entradas=1, izquierda=False,
              chaflan=True, origen=None, eje=None, extra=0.0, sobre=0.5):
    """Taladro roscado dentro de `destino`. origen esta en la cara y eje apunta HACIA DENTRO del cuerpo.
    Se construye el macho de la cavidad (agujero + filete) y se resta.
    extra: taladro liso mas alla del final de la rosca (taladro ciego mas profundo).
    sobre: cuanto sobresale la herramienta por fuera de la cara (mas en caras curvas)."""
    pf = perfil(cresta_d, fondo_d, paso, angulo, holgura, hembra=True)
    pm = perfil(cresta_d + 2 * holgura, fondo_d + 2 * holgura, paso, angulo, 0.0, hembra=False)
    ops = adsk.fusion.FeatureOperations
    macho = _cilindro(comp, pm["r_boca"], -sobre, largo, 0.0, ops.NewBodyFeatureOperation).bodies.item(0)
    cortar_rosca(comp, macho, pm, -sobre, largo, entradas, izquierda, 0.0, True, True)
    if extra > 0:                                     # el tramo extra va al diametro del agujero, sin filete
        # 0,02 mm mas de radio: si coincide con el fondo del filete, la union deja esquirlas sueltas
        _cilindro(comp, pm["r_fondo"] + 0.02, largo - 0.2, largo + extra, 0.0, ops.JoinFeatureOperation, [macho])
    if chaflan:
        # avellanado a 45 grados: del diametro mayor en la cara al agujero
        tm = adsk.fusion.TemporaryBRepManager.get()
        r_cara = pm["r_boca"] + 0.1
        cono = tm.createCylinderOrCone(
            adsk.core.Point3D.create(0, 0, -sobre * MM), (r_cara + sobre) * MM,
            adsk.core.Point3D.create(0, 0, (r_cara - pm["r_fondo"]) * MM), pm["r_fondo"] * MM)
        bf = comp.features.baseFeatures.add()
        bf.startEdit()
        comp.bRepBodies.add(cono, bf)
        bf.finishEdit()
        _combinar(comp, macho, bf.bodies.item(0), ops.JoinFeatureOperation)
    _mover(comp, macho, origen, eje)
    _combinar(comp, destino, macho, ops.CutFeatureOperation)
    return destino, pf


def rosca_en_eje(comp, cuerpo, radio_eje, cresta_d, fondo_d, paso, angulo, largo, holgura=0.0, entradas=1,
                 izquierda=False, chaflan=True, origen=None, eje=None):
    """Rosca macho tallada en un eje cilindrico que ya existe en `cuerpo`.
    origen: centro del extremo libre (cm). eje: direccion hacia dentro del eje. radio_eje en mm.
    No rehace el eje: resta el surco, y lo que sobre de diametro, asi se conserva lo demas (taladros, chaveteros)."""
    pf = perfil(cresta_d, fondo_d, paso, angulo, holgura, hembra=False)
    if pf["r_boca"] > radio_eje + 1e-4:
        raise RoscaError("La cresta pedida (%.2f mm) es mayor que el eje (%.2f mm)" % (2 * pf["r_boca"], 2 * radio_eje))
    resto = radio_eje - pf["r_boca"]                  # material a quitar para llegar a la cresta
    herr = cortar_rosca(comp, None, pf, 0.0, largo, entradas, izquierda, 0.0, sal_ini=True, sal_fin=False,
                        herramienta=True, sobrante=resto + 0.3)
    for h in herr:
        _mover(comp, h, origen, eje)
    tm = adsk.fusion.TemporaryBRepManager.get()
    dif = adsk.fusion.BooleanTypes.DifferenceBooleanType
    P = lambda z: adsk.core.Point3D.create(0, 0, z * MM)   # noqa: E731
    temporales = []
    R = radio_eje + 1.0
    if resto > 1e-3:                                  # tubo que rebaja el eje hasta la cresta
        tubo = tm.createCylinderOrCone(P(-0.2), R * MM, P(largo), R * MM)
        tm.booleanOperation(tubo, tm.createCylinderOrCone(P(-1.0), pf["r_boca"] * MM, P(largo + 1.0), pf["r_boca"] * MM), dif)
        temporales.append(tubo)
    if chaflan:                                       # anillo que deja un cono de entrada a 45 grados
        prof = pf["prof"]
        z0 = -min(0.5, max(0.0, pf["r_boca"] - prof - 0.05))
        anillo = tm.createCylinderOrCone(P(z0), R * MM, P(prof), R * MM)
        tm.booleanOperation(anillo, tm.createCylinderOrCone(P(z0), (pf["r_boca"] - prof + z0) * MM, P(prof), pf["r_boca"] * MM), dif)
        temporales.append(anillo)
    if temporales:
        m = _marco(origen, eje) if (origen is not None and eje is not None) else None
        bf = comp.features.baseFeatures.add()
        bf.startEdit()
        for t in temporales:
            if m is not None:
                tm.transform(t, m)
            comp.bRepBodies.add(t, bf)
        bf.finishEdit()
        herr = list(herr) + [bf.bodies.item(i) for i in range(bf.bodies.count)]
    _combinar(comp, cuerpo, herr, adsk.fusion.FeatureOperations.CutFeatureOperation)
    return cuerpo, pf


def rosca_en_agujero(comp, cuerpo, radio_agujero, cresta_d, fondo_d, paso, angulo, largo, holgura=0.0, entradas=1,
                     izquierda=False, chaflan=True, origen=None, eje=None):
    """Rosca hembra tallada en un agujero cilindrico que ya existe en `cuerpo`.
    origen: centro de la boca del agujero (cm). eje: direccion hacia dentro. radio_agujero en mm.
    No rehace el taladro (restar un cilindro igual al que ya hay falla): resta solo el filete,
    y ensancha el agujero unicamente si es mas estrecho que la rosca."""
    pf = perfil(cresta_d, fondo_d, paso, angulo, holgura, hembra=True)
    if radio_agujero >= pf["r_fondo"] - 0.05:
        raise RoscaError("El agujero (%.2f mm) es demasiado grande para esta rosca (fondo %.2f mm)"
                         % (2 * radio_agujero, 2 * pf["r_fondo"]))
    falta = pf["r_boca"] - radio_agujero              # >0: hay que ensanchar el agujero
    herr = cortar_rosca(comp, None, pf, 0.0, largo, entradas, izquierda, 0.0, sal_ini=True, sal_fin=False,
                        herramienta=True, sobrante=max(0.3, falta + 0.3))
    for h in herr:
        _mover(comp, h, origen, eje)
    tm = adsk.fusion.TemporaryBRepManager.get()
    P = lambda z: adsk.core.Point3D.create(0, 0, z * MM)   # noqa: E731
    temporales = []
    r_final = max(radio_agujero, pf["r_boca"])
    if falta > 0.02:
        temporales.append(tm.createCylinderOrCone(P(-0.5), pf["r_boca"] * MM, P(largo), pf["r_boca"] * MM))
    if chaflan:                                       # avellanado a 45 grados; acaba 0,05 dentro del hueco
        r_cara = pf["r_fondo"] + 0.1
        r_fin = max(0.05, r_final - 0.05)
        temporales.append(tm.createCylinderOrCone(P(-0.5), (r_cara + 0.5) * MM, P(r_cara - r_fin), r_fin * MM))
    if temporales:
        m = _marco(origen, eje) if (origen is not None and eje is not None) else None
        bf = comp.features.baseFeatures.add()
        bf.startEdit()
        for t in temporales:
            if m is not None:
                tm.transform(t, m)
            comp.bRepBodies.add(t, bf)
        bf.finishEdit()
        herr = list(herr) + [bf.bodies.item(i) for i in range(bf.bodies.count)]
    _combinar(comp, cuerpo, herr, adsk.fusion.FeatureOperations.CutFeatureOperation)
    return cuerpo, pf
