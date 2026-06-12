from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.base import db, Pregunta, Rol

admin_preguntas_bp = Blueprint('admin_preguntas', __name__)

@admin_preguntas_bp.route('/admin/preguntas', methods=['GET', 'POST'])
@login_required
def gestionar_preguntas():
    # 1. Seguridad estricta: Solo Administrador
    if current_user.rol.nombre != 'Administrador':
        flash('Acceso denegado. Perfil no autorizado para configurar el sistema.', 'danger')
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        enunciado = request.form.get('enunciado')
        tipo_respuesta = request.form.get('tipo_respuesta')
        rol_id = request.form.get('rol_id')

        # 2. Guardamos la pregunta dinámica en la DB
        nueva_pregunta = Pregunta(
            rol_asignado_id=rol_id,
            enunciado=enunciado,
            tipo_respuesta=tipo_respuesta,
            activa=True
        )
        db.session.add(nueva_pregunta)
        db.session.commit()
        
        flash('Pregunta agregada correctamente al sistema institucional.', 'success')
        return redirect(url_for('admin_preguntas.gestionar_preguntas'))

    # 3. Para mostrar la pantalla (GET)
    # Traemos todas las preguntas creadas
    preguntas_creadas = Pregunta.query.all()
    
    # Traemos SOLO los roles que deben responder preguntas (Excluimos al Admin y al Ex Funcionario de esta lista)
    roles_areas = Rol.query.filter(Rol.nombre.in_([
        'Administrativa', 'Financiera', 'TICs', 'Seguridad'
    ])).all()

    return render_template('admin/gestionar_preguntas.html', preguntas=preguntas_creadas, roles=roles_areas)