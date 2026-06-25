from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, send_file, abort, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
import os

from app.models.base import db, Usuario, Rol, SolicitudPazSalvo, Respuesta, Pregunta, LogAuditoria
from app.services.pdf_service import generar_documento_paz_salvo

# Importaciones para Firma Criptográfica PAdES (FirmaEC)
from pyhanko.sign import signers
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.fields import SigFieldSpec, append_signature_field

paz_salvo_bp = Blueprint('paz_salvo', __name__)

# ==========================================
# 1. RUTA: INICIAR SOLICITUD
# ==========================================
@paz_salvo_bp.route('/paz-salvo/nueva', methods=['GET', 'POST'])
@login_required
def nueva_solicitud():
    if current_user.rol.nombre not in ['Administrador', 'Talento Humano - Recepción Documentos']:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        cedula = request.form.get('cedula', '').strip()
        username_input = request.form.get('username', '').strip()
        email_input = request.form.get('email', '').strip()

        usuario = Usuario.query.filter_by(cedula=cedula).first()
        
        if not usuario:
            correo_existente = Usuario.query.filter_by(email=email_input).first()
            if correo_existente:
                flash(f'El correo {email_input} ya está asignado.', 'danger')
                return redirect(url_for('paz_salvo.nueva_solicitud'))

            rol_ex = Rol.query.filter_by(nombre='Ex Funcionario').first()
            usuario = Usuario(
                rol_id=rol_ex.id, 
                cedula=cedula, 
                nombres=request.form.get('nombres', '').upper(),
                apellidos=request.form.get('apellidos', '').upper(),
                username=username_input,
                email=email_input,
                password_hash=generate_password_hash(cedula), 
                activo=True
            )
            db.session.add(usuario)
            db.session.commit()

        tramite_creado = SolicitudPazSalvo.query.filter_by(ex_funcionario_id=usuario.id, estado='CREADO').first()
        tramite_proceso = SolicitudPazSalvo.query.filter_by(ex_funcionario_id=usuario.id, estado='EN_PROGRESO').first()
        
        if tramite_creado or tramite_proceso:
            flash('Este ex funcionario ya cuenta con un trámite activo.', 'warning')
            return redirect(url_for('paz_salvo.nueva_solicitud'))

        nueva_solicitud = SolicitudPazSalvo(ex_funcionario_id=usuario.id, estado='CREADO')
        db.session.add(nueva_solicitud)
        
        log = LogAuditoria(usuario_id=current_user.id, modulo='Formularios', accion='NUEVO EXPEDIENTE', detalle=f"Creó expediente CI: {usuario.cedula}")
        db.session.add(log)
        db.session.commit()
        
        flash('Expediente creado exitosamente.', 'success')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=nueva_solicitud.id))

    solicitudes_db = SolicitudPazSalvo.query.order_by(SolicitudPazSalvo.id.desc()).all()
    for sol in solicitudes_db:
        sol.usuario_data = Usuario.query.get(sol.ex_funcionario_id)
        
    return render_template('paz_salvo/crear.html', solicitudes=solicitudes_db)

# ==========================================
# 2. RUTA: ASIGNAR CAMPOS (PANEL ADMINISTRADOR)
# ==========================================
@paz_salvo_bp.route('/paz-salvo/asignar-campos/<int:solicitud_id>', methods=['POST'])
@login_required
def asignar_campos(solicitud_id):
    if current_user.rol.nombre != 'Administrador':
        abort(403)
        
    bloques_seleccionados = request.form.getlist('bloques')
    usuario_asignado_id = request.form.get('usuario_asignado_id')
    
    if not bloques_seleccionados or not usuario_asignado_id:
        return "<div class='alert alert-danger py-2 mt-2'>Debe seleccionar al menos un bloque y un servidor.</div>"
        
    # Aquí iría tu lógica para guardar en la BD qué usuario debe llenar qué bloques
    # Ejemplo: AsignacionBloque(solicitud_id=solicitud_id, usuario_id=usuario_asignado_id, bloque=...)
    
    return "<div class='alert alert-success py-2 mt-2 fw-bold'><i class='bi bi-check-circle-fill'></i> Responsabilidades delegadas exitosamente.</div>"

# ==========================================
# 3. RUTA: FORMULARIO DINÁMICO
# ==========================================
@paz_salvo_bp.route('/paz-salvo/llenar/<int:solicitud_id>', methods=['GET'])
@login_required
def llenar_formulario(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    if current_user.id != solicitud.ex_funcionario_id and current_user.rol.nombre != 'Administrador':
        abort(403)
        
    # Extraemos todos los usuarios disponibles para el select del Administrador
    usuarios_disponibles = Usuario.query.filter(Usuario.rol_id != 1).all() # Ajusta el ID según tu BD
    
    # Aquí puedes enviar una lista de nombres de campos que ya están llenos para bloquearlos
    campos_bloqueados = ['nombres_apellidos', 'cedula'] # Ejemplo
    
    return render_template('paz_salvo/llenar_formulario.html', 
                           solicitud=solicitud, 
                           usuarios_disponibles=usuarios_disponibles,
                           campos_bloqueados=campos_bloqueados)

# ==========================================
# 4. RUTA: AUTOGUARDADO HTMX
# ==========================================
@paz_salvo_bp.route('/actualizar-espejo', methods=['POST'])
@login_required
def actualizar_espejo():
    datos = request.form.to_dict()
    solicitud_id = datos.get('solicitud_id')
    solicitud = SolicitudPazSalvo.query.get(solicitud_id)
    
    if solicitud:
        solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
        
        # Aquí guardas los datos que envía el HTML a tu tabla Respuestas
        # ...
        
    return render_template('paz_salvo/partials/hoja_espejo.html', datos=datos, solicitud=solicitud)

# ==========================================
# 5. RUTA: GENERACIÓN Y DESCARGA DE PDF
# ==========================================
# ==========================================
# 5. RUTA: GENERACIÓN Y DESCARGA DE PDF
# ==========================================
@paz_salvo_bp.route('/paz-salvo/descargar-pdf/<int:solicitud_id>')
@login_required
def descargar_pdf(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    
    # ¡ESTA ES LA LÍNEA QUE FALTABA PARA EVITAR EL ERROR!
    # El HTML necesita saber los datos del ex funcionario para imprimir sus nombres.
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    # Creamos la carpeta de forma segura
    directorio_temp = os.path.join(current_app.root_path, 'static', 'temp')
    os.makedirs(directorio_temp, exist_ok=True)
    ruta_pdf = os.path.join(directorio_temp, f'PazSalvo_{solicitud.id}.pdf')
    
    # Recopilamos todos los datos guardados en BD para enviarlos al PDF
    respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
    datos_diccionario = {r.campo_formulario: r.valor_respuesta for r in respuestas_db} if hasattr(Respuesta, 'campo_formulario') else {}
    
    try:
        usuario_obj = Usuario.query.get(solicitud.ex_funcionario_id)
        # ESTA FUNCIÓN ES LA CLAVE (Debe usar WeasyPrint)
        generar_documento_paz_salvo(solicitud, usuario_obj, datos_diccionario, ruta_pdf)
    except Exception as e:
        flash(f'Ocurrió un error al generar el PDF: {str(e)}', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud.id))
    
    if os.path.exists(ruta_pdf):
        log = LogAuditoria(usuario_id=current_user.id, modulo='Reportes', accion='DESCARGA PDF', detalle=f"Descargó PDF del trámite #{solicitud.id}")
        db.session.add(log)
        db.session.commit()
        return send_file(ruta_pdf, as_attachment=True, download_name=f"Paz_y_Salvo_{solicitud.id}.pdf")
    else:
        flash('El archivo PDF no se pudo generar.', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud.id))

# ==========================================
# 6. RUTA: FIRMA CRIPTOGRÁFICA PAdES (FirmaEC)
# ==========================================
@paz_salvo_bp.route('/paz-salvo/subir-firma/<int:solicitud_id>', methods=['POST'])
@login_required
def subir_firma_pades(solicitud_id):
    if 'pdf_firmado' not in request.files:
        return jsonify({'mensaje': 'No se adjuntó el certificado .p12'}), 400
        
    archivo_p12 = request.files['pdf_firmado']
    password = request.form.get('password', '')
    campo_firma = request.form.get('campo', 'Firma_Desconocida')

    try:
        p12_data = archivo_p12.read()
        signer = signers.SimpleSigner.load_pkcs12(p12_data, bpassword=password.encode('utf-8'))
    except Exception as e:
        return jsonify({'mensaje': 'La contraseña es incorrecta o el certificado es inválido.'}), 400

    directorio_temp = os.path.join(current_app.root_path, 'static', 'temp')
    ruta_pdf_original = os.path.join(directorio_temp, f'PazSalvo_{solicitud_id}.pdf')
    
    if not os.path.exists(ruta_pdf_original):
        return jsonify({'mensaje': 'El PDF base no existe. Debe dar clic en "Descargar PDF Legal" al menos una vez para crearlo.'}), 404

    try:
        with open(ruta_pdf_original, 'rb') as inf:
            w = IncrementalPdfFileWriter(inf)
            append_signature_field(w, SigFieldSpec(sig_field_name=campo_firma))
            
            with open(ruta_pdf_original, 'r+b') as outf:
                signers.sign_pdf(
                    w, signers.PdfSignatureMetadata(field_name=campo_firma),
                    signer=signer,
                    outf=outf
                )
        
        nombre_firmante = signer.cert.subject.human_friendly
        return jsonify({
            'mensaje': 'Documento encriptado y firmado con éxito.',
            'firmado_por': nombre_firmante
        }), 200

    except Exception as e:
        return jsonify({'mensaje': f'Error al estampar la firma en el PDF: {str(e)}'}), 500