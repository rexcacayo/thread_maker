# Thread Maker - Fusion add-in.
# Dialog to build a printable thread (male or female) from measurements.
# The dialog text is in Spanish for now; the file is UTF-8.
import importlib
import json
import math
import os
import sys
import traceback

import adsk.core
import adsk.fusion

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)
import rosca_core  # noqa: E402

CMD_ID = "threadMakerCmd"
CMD_NAME = "Thread Maker"
CMD_TIP = "Rosca imprimible de perfil propio (macho o hembra) a partir de medidas."
PANEL_ID = "SolidCreatePanel"
SEG_POR_VUELTA = 1.4

LIBRE = "Libre (medidas propias)"


def _metrica(d, p):
    return (d, d - 1.0825 * p, p, 60.0)


def _gas(d, tpi):
    p = 25.4 / tpi
    return (d, d - 1.2806 * p, p, 55.0)


def _unc(d, tpi):
    p = 25.4 / tpi
    return (d, d - 1.0825 * p, p, 60.0)


# nombre -> (cresta, fondo, paso, angulo) del macho nominal, en mm
NORMAS = [
    (LIBRE, None),
    ("M5 x 0,8", _metrica(5, 0.8)),
    ("M6 x 1", _metrica(6, 1.0)),
    ("M7 x 0,75 (fina, aerógrafos)", _metrica(7, 0.75)),
    ("M8 x 1,25", _metrica(8, 1.25)),
    ("M8 x 1 (fina)", _metrica(8, 1.0)),
    ("M10 x 1,5", _metrica(10, 1.5)),
    ("M10 x 1 (fina)", _metrica(10, 1.0)),
    ("M12 x 1,75", _metrica(12, 1.75)),
    ("M16 x 2", _metrica(16, 2.0)),
    ("M20 x 2,5", _metrica(20, 2.5)),
    ("G 1/16 (28 hilos)", _gas(7.723, 28)),
    ("G 1/8 (28 hilos)", _gas(9.728, 28)),
    ("G 1/4 (19 hilos)", _gas(13.157, 19)),
    ("G 3/8 (19 hilos)", _gas(16.662, 19)),
    ("G 1/2 (14 hilos)", _gas(20.955, 14)),
    ("G 3/4 (14 hilos)", _gas(26.441, 14)),
    ("1/4\"-20 UNC", _unc(6.35, 20)),
    ("5/16\"-18 UNC", _unc(7.938, 18)),
    ("3/8\"-16 UNC", _unc(9.525, 16)),
    ("1/2\"-13 UNC", _unc(12.7, 13)),
]
_NORMAS = dict(NORMAS)

_handlers = []


def _ui():
    return adsk.core.Application.get().userInterface


EJES = {"Z": (0, 0, 1), "X": (1, 0, 0), "Y": (0, 1, 0)}
_MEMO = os.path.join(_DIR, "settings.json")


# ---------------------------------------------------------------------------
# Colocacion: de la seleccion a "donde nace la rosca y hacia donde sale"
# ---------------------------------------------------------------------------

def _cil_info(cara):
    """Datos de una cara cilindrica: eje, radio (mm), extension y si es un agujero."""
    cil = adsk.core.Cylinder.cast(cara.geometry)
    if not cil:
        return None
    eje = cil.axis.copy()
    eje.normalize()
    org = cil.origin
    ts = []
    for e in cara.edges:
        for vtx in (e.startVertex, e.endVertex):
            if vtx:
                ts.append(org.vectorTo(vtx.geometry).dotProduct(eje))
    if len(ts) < 2 or max(ts) - min(ts) < 1e-6:
        bb = cara.boundingBox
        ts = [org.vectorTo(q).dotProduct(eje) for q in (bb.minPoint, bb.maxPoint)]
    q = cara.pointOnFace
    _, nn = cara.evaluator.getNormalAtPoint(q)
    v = org.vectorTo(q)
    k = v.dotProduct(eje)
    radial = adsk.core.Vector3D.create(v.x - eje.x * k, v.y - eje.y * k, v.z - eje.z * k)
    return {"org": org, "eje": eje, "R": cil.radius * 10.0, "tmin": min(ts), "tmax": max(ts),
            "agujero": nn.dotProduct(radial) < 0}


def _desde_cilindro(cara, ci, p_ref):
    """Eje o agujero existente: la rosca empieza en el extremo mas cercano a p_ref y va hacia el otro."""
    t = ci["org"].vectorTo(p_ref).dotProduct(ci["eje"])
    en_min = abs(t - ci["tmin"]) <= abs(t - ci["tmax"])
    t0 = ci["tmin"] if en_min else ci["tmax"]
    e = ci["eje"]
    o = adsk.core.Point3D.create(ci["org"].x + e.x * t0, ci["org"].y + e.y * t0, ci["org"].z + e.z * t0)
    fuera = e.copy()
    if en_min:
        fuera.scaleBy(-1)                 # "fuera" apunta alejandose del cilindro
    return {"o": o, "fuera": fuera, "cuerpo": cara.body, "modo": "agujero" if ci["agujero"] else "eje",
            "radio": ci["R"], "largo": (ci["tmax"] - ci["tmin"]) * 10.0, "plana": True, "puntos": [o],
            "radios": [ci["R"] if ci["agujero"] else None]}


def _proyectar(p, o, n):
    d = o.vectorTo(p).dotProduct(n)
    return adsk.core.Point3D.create(p.x - n.x * d, p.y - n.y * d, p.z - n.z * d)


def _punto_de(ent):
    v = adsk.fusion.BRepVertex.cast(ent)
    if v:
        return v.geometry
    sp = adsk.fusion.SketchPoint.cast(ent)
    if sp:
        return sp.worldGeometry
    ed = adsk.fusion.BRepEdge.cast(ent)
    if ed and hasattr(ed.geometry, "center"):
        return ed.geometry.center
    return None


def _radio_agujero(ent):
    """Si la entidad es el borde circular de un agujero cilindrico, su radio en mm. Si no, None."""
    ed = adsk.fusion.BRepEdge.cast(ent)
    if not ed or not hasattr(ed.geometry, "radius"):
        return None
    for f in ed.faces:
        ci = _cil_info(f)
        if ci and ci["agujero"] and abs(ci["R"] - ed.geometry.radius * 10.0) < 1e-3:
            return ci["R"]
    return None


def _colocacion(inputs):
    """Devuelve un dict: o (punto), fuera (direccion que se aleja de la pieza), cuerpo, modo
    ('libre', 'plano', 'curva', 'eje', 'agujero'), radio y largo sugeridos (mm), plana, puntos."""
    sp = inputs.itemById("plano")
    if sp.selectionCount == 0:
        e = EJES[inputs.itemById("eje").selectedItem.name]
        o = adsk.core.Point3D.create(0, 0, 0)
        return {"o": o, "fuera": adsk.core.Vector3D.create(*e), "cuerpo": None, "modo": "libre",
                "radio": None, "largo": None, "plana": True, "puntos": [o], "radios": [None]}
    sel = sp.selection(0)
    ent = sel.entity
    col = None
    cara = adsk.fusion.BRepFace.cast(ent)
    borde = adsk.fusion.BRepEdge.cast(ent)
    centrar = inputs.itemById("centrar").value
    if cara:
        ci = _cil_info(cara)
        if ci:
            return _desde_cilindro(cara, ci, sel.point)
        if adsk.core.Plane.cast(cara.geometry):
            _, n = cara.evaluator.getNormalAtPoint(cara.pointOnFace)
            n = n.copy()
            n.normalize()
            o = cara.centroid if centrar else _proyectar(sel.point, cara.centroid, n)
            col = {"o": o, "fuera": n, "cuerpo": cara.body, "modo": "plano", "radio": None, "largo": None, "plana": True}
        else:                                   # cara curva: perpendicular a la superficie donde se hizo clic
            _, n = cara.evaluator.getNormalAtPoint(sel.point)
            n = n.copy()
            n.normalize()
            o = sel.point
            return {"o": o, "fuera": n, "cuerpo": cara.body, "modo": "curva", "radio": None, "largo": None,
                    "plana": False, "puntos": [o], "radios": [None]}
    elif borde:
        g = borde.geometry
        centro = g.center
        for f in borde.faces:
            ci = _cil_info(f)
            if ci and abs(ci["R"] - g.radius * 10.0) < 1e-3:
                return _desde_cilindro(f, ci, centro)
        n = g.normal.copy()
        for f in borde.faces:
            if adsk.core.Plane.cast(f.geometry):
                _, n = f.evaluator.getNormalAtPoint(f.pointOnFace)
                n = n.copy()
                break
        n.normalize()
        col = {"o": centro, "fuera": n, "cuerpo": borde.body, "modo": "plano", "radio": g.radius * 10.0,
               "largo": None, "plana": True}
    else:
        pl = adsk.fusion.ConstructionPlane.cast(ent).geometry
        n = pl.normal.copy()
        n.normalize()
        o = pl.origin if centrar else _proyectar(sel.point, pl.origin, n)
        col = {"o": o, "fuera": n, "cuerpo": None, "modo": "plano", "radio": None, "largo": None, "plana": True}
    # puntos adicionales: una rosca en cada uno
    pts, radios = [], []
    spt = inputs.itemById("punto")
    for i in range(spt.selectionCount):
        e = spt.selection(i).entity
        q = _punto_de(e)
        if q:
            pts.append(_proyectar(q, col["o"], col["fuera"]))
            radios.append(_radio_agujero(e))
    col["puntos"] = pts or [col["o"]]
    col["radios"] = radios or [None]
    if pts:
        col["o"] = pts[0]
    return col


def _leer(inputs, col=None):
    """Lee el dialogo y devuelve los valores en mm / grados."""
    g = inputs.itemById
    if col is None:
        col = _colocacion(inputs)
    largo = g("largo")
    val = largo.value if largo.isValidExpression else 0.0
    return {
        "modo": col["modo"],
        "n": len(col["puntos"]),
        "en_pieza": col["cuerpo"] is not None and g("encuerpo").value,
        "hembra": g("tipo").selectedItem.name == "Hembra",
        "cresta": g("cresta").value * 10.0,
        "fondo": g("fondo").value * 10.0,
        "paso": g("paso").value * 10.0,
        "angulo": math.degrees(g("angulo").value),
        "largo": abs(val) * 10.0,
        "sentido": -1.0 if val < 0 else 1.0,
        "liso": max(0.0, g("liso").value * 10.0),
        "holgura": g("holgura").value * 10.0,
        "exterior": g("exterior").value * 10.0,
        "entradas": g("entradas").value,
        "izquierda": g("izquierda").value,
        "chaflan": g("chaflan").value,
        "radio_sel": col["radio"],
    }


def _tallar_eje(v):
    """True cuando toca tallar la rosca en un eje que ya existe (en vez de anadir un macho nuevo)."""
    return v["modo"] == "eje" and not v["hembra"] and v["en_pieza"] and v["sentido"] > 0


def _direccion(v, col):
    """Direccion base de la flecha. Hacia fuera de la pieza, salvo el taladro roscado y el eje existente."""
    b = col["fuera"].copy()
    if (v["hembra"] and v["en_pieza"]) or (v["modo"] == "eje" and not v["hembra"] and v["en_pieza"]):
        b.scaleBy(-1)
    return b


def _eje_final(v, col):
    e = _direccion(v, col)
    if v["sentido"] < 0:
        e.scaleBy(-1)
    return e


def _elegir(desplegable, nombre):
    for i in range(desplegable.listItems.count):
        it = desplegable.listItems.item(i)
        if it.name == nombre:
            it.isSelected = True
            return


def _tomar_medidas(inputs, col):
    """Al elegir un eje, un agujero o un borde circular: copia su diametro y su longitud al dialogo."""
    g = inputs.itemById
    if col["radio"] is None or not g("usar_d").value:
        return
    d = col["radio"] * 2.0 / 10.0                   # cm
    prof = g("cresta").value - g("fondo").value
    if col["modo"] == "eje":
        _elegir(g("tipo"), "Macho")
    elif col["modo"] == "agujero":
        _elegir(g("tipo"), "Hembra")
    if g("tipo").selectedItem.name == "Hembra":
        g("fondo").value = d                        # el agujero es el diametro de fondo del macho equivalente
        g("cresta").value = d + prof
    else:
        g("cresta").value = d
        g("fondo").value = d - prof
    _elegir(g("norma"), LIBRE)
    if col["largo"]:
        g("largo").value = col["largo"] / 10.0


def _refrescar(inputs, col=None):
    """Situa la flecha y muestra solo los campos que aplican a la seleccion actual."""
    if col is None:
        col = _colocacion(inputs)
    v = _leer(inputs, col)
    g = inputs.itemById
    g("largo").setManipulator(col["o"], _direccion(v, col))
    plano = col["modo"] == "plano"
    g("eje").isVisible = col["modo"] == "libre"
    g("centrar").isVisible = plano and col["radio"] is None
    g("punto").isVisible = plano
    g("encuerpo").isVisible = col["cuerpo"] is not None
    g("usar_d").isVisible = col["radio"] is not None
    g("exterior").isVisible = v["hembra"] and not v["en_pieza"]
    g("liso").isVisible = not _tallar_eje(v) and not (v["hembra"] and not v["en_pieza"])
    return v, col


def _resumen(v):
    """Texto de informacion y avisos. Devuelve (texto, valido)."""
    try:
        if v["paso"] <= 0 or v["largo"] <= 0:
            raise rosca_core.RoscaError("Paso y longitud deben ser distintos de cero")
        if not (10.0 <= v["angulo"] <= 120.0):
            raise rosca_core.RoscaError("Ángulo fuera de rango (10° a 120°)")
        if v["holgura"] < 0:
            raise rosca_core.RoscaError("La holgura no puede ser negativa")
        pf = rosca_core.perfil(v["cresta"], v["fondo"], v["paso"], v["angulo"], v["holgura"], v["hembra"])
        if v["hembra"] and not v.get("en_pieza") and v["exterior"] <= 2 * pf["r_fondo"] + 1.0:
            raise rosca_core.RoscaError(
                "El diámetro exterior del casquillo debe superar %.2f mm" % (2 * pf["r_fondo"] + 1.0))
        if _tallar_eje(v) and v.get("radio_sel") and pf["r_boca"] > v["radio_sel"] + 1e-4:
            raise rosca_core.RoscaError(
                "La cresta (%.2f mm) es mayor que el eje seleccionado (%.2f mm)" % (2 * pf["r_boca"], 2 * v["radio_sel"]))
    except rosca_core.RoscaError as e:
        return "<b>No se puede generar:</b> %s" % e, False
    avance = v["paso"] * v["entradas"]
    n = v.get("n", 1)
    vueltas = (v["largo"] + 2 * avance) / avance * v["entradas"] * n
    modo = v.get("modo", "libre")
    if _tallar_eje(v):
        destino = "Rosca tallada en el eje existente"
    elif v.get("en_pieza"):
        destino = "Taladro roscado dentro de la pieza" if v["hembra"] else "Macho unido a la pieza"
        if modo == "agujero" and v["hembra"]:
            destino = "Rosca en el agujero existente"
    elif modo == "libre":
        destino = "Cuerpo nuevo en el origen"
    else:
        destino = "Cuerpo nuevo sobre la selección"
    if v["hembra"] and not v.get("en_pieza"):
        destino += " (casquillo)"
    if n > 1:
        destino += " × %d" % n
    lineas = ["<b>%s</b>" % destino]
    if v.get("radio_sel"):
        lineas.append("Diámetro de la selección: %.2f mm" % (2 * v["radio_sel"]))
    lineas += [
        "Profundidad del surco: <b>%.2f mm</b>" % pf["prof"],
        "Plano de cresta %.2f mm · plano de fondo %.2f mm" % (pf["plano_cresta"], pf["plano_fondo"]),
        "Tiempo estimado: unos %d s" % max(3, round(vueltas * SEG_POR_VUELTA)),
    ]
    avisos = []
    if modo == "curva":
        avisos.append("Cara curva: la rosca sale perpendicular a la superficie donde hiciste clic.")
    if v["paso"] <= 1.0:
        avisos.append("Paso de 1 mm o menos: usa boquilla de 0,4 o menor y capa de 0,12.")
    if v["cresta"] < 6.0:
        avisos.append("Rosca pequeña: para piezas con carga, mejor inserto o tuerca embutida.")
    if pf["plano_cresta"] < 0.15:
        avisos.append("Cresta muy afilada: al imprimir saldrá redondeada.")
    if v["holgura"] == 0:
        avisos.append("Sin holgura: correcto contra rosca metálica; entre impresas pon 0,2.")
    elif v["hembra"]:
        avisos.append("Hembra sobre macho metálico: prueba primero con holgura 0.")
    if avisos:
        lineas.append("<br><b>Avisos</b>")
        lineas.extend("• " + a for a in avisos)
    return "<br>".join(lineas), True


# ---------------------------------------------------------------------------
# Construccion
# ---------------------------------------------------------------------------

def _a_local(design, col):
    """Pasa la colocacion a las coordenadas del componente donde se va a construir.
    Devuelve (componente, cuerpo nativo, matriz mundo->local o None)."""
    cuerpo = col["cuerpo"]
    if cuerpo is not None:
        occ = cuerpo.assemblyContext
        if occ:
            cuerpo = cuerpo.nativeObject
        comp = cuerpo.parentComponent
    else:
        comp = design.activeComponent
        occ = design.activeOccurrence
    m = None
    if occ:
        m = (occ.transform2 if hasattr(occ, "transform2") else occ.transform).copy()
        m.invert()
    return comp, cuerpo, m


def _construir(design, v, col):
    """Genera la rosca (o las roscas) con los valores v en la colocacion col. Devuelve el nombre."""
    comp, cuerpo, m = _a_local(design, col)
    en_pieza = v["en_pieza"] and cuerpo is not None
    eje = _eje_final(v, col)
    puntos = [p.copy() for p in col["puntos"]]
    if m is not None:
        eje.transformBy(m)
        for p in puntos:
            p.transformBy(m)
    nombre = "%s D%.2f P%.3f" % ("Hembra" if v["hembra"] else "Macho", v["cresta"], v["paso"])
    comunes = dict(holgura=v["holgura"], entradas=v["entradas"], izquierda=v["izquierda"], chaflan=v["chaflan"])
    medidas = (v["cresta"], v["fondo"], v["paso"], v["angulo"], v["largo"])
    r_ext = v["cresta"] / 2.0
    tl = design.timeline if design.designType == adsk.fusion.DesignTypes.ParametricDesignType else None
    ini = tl.markerPosition if tl else 0
    for p, r_ag in zip(puntos, col["radios"]):
        if v["hembra"] and en_pieza and r_ag and v["sentido"] > 0:
            rosca_core.rosca_en_agujero(comp, cuerpo, r_ag, *medidas, origen=p, eje=eje, **comunes)
        elif v["hembra"] and en_pieza:
            rosca_core.hembra_en(comp, cuerpo, *medidas, origen=p, eje=eje, extra=v["liso"],
                                 sobre=0.5 if col["plana"] else r_ext + 0.5, **comunes)
        elif v["hembra"]:
            body, _ = rosca_core.rosca_hembra(comp, *medidas, exterior_d=v["exterior"], nombre=nombre, **comunes)
            rosca_core._mover(comp, body, p, eje)
        elif _tallar_eje(v):
            rosca_core.rosca_en_eje(comp, cuerpo, col["radio"], *medidas, origen=p, eje=eje, **comunes)
        else:
            rosca_core.macho_en(comp, *medidas, origen=p, eje=eje, unir_a=cuerpo if en_pieza else None,
                                nombre=nombre, liso=v["liso"], solape=None if col["plana"] else r_ext + 0.3, **comunes)
    if tl:
        try:
            fin = tl.markerPosition - 1
            if fin > ini:
                grupo = tl.timelineGroups.add(ini, fin)
                grupo.name = "Thread Maker: " + nombre
        except Exception:  # noqa: BLE001
            pass                                      # el grupo es solo orden; si falla, la rosca ya esta hecha
    return nombre


# ---------------------------------------------------------------------------
# Valores recordados entre usos
# ---------------------------------------------------------------------------

_NUM = ("cresta", "fondo", "paso", "angulo", "largo", "liso", "holgura", "exterior")
_BOOL = ("centrar", "encuerpo", "usar_d", "izquierda", "chaflan")
_LISTA = ("tipo", "norma", "eje")


def _guardar_memo(inputs):
    try:
        g = inputs.itemById
        d = {k: g(k).value for k in _NUM + _BOOL}
        d["largo"] = abs(d["largo"])
        d.update({k: g(k).selectedItem.name for k in _LISTA})
        d["entradas"] = g("entradas").value
        with open(_MEMO, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
    except Exception:  # noqa: BLE001
        pass


def _cargar_memo():
    try:
        with open(_MEMO, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# Dialogo
# ---------------------------------------------------------------------------

class _Creado(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            cmd.isExecutedWhenPreEmpted = False
            cmd.setDialogInitialSize(400, 760)
            ins = cmd.commandInputs
            vr = adsk.core.ValueInput.createByReal
            lista = adsk.core.DropDownStyles.TextListDropDownStyle
            memo = _cargar_memo()
            c0, f0, p0, a0 = _NORMAS["M10 x 1,5"]

            def num(k, defecto):
                x = memo.get(k)
                return float(x) if isinstance(x, (int, float)) else defecto

            def si(k, defecto):
                x = memo.get(k)
                return x if isinstance(x, bool) else defecto

            plano = ins.addSelectionInput("plano", "Dónde", "Cara plana, plano de construcción, cara curva, cara cilíndrica (eje o agujero) o borde circular. Sin selección: en el origen.")
            for filtro in ("Faces", "ConstructionPlanes", "CircularEdges"):
                plano.addSelectionFilter(filtro)
            plano.setSelectionLimits(0, 1)
            centrar = ins.addBoolValueInput("centrar", "Centrar en la cara", True, "", si("centrar", True))
            centrar.tooltip = "Desmarcado: la rosca nace justo donde hiciste clic al elegir la cara."
            punto = ins.addSelectionInput("punto", "Puntos (opcional)", "Vértices, puntos de boceto o bordes circulares. Se hace una rosca en cada uno.")
            for filtro in ("Vertices", "SketchPoints", "CircularEdges"):
                punto.addSelectionFilter(filtro)
            punto.setSelectionLimits(0, 0)
            eje = ins.addDropDownCommandInput("eje", "Eje", lista)
            for nombre in ("Z", "X", "Y"):
                eje.listItems.add(nombre, nombre == memo.get("eje", "Z"))
            ins.addBoolValueInput("encuerpo", "Unir / taladrar en la pieza", True, "", si("encuerpo", True))
            usar = ins.addBoolValueInput("usar_d", "Usar el diámetro seleccionado", True, "", si("usar_d", True))
            usar.tooltip = "Copia el diámetro y la longitud del eje, agujero o borde elegido."

            tipo = ins.addDropDownCommandInput("tipo", "Tipo", lista)
            for nombre in ("Macho", "Hembra"):
                tipo.listItems.add(nombre, nombre == memo.get("tipo", "Macho"))

            norma = ins.addDropDownCommandInput("norma", "Norma", lista)
            elegida = memo.get("norma", "M10 x 1,5")
            if elegida not in _NORMAS:
                elegida = "M10 x 1,5"
            for nombre, _ in NORMAS:
                norma.listItems.add(nombre, nombre == elegida)

            ins.addValueInput("cresta", "Diámetro de cresta", "mm", vr(num("cresta", c0 / 10.0)))
            ins.addValueInput("fondo", "Diámetro de fondo", "mm", vr(num("fondo", f0 / 10.0)))
            ins.addValueInput("paso", "Paso", "mm", vr(num("paso", p0 / 10.0)))
            ins.addValueInput("angulo", "Ángulo del filete", "deg", vr(num("angulo", math.radians(a0))))
            largo = ins.addDistanceValueCommandInput("largo", "Longitud de rosca", vr(num("largo", 2.0)))
            largo.tooltip = "Arrastra la flecha en pantalla. Hacia el otro lado cambia el sentido."
            liso = ins.addValueInput("liso", "Tramo liso / taladro extra", "mm", vr(num("liso", 0.0)))
            liso.tooltip = "Macho: tramo sin rosca entre la pieza y el filete. Hembra: taladro liso más allá de la rosca."
            ins.addValueInput("holgura", "Holgura radial", "mm", vr(num("holgura", 0.02)))
            ins.addValueInput("exterior", "Ø exterior (solo casquillo)", "mm", vr(num("exterior", 1.8)))
            ent = memo.get("entradas", 1)
            ins.addIntegerSpinnerCommandInput("entradas", "Entradas", 1, 8, 1, ent if isinstance(ent, int) and 1 <= ent <= 8 else 1)
            ins.addBoolValueInput("izquierda", "Rosca a izquierdas", True, "", si("izquierda", False))
            ins.addBoolValueInput("chaflan", "Chaflán de entrada", True, "", si("chaflan", True))
            info = ins.addTextBoxCommandInput("info", "", "", 11, True)
            info.isFullWidth = True

            v, _ = _refrescar(ins)
            info.formattedText = _resumen(v)[0]

            for cls, evento in ((_Cambio, cmd.inputChanged), (_Validar, cmd.validateInputs),
                                (_Previa, cmd.executePreview), (_Ejecutar, cmd.execute)):
                h = cls()
                evento.add(h)
                _handlers.append(h)
        except Exception:  # noqa: BLE001
            _ui().messageBox("Thread Maker:\n" + traceback.format_exc())


class _Cambio(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            ins = args.inputs
            cambiado = args.input.id
            if cambiado == "info":
                return
            if cambiado == "norma":
                datos = _NORMAS.get(ins.itemById("norma").selectedItem.name)
                if datos:
                    c, f, p, a = datos
                    ins.itemById("cresta").value = c / 10.0
                    ins.itemById("fondo").value = f / 10.0
                    ins.itemById("paso").value = p / 10.0
                    ins.itemById("angulo").value = math.radians(a)
            if cambiado == "tipo" and ins.itemById("tipo").selectedItem.name == "Hembra":
                ins.itemById("exterior").value = (ins.itemById("cresta").value * 10.0 + 8.0) / 10.0
            col = _colocacion(ins)
            if cambiado in ("plano", "usar_d"):
                _tomar_medidas(ins, col)
            v, _ = _refrescar(ins, col)
            ins.itemById("info").formattedText = _resumen(v)[0]
        except Exception:  # noqa: BLE001
            _ui().messageBox("Thread Maker:\n" + traceback.format_exc())


class _Validar(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            args.areInputsValid = _resumen(_leer(args.inputs))[1]
        except Exception:  # noqa: BLE001
            args.areInputsValid = False


class _Previa(adsk.core.CommandEventHandler):
    """Vista previa rapida: un cilindro con el diametro y la longitud de la rosca en cada posicion.
    El filete real se calcula solo al aceptar, porque tarda varios segundos."""

    def notify(self, args):
        try:
            ins = args.command.commandInputs
            col = _colocacion(ins)
            v = _leer(ins, col)
            if not _resumen(v)[1]:
                return
            e = _eje_final(v, col)
            pf = rosca_core.perfil(v["cresta"], v["fondo"], v["paso"], v["angulo"], v["holgura"], v["hembra"])
            if v["hembra"] and not v["en_pieza"]:
                r = v["exterior"] / 2.0
            elif _tallar_eje(v):
                r = col["radio"] + 0.05
            else:
                r = pf["r_fondo"] if v["hembra"] else pf["r_boca"]
            L = (v["largo"] + (v["liso"] if not _tallar_eje(v) else 0.0)) / 10.0
            design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
            grupo = design.rootComponent.customGraphicsGroups.add()
            color = adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(38, 110, 190, 150))
            tm = adsk.fusion.TemporaryBRepManager.get()
            for o in col["puntos"]:
                p2 = adsk.core.Point3D.create(o.x + e.x * L, o.y + e.y * L, o.z + e.z * L)
                cg = grupo.addBRepBody(tm.createCylinderOrCone(o, r / 10.0, p2, r / 10.0))
                cg.color = color
            args.isValidResult = False          # al aceptar se ejecuta el calculo completo
        except Exception:  # noqa: BLE001
            pass


class _Ejecutar(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            ins = args.command.commandInputs
            design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
            if not design:
                _ui().messageBox("Thread Maker: abre un diseño primero.")
                return
            col = _colocacion(ins)              # se lee antes de tocar el modelo
            v = _leer(ins, col)
            _guardar_memo(ins)
            _construir(design, v, col)
        except Exception:  # noqa: BLE001
            args.executeFailed = True
            args.executeFailedMessage = "Thread Maker no pudo generar la rosca:<br>" + traceback.format_exc().splitlines()[-1]


def _limpiar():
    ui = _ui()
    panel = ui.allToolbarPanels.itemById(PANEL_ID)
    if panel:
        ctl = panel.controls.itemById(CMD_ID)
        if ctl:
            ctl.deleteMe()
    cd = ui.commandDefinitions.itemById(CMD_ID)
    if cd:
        cd.deleteMe()


def run(context):
    try:
        importlib.reload(rosca_core)
        _limpiar()
        ui = _ui()
        cd = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TIP, os.path.join(_DIR, "resources"))
        h = _Creado()
        cd.commandCreated.add(h)
        _handlers.append(h)
        panel = ui.allToolbarPanels.itemById(PANEL_ID)
        if panel:
            ctl = panel.controls.addCommand(cd)
            ctl.isPromoted = True
    except Exception:  # noqa: BLE001
        _ui().messageBox("Thread Maker:\n" + traceback.format_exc())


def stop(context):
    try:
        _limpiar()
        del _handlers[:]
    except Exception:  # noqa: BLE001
        pass
