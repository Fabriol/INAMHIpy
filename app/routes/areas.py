from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user

# Modelos oficiales del sistema institucional
from app.models.base import db, SolicitudPazSalvo, Respuesta, LogAuditoria, Usuario, Rol

areas_bp = Blueprint('areas', __name__)

# ====================================================================
# 1. RUTA: PANEL INTELIGENTE DE TRÁMITES (CORREGIDO SIN BUSQUEDA EN_PROGRESO)
# ====================================================================
@areas_bp.route('/areas/tareas')
@login_required
def mis_tareas():
    # Lista de roles permitidos en el Centro de Gestión Institucional
    roles_areas = ['Administrativa', 'Financiera', 'TICs', 'Seguridad', 'Administrador', 'Talento Humano - Recepción Documentos', 'Ex Funcionario']
    
    if current_user.rol.nombre not in roles_areas:
        flash('Acceso denegado. No perteneces a un área de validación.', 'danger')
        return redirect(url_for('dashboard.index'))

    # FILTRADO DE BANDEJA SEGÚN EL ROL DE INICIO DE SESIÓN
    if current_user.rol.nombre in ['Administrador', 'Talento Humano - Recepción Documentos']:
        # El Administrador y RRHH visualizan la bandeja completa de la institución
        solicitudes = SolicitudPazSalvo.query.order_by(SolicitudPazSalvo.fecha_creacion.desc()).all()
        
    elif current_user.rol.nombre == 'Ex Funcionario':
        # El Ex Funcionario visualiza EXCLUSIVAMENTE su propia solicitud de Paz y Salvo
        solicitudes = SolicitudPazSalvo.query.filter_by(ex_funcionario_id=current_user.id).all()
        
    else:
        # Las áreas técnicas (TICs, Financiera, Seguridad, etc.) ven solo donde el Admin les delegó campos
        asignaciones = Respuesta.query.filter_by(usuario_asignado_id=current_user.id).all()
        
        # Obtenemos los IDs de los trámites asignados eliminando duplicados
        solicitud_ids = list(set([r.solicitud_id for r in asignaciones]))
        
        if solicitud_ids:
            solicitudes = SolicitudPazSalvo.query.filter(SolicitudPazSalvo.id.in_(solicitud_ids)).order_by(SolicitudPazSalvo.fecha_creacion.desc()).all()
        else:
            solicitudes = []
        
    # Inyección forzada de datos de identidad para limpiar el "Dato No Vinculado" en las tablas
    for sol in solicitudes:
        sol.usuario_data = Usuario.query.get(sol.ex_funcionario_id)
        
    return render_template('areas/pendientes.html', solicitudes=solicitudes)


# ====================================================================
# 2. RUTA: VISTA PREVIA AISLADA DEL DOCUMENTO (HOJA ESPEJO)
# ====================================================================
@areas_bp.route('/areas/ver/<int:solicitud_id>')
@login_required
def vista_previa(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    # Extraemos las respuestas asentadas para la previsualización de la Hoja Espejo
    respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
    datos_combinados = {r.campo_formulario: r.valor_respuesta for r in respuestas_db}
    
    return render_template('paz_salvo/ver_espejo.html', solicitud=solicitud, datos=datos_combinados)


# ====================================================================
# 3. RUTA: EMITIR DICTAMEN FINAL DE CIERRE (ADMINISTRADOR / RRHH)
# ====================================================================
@areas_bp.route('/areas/responder/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
def responder_preguntas(solicitud_id):
    # Restricción: Solo el Administrador o RRHH cierran legalmente el expediente
    if current_user.rol.nombre not in ['Administrador', 'Talento Humano - Recepción Documentos']:
        flash('No tiene permisos para emitir el dictamen final de este expediente.', 'danger')
        return redirect(url_for('areas.mis_tareas'))

    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)

    if request.method == 'POST':
        estado_final = request.form.get('estado_final')
        observacion_final = request.form.get('observacion_final')

        if not estado_final:
            flash('Error: Debe seleccionar un veredicto oficial para el trámite.', 'danger')
            return redirect(url_for('areas.responder_preguntas', solicitud_id=solicitud.id))

        # Actualizamos de forma irreversible el estado del Paz y Salvo
        solicitud.estado = str(estado_final).upper()
        detalle_auditoria = f"Emitió veredicto final: {estado_final}."

        if estado_final == 'Negado':
            solicitud.observacion_rechazo = str(observacion_final).upper()
            detalle_auditoria += f" Motivo de Rechazo: {observacion_final}"
            flash('Trámite negado de forma oficial. Se registró el motivo del rechazo en el sistema.', 'warning')

        elif estado_final == 'Aprobado':
            # Bloqueo total e inmediato de autenticación para el Ex Funcionario en la nube
            ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
            if ex_funcionario:
                ex_funcionario.activo = False
            flash('Trámite Aprobado Exitosamente. El expediente se ha cerrado y las credenciales del ex-funcionario fueron inhabilitadas.', 'success')

        # Registro de seguridad y rastreabilidad en la auditoría del sistema
        log = LogAuditoria(
            usuario_id=current_user.id, 
            modulo='Validación de Áreas', 
            accion='DICTAMEN FINAL', 
            detalle=f"El usuario {current_user.rol.nombre} procesó el trámite #{solicitud.id}. {detalle_auditoria}"
        )
        db.session.add(log)
        db.session.commit()
        
        return redirect(url_for('areas.mis_tareas'))

    return render_template('areas/responder.html', solicitud=solicitud)