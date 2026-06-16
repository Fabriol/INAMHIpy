import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models.base import db, SolicitudPazSalvo, Usuario
from app.services.firma_service import validar_firma_p12

firma_bp = Blueprint('firma', __name__)

@firma_bp.route('/paz-salvo/subir-firma/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
def subir_firma(solicitud_id):
    if current_user.rol.nombre != 'Ex Funcionario':
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('dashboard.index'))

    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)

    if request.method == 'POST':
        if 'pdf_firmado' not in request.files:
            flash('No se seleccionó ningún archivo.', 'danger')
            return redirect(request.url)
            
        archivo = request.files['pdf_firmado']
        
        if archivo.filename == '':
            flash('No se seleccionó ningún archivo.', 'danger')
            return redirect(request.url)

        if archivo and archivo.filename.endswith('.pdf'):
            # Guardamos el archivo subido en el servidor
            nombre_seguro = secure_filename(f"Firmado_{current_user.cedula}_{archivo.filename}")
            directorio_firmas = os.path.join('app', 'static', 'firmas')
            os.makedirs(directorio_firmas, exist_ok=True)
            
            ruta_guardado = os.path.join(directorio_firmas, nombre_seguro)
            archivo.save(ruta_guardado)
            
            # MAGIA: Enviamos a validar la criptografía del certificado .p12
            es_valida, resultado = validar_firma_p12(ruta_guardado)
            
            if es_valida:
                # Regla de Negocio: Se aprueba el trámite, se guarda metadata y se bloquea al usuario
                solicitud.estado = 'APROBADO'
                solicitud.pdf_firmado_path = ruta_guardado
                solicitud.certificado_valido = True
                solicitud.certificado_metadata = resultado
                
                # Bloqueamos acceso futuro del Ex Funcionario
                current_user.activo = False 
                
                db.session.commit()
                flash('¡Firma electrónica validada con éxito! Su proceso de Paz y Salvo ha concluido.', 'success')
                return redirect(url_for('auth.logout')) # Lo sacamos del sistema
            else:
                # Si falla (era una imagen, estaba alterado, etc.)
                os.remove(ruta_guardado) # Borramos el archivo falso
                flash(resultado, 'danger')
                return redirect(request.url)
        else:
            flash('Solo se permiten archivos en formato PDF.', 'danger')

    return render_template('paz_salvo/subir_firma.html', solicitud=solicitud)