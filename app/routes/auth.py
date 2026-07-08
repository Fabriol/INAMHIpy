from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

# 1. Importamos la tabla de Auditoría y las utilidades de tiempo
from app.models.base import db, Usuario, LogAuditoria
from datetime import datetime, timedelta, timezone 

# Creamos el Blueprint
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/dashboard')

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and check_password_hash(usuario.password_hash, password):
            if not usuario.activo:
                flash('Su cuenta ha sido desactivada.', 'danger')
                return redirect(url_for('auth.login'))
            
            login_user(usuario)
            
            # ==========================================================
            # MAGIA DE AUDITORÍA: HORA EXACTA DE ECUADOR Y RASTREO
            # ==========================================================
            # Forzamos la zona horaria a UTC-5 (Ecuador continental)
            ecuador_tz = timezone(timedelta(hours=-5))
            hora_real_ec = datetime.now(ecuador_tz).strftime("%d/%m/%Y %H:%M:%S")
            
            # Extraemos el rol si lo tiene, para que quede en el historial
            rol_nombre = usuario.rol.nombre if usuario.rol else "Sin Rol"

            nuevo_log = LogAuditoria(
                usuario_id=usuario.id,
                modulo='Autenticación',
                accion='INICIO DE SESIÓN',
                detalle=f"Ingreso exitoso al sistema. Rol: {rol_nombre}. Hora ECU: {hora_real_ec}"
            )
            db.session.add(nuevo_log)
            db.session.commit()
            # ==========================================================

            return redirect('/dashboard')
        else:
            flash('Correo electrónico o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    # Podemos auditar la salida también si lo deseas en el futuro
    logout_user()
    return redirect(url_for('auth.login'))