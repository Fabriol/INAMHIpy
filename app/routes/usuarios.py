import unicodedata
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from app.models.base import db, Usuario, Rol
from sqlalchemy.exc import IntegrityError

usuarios_bp = Blueprint('usuarios', __name__)

def _quitar_tildes(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def _generar_usuario_correo(nombres, apellidos, dominio):
    primer_nombre = _quitar_tildes(nombres.strip().split()[0]) if nombres and nombres.strip() else ''
    primer_apellido = _quitar_tildes(apellidos.strip().split()[0]) if apellidos and apellidos.strip() else ''
    usuario = (primer_nombre[:1] + primer_apellido).lower()
    return f"{usuario}@{dominio}"

@usuarios_bp.route('/usuarios', methods=['GET', 'POST'])
@login_required
def gestionar_usuarios():
    if current_user.rol.nombre not in ['Administrador', 'Talento Humano - Recepción Documentos']:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        nombres = request.form.get('nombres')
        apellidos = request.form.get('apellidos')
        cedula = request.form.get('cedula') # Mantenemos la cédula para la BD
        usuario = request.form.get('usuario')
        password = request.form.get('password')
        rol_id = request.form.get('rol_id')

        # Convertimos el "usuario" autogenerado en un correo institucional
        email = f"{usuario}@inamhi.ec"

        if Usuario.query.filter_by(email=email).first() or Usuario.query.filter_by(cedula=cedula).first():
            flash('Error: El usuario o la cédula ya existen.', 'danger')
        else:
            nuevo_usuario = Usuario(
                nombres=nombres, apellidos=apellidos, cedula=cedula, email=email,
                password_hash=generate_password_hash(password), rol_id=rol_id, activo=True
            )
            db.session.add(nuevo_usuario)
            db.session.commit()
            flash(f'Usuario {usuario} creado exitosamente.', 'success')
            
        return redirect(url_for('usuarios.gestionar_usuarios'))

    usuarios = Usuario.query.order_by(Usuario.id.asc()).all()
    roles = Rol.query.all()
    return render_template('admin/usuarios.html', usuarios=usuarios, roles=roles)

# --- NUEVAS RUTAS PARA HABILITAR LOS BOTONES ---

@usuarios_bp.route('/usuarios/editar/<int:id>', methods=['POST'])
@login_required
def editar_usuario(id):
    u = Usuario.query.get_or_404(id)
    nuevos_nombres = request.form.get('nombres')
    nuevos_apellidos = request.form.get('apellidos')

    if nuevos_nombres != u.nombres or nuevos_apellidos != u.apellidos:
        dominio = u.email.split('@')[-1] if u.email and '@' in u.email else 'inamhi.ec'
        u.email = _generar_usuario_correo(nuevos_nombres, nuevos_apellidos, dominio)

    u.nombres = nuevos_nombres
    u.apellidos = nuevos_apellidos
    u.rol_id = request.form.get('rol_id')
    u.activo = True if request.form.get('estado') == 'ACTIVO' else False
    
    nuevo_pass = request.form.get('password')
    if nuevo_pass: # Solo si escribió una nueva contraseña
        u.password_hash = generate_password_hash(nuevo_pass)
        
    db.session.commit()
    flash('Usuario actualizado correctamente.', 'success')
    return redirect(url_for('usuarios.gestionar_usuarios'))

@usuarios_bp.route('/usuarios/estado/<int:id>')
@login_required
def cambiar_estado(id):
    u = Usuario.query.get_or_404(id)
    u.activo = not u.activo # Invierte el estado
    db.session.commit()
    estado_str = "ACTIVO" if u.activo else "INHABILITADO"
    flash(f'El usuario pasó a estado {estado_str}.', 'success')
    return redirect(url_for('usuarios.gestionar_usuarios'))

@usuarios_bp.route('/usuarios/eliminar/<int:id>')
@login_required
def eliminar_usuario(id):
    u = Usuario.query.get_or_404(id)
    try:
        db.session.delete(u)
        db.session.commit()
        flash('Usuario eliminado del sistema.', 'success')
    except IntegrityError:
        db.session.rollback()
        flash('No se puede eliminar a este usuario porque tiene trámites de Paz y Salvo u otros '
              'registros asociados en el sistema. Si ya no debe tener acceso, inhabilítelo en su lugar.', 'danger')
    return redirect(url_for('usuarios.gestionar_usuarios'))