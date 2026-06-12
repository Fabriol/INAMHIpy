from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app.models.base import db, Usuario, Rol, SolicitudPazSalvo

paz_salvo_bp = Blueprint('paz_salvo', __name__)

@paz_salvo_bp.route('/paz-salvo/nueva', methods=['GET', 'POST'])
@login_required
def nueva_solicitud():
    # 1. Validación de Seguridad: Solo perfiles autorizados pueden crear trámites
    roles_permitidos = ['Administrador', 'Talento Humano - Recepción Documentos']
    if current_user.rol.nombre not in roles_permitidos:
        flash('Acceso denegado. No tienes permisos para iniciar un trámite.', 'danger')
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        cedula = request.form.get('cedula')
        nombres = request.form.get('nombres')
        apellidos = request.form.get('apellidos')
        email = request.form.get('email')

        # 2. Verificamos si el usuario ya existe en la base de datos
        usuario = Usuario.query.filter_by(cedula=cedula).first()

        if not usuario:
            # Si no existe, buscamos el rol oficial y lo creamos
            rol_ex = Rol.query.filter_by(nombre='Ex Funcionario').first()
            
            usuario = Usuario(
                rol_id=rol_ex.id,
                cedula=cedula,
                nombres=nombres,
                apellidos=apellidos,
                email=email,
                # La contraseña temporal será la misma cédula
                password_hash=generate_password_hash(cedula),
                activo=True
            )
            db.session.add(usuario)
            db.session.flush() # Guardamos temporalmente para obtener su ID

        # 3. Generamos el inicio del trámite de Paz y Salvo
        nueva_solicitud = SolicitudPazSalvo(
            ex_funcionario_id=usuario.id,
            estado='CREADO'
        )
        db.session.add(nueva_solicitud)
        db.session.commit()

        flash(f'Trámite iniciado correctamente para el ex funcionario {nombres} {apellidos}.', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('paz_salvo/crear.html')