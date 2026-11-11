# Thread Maker - Fusion add-in.
# Dialog to build a printable thread (male or female) from measurements.
# The dialog text is in Spanish for now; the file is UTF-8.
import importlib
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


def _leer(inputs):
    """Lee el dialogo y devuelve los valores en mm / grados."""
    g = inputs.itemById
    return {
        "hembra": g("tipo").selectedItem.name == "Hembra",
        "cresta": g("cresta").value * 10.0,
        "fondo": g("fondo").value * 10.0,
        "paso": g("paso").value * 10.0,
        "angulo": math.degrees(g("angulo").value),
        "largo": g("largo").value * 10.0,
        "holgura": g("holgura").value * 10.0,
        "exterior": g("exterior").value * 10.0,
        "entradas": g("entradas").value,
        "izquierda": g("izquierda").value,
        "chaflan": g("chaflan").value,
    }


def _resumen(v):
    """Texto de informacion y avisos. Devuelve (texto, valido)."""
    try:
        if v["paso"] <= 0 or v["largo"] <= 0:
            raise rosca_core.RoscaError("Paso y longitud deben ser mayores que cero")
        if not (10.0 <= v["angulo"] <= 120.0):
            raise rosca_core.RoscaError("Ángulo fuera de rango (10° a 120°)")
        if v["holgura"] < 0:
            raise rosca_core.RoscaError("La holgura no puede ser negativa")
        pf = rosca_core.perfil(v["cresta"], v["fondo"], v["paso"], v["angulo"], v["holgura"], v["hembra"])
        if v["hembra"] and v["exterior"] <= 2 * pf["r_fondo"] + 1.0:
            raise rosca_core.RoscaError(
                "El diámetro exterior del casquillo debe superar %.2f mm" % (2 * pf["r_fondo"] + 1.0))
    except rosca_core.RoscaError as e:
        return "<b>No se puede generar:</b> %s" % e, False
    avance = v["paso"] * v["entradas"]
    vueltas = (v["largo"] + 2 * avance) / avance * v["entradas"]
    lineas = [
        "Profundidad del surco: <b>%.2f mm</b>" % pf["prof"],
        "Plano de cresta %.2f mm · plano de fondo %.2f mm" % (pf["plano_cresta"], pf["plano_fondo"]),
        "Tiempo estimado: unos %d s" % max(3, round(vueltas * SEG_POR_VUELTA)),
    ]
    avisos = []
    if v["paso"] <= 1.0:
        avisos.append("Paso de 1 mm o menos: usa boquilla de 0,4 o menor y capa de 0,12.")
    if v["cresta"] < 6.0:
        avisos.append("Rosca pequeña: para piezas con carga, mejor inserto o tuerca embutida.")
    if pf["plano_cresta"] < 0.15:
        avisos.append("Cresta muy afilada: al imprimir saldrá redondeada.")
    if v["holgura"] == 0 and not v["hembra"]:
        avisos.append("Sin holgura: correcto contra rosca metálica; entre impresas pon 0,2.")
    if avisos:
        lineas.append("<br><b>Avisos</b>")
        lineas.extend("• " + a for a in avisos)
    return "<br>".join(lineas), True


class _Creado(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            cmd.isExecutedWhenPreEmpted = False
            cmd.setDialogInitialSize(380, 560)
            ins = cmd.commandInputs
            vr = adsk.core.ValueInput.createByReal
            vs = adsk.core.ValueInput.createByString

            tipo = ins.addDropDownCommandInput("tipo", "Tipo", adsk.core.DropDownStyles.TextListDropDownStyle)
            tipo.listItems.add("Macho", True)
            tipo.listItems.add("Hembra", False)

            norma = ins.addDropDownCommandInput("norma", "Norma", adsk.core.DropDownStyles.TextListDropDownStyle)
            for nombre, _ in NORMAS:
                norma.listItems.add(nombre, nombre == "M10 x 1,5")

            c, f, p, a = _NORMAS["M10 x 1,5"]
            ins.addValueInput("cresta", "Diámetro de cresta", "mm", vr(c / 10.0))
            ins.addValueInput("fondo", "Diámetro de fondo", "mm", vr(f / 10.0))
            ins.addValueInput("paso", "Paso", "mm", vr(p / 10.0))
            ins.addValueInput("angulo", "Ángulo del filete", "deg", vs("%g deg" % a))
            ins.addValueInput("largo", "Longitud", "mm", vr(2.0))
            ins.addValueInput("holgura", "Holgura radial", "mm", vr(0.02))
            ext = ins.addValueInput("exterior", "Ø exterior del casquillo", "mm", vr(1.8))
            ext.isVisible = False
            ins.addIntegerSpinnerCommandInput("entradas", "Entradas", 1, 8, 1, 1)
            ins.addBoolValueInput("izquierda", "Rosca a izquierdas", True, "", False)
            ins.addBoolValueInput("chaflan", "Chaflán de entrada", True, "", True)
            info = ins.addTextBoxCommandInput("info", "", "", 9, True)
            info.isFullWidth = True
            info.formattedText = _resumen(_leer(ins))[0]

            for cls, evento in ((_Cambio, cmd.inputChanged), (_Validar, cmd.validateInputs), (_Ejecutar, cmd.execute)):
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
            if cambiado == "norma":
                datos = _NORMAS.get(ins.itemById("norma").selectedItem.name)
                if datos:
                    c, f, p, a = datos
                    ins.itemById("cresta").value = c / 10.0
                    ins.itemById("fondo").value = f / 10.0
                    ins.itemById("paso").value = p / 10.0
                    ins.itemById("angulo").value = math.radians(a)
            if cambiado == "tipo":
                hembra = ins.itemById("tipo").selectedItem.name == "Hembra"
                ins.itemById("exterior").isVisible = hembra
                if hembra:
                    ins.itemById("exterior").value = (ins.itemById("cresta").value * 10.0 + 8.0) / 10.0
            if cambiado != "info":
                ins.itemById("info").formattedText = _resumen(_leer(ins))[0]
        except Exception:  # noqa: BLE001
            _ui().messageBox("Thread Maker:\n" + traceback.format_exc())


class _Validar(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            args.areInputsValid = _resumen(_leer(args.inputs))[1]
        except Exception:  # noqa: BLE001
            args.areInputsValid = False


class _Ejecutar(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            v = _leer(args.command.commandInputs)
            app = adsk.core.Application.get()
            design = adsk.fusion.Design.cast(app.activeProduct)
            if not design:
                _ui().messageBox("Thread Maker: abre un diseño primero.")
                return
            comp = design.activeComponent
            nombre = "%s D%.2f P%.3f" % ("Hembra" if v["hembra"] else "Macho", v["cresta"], v["paso"])
            if v["hembra"]:
                rosca_core.rosca_hembra(comp, v["cresta"], v["fondo"], v["paso"], v["angulo"], v["largo"],
                                        holgura=v["holgura"], entradas=v["entradas"], izquierda=v["izquierda"],
                                        chaflan=v["chaflan"], exterior_d=v["exterior"], nombre=nombre)
            else:
                rosca_core.rosca_macho(comp, v["cresta"], v["fondo"], v["paso"], v["angulo"], v["largo"],
                                       holgura=v["holgura"], entradas=v["entradas"], izquierda=v["izquierda"],
                                       chaflan=v["chaflan"], nombre=nombre)
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
        cd = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_TIP)
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
