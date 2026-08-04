from app.models.base import Respuesta

# Total oficial de campos del Formulario Paz y Salvo (ver hoja_espejo.html:
# cada campo_formulario referenciado ahí, sin contar los '_nombre' que se
# autogeneran al firmar). Única fuente de verdad para el % de avance,
# usada tanto por areas.py como por paz_salvo.py.
TOTAL_CAMPOS_PAZ_SALVO = 152

# Campos que existen en el formulario pero son opcionales: si quedan vacíos
# no deben impedir llegar al 100% de avance (ej. email2, correo alternativo)
CAMPOS_OPCIONALES = {'email2'}


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
