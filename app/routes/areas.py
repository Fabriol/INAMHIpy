from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

# OJO: Se añadió LogAuditoria a las importaciones
from app.models.base import db, SolicitudPazSalvo, Pregunta, Respuesta, LogAuditoria

areas_bp = Blueprint('areas', __name__)

# ==========================================
# 1. RUTA: PANEL DE DOCUMENTOS / TAREAS
# ==========================================
@areas_bp.route('/areas/tareas')
@login_required
def mis_tareas():
    # 1. Llave Maestra: Añadimos 'Administrador' a los roles permitidos
    roles_areas = ['Administrativa', 'Financiera', 'TICs', 'Seguridad', 'Administrador']
    
    if current_user.rol.nombre not in roles_areas:
        flash('Acceso denegado. No perteneces a un área de validación.', 'danger')
        return redirect(url_for('dashboard.index'))

    # 2. BYPASS ADMINISTRADOR: El Admin ve TODO el historial. Las áreas solo ven lo que está EN_PROGRESO.
    if current_user.rol.nombre == 'Administrador':
        solicitudes = SolicitudPazSalvo.query.order_by(SolicitudPazSalvo.fecha_creacion.desc()).all()
    else:
        solicitudes = SolicitudPazSalvo.query.filter_by(estado='EN_PROGRESO').all()
        
    return render_template('areas/pendientes.html', solicitudes=solicitudes)


# ==========================================
# 2. RUTA: RESPONDER PREGUNTAS DEL ÁREA
# ==========================================
@areas_bp.route('/areas/responder/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
def responder_preguntas(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    
    # 3. FILTRO MÁGICO + BYPASS: El Admin puede ver TODAS las preguntas para revisar, las áreas solo las suyas.
    if current_user.rol.nombre == 'Administrador':
        preguntas = Pregunta.query.filter_by(activa=True).all()
    else:
        preguntas = Pregunta.query.filter_by(rol_asignado_id=current_user.rol_id, activa=True).all()

    if request.method == 'POST':
        respuestas_guardadas = [] # Lista para la auditoría
        
        for pregunta in preguntas:
            valor = request.form.get(f'pregunta_{pregunta.id}')
            observacion = request.form.get(f'observacion_{pregunta.id}')
            
            # REGLA ESTRICTA 8.1: Ningún campo puede quedar vacío
            if not valor:
                flash(f'Error de integridad: Debe responder a la pregunta "{pregunta.enunciado}".', 'danger')
                return redirect(url_for('areas.responder_preguntas', solicitud_id=solicitud.id))
            
            # Buscamos si ya existe una respuesta previa para actualizarla, o si es nueva la creamos.
            respuesta_existente = Respuesta.query.filter_by(solicitud_id=solicitud.id, pregunta_id=pregunta.id).first()
            
            if respuesta_existente:
                respuesta_existente.valor_respuesta = valor
                respuesta_existente.observacion = observacion
            else:
                nueva_respuesta = Respuesta(
                    solicitud_id=solicitud.id,
                    pregunta_id=pregunta.id,
                    usuario_responde_id=current_user.id,
                    valor_respuesta=valor,
                    observacion=observacion
                )
                db.session.add(nueva_respuesta)
            
            # Registramos qué se respondió para mandarlo al log
            respuestas_guardadas.append(f"P{pregunta.id}:{valor}")
        
        # --- REGLA CRÍTICA: AUDITORÍA DEL SISTEMA ---
        # Guardamos en la base de datos exactamente quién hizo qué y a qué hora.
        log = LogAuditoria(
            usuario_id=current_user.id, 
            modulo='Validación de Áreas', 
            accion='ÁREA RESPONDE', 
            detalle=f"El área {current_user.rol.nombre} validó el trámite #{solicitud.id}. Respuestas: [{', '.join(respuestas_guardadas)}]"
        )
        db.session.add(log)
        db.session.commit()
        
        flash('Información guardada. Su validación departamental ha finalizado para este trámite.', 'success')
        return redirect(url_for('areas.mis_tareas'))

    return render_template('areas/responder.html', solicitud=solicitud, preguntas=preguntas)