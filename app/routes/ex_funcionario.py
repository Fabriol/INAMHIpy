from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.base import db, SolicitudPazSalvo

ex_funcionario_bp = Blueprint('ex_funcionario', __name__)

@ex_funcionario_bp.route('/mis-datos', methods=['GET', 'POST'])
@login_required
def mis_datos():
    # Validamos que solo el Ex Funcionario entre aquí
    if current_user.rol.nombre != 'Ex Funcionario':
        flash('Acceso denegado. Esta sección es solo para Ex Funcionarios.', 'danger')
        return redirect(url_for('dashboard.index'))

    # Buscamos su trámite activo
    solicitud = SolicitudPazSalvo.query.filter_by(ex_funcionario_id=current_user.id).first()

    if request.method == 'POST':
        # En una versión completa, aquí guardaríamos celular, provincia, etc. en la DB
        # Por ahora, actualizamos el estado para que el proceso avance a las áreas (TICs, Financiera)
        solicitud.estado = 'EN_PROGRESO'
        db.session.commit()
        
        flash('Datos personales guardados. Tu proceso ha sido enviado a las áreas correspondientes.', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('paz_salvo/mis_datos.html', solicitud=solicitud)


# =========================================================
# API PARA HTMX: Selector Dinámico de Provincia -> Cantón
# =========================================================
@ex_funcionario_bp.route('/api/cantones')
def api_cantones():
    provincia_seleccionada = request.args.get('provincia')
    
    # Base de datos simulada para el dinamismo de HTMX
    diccionario_provincias = {
        "Pichincha": ["Quito", "Cayambe", "Mejía", "Pedro Moncayo", "Rumiñahui", "San Miguel de Los Bancos", "Pedro Vicente Maldonado", "Puerto Quito"],
        "Guayas": ["Guayaquil", "Daule", "Durán", "Samborondón", "Milagro"],
        "Azuay": ["Cuenca", "Gualaceo", "Paute", "Sigsig"]
    }

    cantones = diccionario_provincias.get(provincia_seleccionada, [])
    
    # Generamos HTML puro con las opciones para que HTMX las inyecte
    html_options = '<option value="">Seleccione un cantón...</option>'
    for canton in cantones:
        html_options += f'<option value="{canton}">{canton}</option>'
    
    return html_options

# --- Agregar esto al final de app/routes/ex_funcionario.py ---

@ex_funcionario_bp.route('/actualizar-espejo', methods=['POST'])
@login_required
def actualizar_espejo():
    # Recibimos TODO lo que el usuario está escribiendo en el formulario izquierdo en tiempo real
    datos_en_vivo = request.form.to_dict()
    
    # Renderizamos ÚNICAMENTE la plantilla de la hoja espejo (el lado derecho)
    # inyectándole los datos que está tipeando ahora mismo.
    return render_template('paz_salvo/partials/hoja_espejo.html', datos=datos_en_vivo, usuario=current_user)