from app.models.base import Respuesta
from app.services.pdf_service import CAMPOS_EDITABLES_ACROFORM

# Total oficial de campos del Formulario Paz y Salvo (ver hoja_espejo.html:
# cada campo_formulario referenciado ahí, sin contar los '_nombre' que se
# autogeneran al firmar). Única fuente de verdad para el % de avance,
# usada tanto por areas.py como por paz_salvo.py.
TOTAL_CAMPOS_PAZ_SALVO = 152

# Campos que existen en el formulario pero son opcionales: si quedan vacíos
# no deben impedir llegar al 100% de avance (ej. email2, correo alternativo)
CAMPOS_OPCIONALES = {'email2'}

# "Casillas de firma" (no son texto, se llenan solas con 'FIRMADO' al estampar
# PAdES). Se excluyen del chequeo de "texto completo" porque, antes de la
# primera firma de todo el trámite, NINGUNA de estas puede estar llena todavía
# — si se contaran aquí, nunca se podría habilitar la primera firma.
CAMPOS_FIRMA = {
    'tramites_r1', 'tramites_r2', 'tramites_r3', 'tramites_jefe',
    'admin_r1', 'admin_r2', 'admin_r3', 'admin_r4', 'admin_dir',
    'tic_r1', 'tic_r2', 'tic_r3', 'tic_r4', 'tic_r5',
    'fin_r1', 'fin_r2', 'fin_r3', 'fin_r4', 'fin_dir',
    'seg_r1', 'seg_r2', 'seg_oficial_sig',
    'rrhh_r1', 'rrhh_r2', 'rrhh_r3', 'rrhh_r4', 'rrhh_r5', 'rrhh_r6', 'rrhh_r7', 'rrhh_r8', 'rrhh_dir',
    'recepcion_r1', 'servidor_saliente',
}


def calcular_progreso(solicitud_id):
    """Devuelve (campos_respondidos, total_campos, porcentaje) de una solicitud.
    Solo cuenta como 'respondido' un campo con valor real guardado, no uno
    simplemente asignado por el Administrador."""
    respuestas = Respuesta.query.filter_by(solicitud_id=solicitud_id).all()
    respondidos = sum(
        1 for r in respuestas
        if r.valor_respuesta and str(r.valor_respuesta).strip() != ''
        and not r.campo_formulario.endswith('_nombre')
        and r.campo_formulario not in CAMPOS_OPCIONALES
    )
    total = TOTAL_CAMPOS_PAZ_SALVO - len(CAMPOS_OPCIONALES)
    porcentaje = min(100, round((respondidos / total) * 100))
    return respondidos, total, porcentaje


def texto_completo(solicitud_id):
    """True si todos los campos de texto que TODAVÍA NO se pueden actualizar
    después de firmar (es decir, sin contar casillas de firma, campos
    opcionales, ni los ya migrados a CAMPOS_EDITABLES_ACROFORM) ya tienen un
    valor real guardado. Es el candado/aviso que se usa antes de la PRIMERA
    firma PAdES del trámite: los campos de CAMPOS_EDITABLES_ACROFORM quedan
    fuera de este chequeo porque esos sí se pueden llenar antes O después de
    cualquier firma sin arriesgarla (ver pdf_service.actualizar_campo_pdf_incremental)."""
    respuestas = Respuesta.query.filter_by(solicitud_id=solicitud_id).all()
    campos_excluidos = CAMPOS_OPCIONALES | CAMPOS_FIRMA | CAMPOS_EDITABLES_ACROFORM
    respondidos = sum(
        1 for r in respuestas
        if r.valor_respuesta and str(r.valor_respuesta).strip() != ''
        and not r.campo_formulario.endswith('_nombre')
        and r.campo_formulario not in campos_excluidos
    )
    total_texto = TOTAL_CAMPOS_PAZ_SALVO - len(campos_excluidos)
    return respondidos >= total_texto


def actualizar_estado_automatico(solicitud):
    """Actualiza solicitud.estado según el % de avance (EN_PROGRESO / EN REVISIÓN),
    SIN tocar un trámite que ya tiene veredicto final de RRHH (Aprobado/Negado).
    No hace commit; el llamador decide cuándo guardar."""
    if solicitud.estado in ('APROBADO', 'NEGADO'):
        return solicitud.estado

    _, _, porcentaje = calcular_progreso(solicitud.id)
    nuevo_estado = 'EN REVISIÓN' if porcentaje >= 100 else 'EN_PROGRESO'
    if solicitud.estado != nuevo_estado:
        solicitud.estado = nuevo_estado
    return solicitud.estado
