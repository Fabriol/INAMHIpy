from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, send_file, abort
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
import os

from app.models.base import db, Usuario, Rol, SolicitudPazSalvo, Respuesta, Pregunta, LogAuditoria
from app.services.pdf_service import generar_documento_paz_salvo
from app.services.firma_service import validar_firma_p12

paz_salvo_bp = Blueprint('paz_salvo', __name__)

# ==========================================
# 1. RUTA: INICIAR SOLICITUD
# ==========================================
# Reemplaza solo esta función en tu app/routes/paz_salvo.py

@paz_salvo_bp.route('/paz-salvo/nueva', methods=['GET', 'POST'])
@login_required
def nueva_solicitud():
    if current_user.rol.nombre not in ['Administrador', 'Talento Humano - Recepción Documentos']:
        flash('Acceso denegado. No tiene permisos para gestionar este módulo.', 'danger')
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        cedula = request.form.get('cedula', '').strip()
        username_input = request.form.get('username', '').strip()
        email_input = request.form.get('email', '').strip()

        # VALIDACIÓN 1: Verificamos si la cédula ya existe en la base de datos
        usuario = Usuario.query.filter_by(cedula=cedula).first()
        
        if not usuario:
            # VALIDACIÓN 2: Verificamos que el correo generado no pertenezca a OTRO usuario
            correo_existente = Usuario.query.filter_by(email=email_input).first()
            if correo_existente:
                flash(f'El correo {email_input} ya está asignado a otro funcionario. Por favor, modifique manualmente el nombre de usuario (Ej: agregue un número al final).', 'danger')
                return redirect(url_for('paz_salvo.nueva_solicitud'))

            rol_ex = Rol.query.filter_by(nombre='Ex Funcionario').first()
            
            # Guardamos el usuario con el nuevo campo username y el correo institucional
            usuario = Usuario(
                rol_id=rol_ex.id, 
                cedula=cedula, 
                nombres=request.form.get('nombres', '').upper(),
                apellidos=request.form.get('apellidos', '').upper(),
                username=username_input,   # <-- NUEVO DATO GUARDADO
                email=email_input,         # <-- CORREO AUTOCOMPLETADO
                password_hash=generate_password_hash(cedula), 
                activo=True
            )
            db.session.add(usuario)
            db.session.commit()

        # VALIDACIÓN 3: Prevenir duplicidad de trámites (Que no tenga 2 trámites abiertos)
        tramite_creado = SolicitudPazSalvo.query.filter_by(ex_funcionario_id=usuario.id, estado='CREADO').first()
        tramite_proceso = SolicitudPazSalvo.query.filter_by(ex_funcionario_id=usuario.id, estado='EN_PROGRESO').first()
        
        if tramite_creado or tramite_proceso:
            flash('Este ex funcionario ya cuenta con un trámite activo en el sistema. Utilice el botón "Abrir y Llenar Formulario" en la tabla inferior.', 'warning')
            return redirect(url_for('paz_salvo.nueva_solicitud'))

        # Si pasa todas las validaciones, se crea el expediente
        nueva_solicitud = SolicitudPazSalvo(ex_funcionario_id=usuario.id, estado='CREADO')
        db.session.add(nueva_solicitud)
        
        log = LogAuditoria(
            usuario_id=current_user.id, modulo='Formularios', accion='NUEVO EXPEDIENTE', 
            detalle=f"Creó expediente de Paz y Salvo para CI: {usuario.cedula} ({usuario.email})"
        )
        db.session.add(log)
        db.session.commit()
        
        flash('Expediente institucional creado exitosamente. Proceda con el llenado de datos.', 'success')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=nueva_solicitud.id))

    # Renderiza la vista y envía la lista de solicitudes para la tabla inferior
    solicitudes_db = SolicitudPazSalvo.query.order_by(SolicitudPazSalvo.id.desc()).all()
    for sol in solicitudes_db:
        sol.usuario_data = Usuario.query.get(sol.ex_funcionario_id)
        
    return render_template('paz_salvo/crear.html', solicitudes=solicitudes_db)

# ==========================================
# 2. RUTA: FORMULARIO DINÁMICO
# ==========================================
@paz_salvo_bp.route('/paz-salvo/llenar/<int:solicitud_id>', methods=['GET'])
@login_required
def llenar_formulario(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    if current_user.id != solicitud.ex_funcionario_id and current_user.rol.nombre != 'Administrador':
        abort(403)
        
    preguntas = Pregunta.query.all()
    # SOLUCIÓN: Buscamos el nombre del rol manualmente y se lo pegamos a la pregunta
    for p in preguntas:
        rol_obj = Rol.query.get(p.rol_asignado_id)
        p.area_nombre = rol_obj.nombre if rol_obj else 'ÁREA TÉCNICA'
        
    return render_template('paz_salvo/llenar_formulario.html', solicitud=solicitud, preguntas=preguntas)


# ==========================================
# 3. RUTA: AUTOGUARDADO HTMX
# ==========================================
@paz_salvo_bp.route('/actualizar-espejo', methods=['POST'])
@login_required
def actualizar_espejo():
    datos = request.form.to_dict()
    solicitud_id = datos.get('solicitud_id')
    solicitud = SolicitudPazSalvo.query.get(solicitud_id)
    cambios_registrados = []
    
    if solicitud:
        solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
        
        if datos.get('celular'):
            solicitud.ex_funcionario.celular = datos.get('celular')
        if datos.get('direccion'):
            solicitud.ex_funcionario.direccion = datos.get('direccion')

        for key, value in datos.items():
            if key.startswith('pregunta_'):
                pregunta_id = key.split('_')[1]
                respuesta = Respuesta.query.filter_by(solicitud_id=solicitud_id, pregunta_id=pregunta_id).first()
                
                if respuesta:
                    if respuesta.valor_respuesta != value:
                        cambios_registrados.append(f"P{pregunta_id} a '{value}'")
                        respuesta.valor_respuesta = value
                else:
                    cambios_registrados.append(f"P{pregunta_id} respondida '{value}'")
                    db.session.add(Respuesta(solicitud_id=solicitud_id, pregunta_id=pregunta_id, valor_respuesta=value))
        
        if cambios_registrados:
            log = LogAuditoria(
                usuario_id=current_user.id, modulo='Formularios', accion='EDICIÓN CAMPOS', 
                detalle=f"Tramite #{solicitud_id} actualizado: {', '.join(cambios_registrados)}"
            )
            db.session.add(log)
            
        db.session.commit()
    
    # SOLUCIÓN: Volvemos a enviar las preguntas al actualizar para que no desaparezcan de la tabla
    preguntas = Pregunta.query.all()
    for p in preguntas:
        rol_obj = Rol.query.get(p.rol_asignado_id)
        p.area_nombre = rol_obj.nombre if rol_obj else 'ÁREA TÉCNICA'
    
    return render_template('paz_salvo/partials/hoja_espejo.html', datos=datos, solicitud=solicitud, preguntas=preguntas)


# ==========================================
# 4. RUTA: GENERACIÓN Y DESCARGA DE PDF
# ==========================================
import os
from flask import current_app, send_file, abort, flash, redirect, url_for
from flask_login import login_required, current_user

@paz_salvo_bp.route('/paz-salvo/descargar-pdf/<int:solicitud_id>')
@login_required
def descargar_pdf(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    if current_user.id != solicitud.ex_funcionario_id and current_user.rol.nombre != 'Administrador':
        abort(403)

    respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
    respuestas_por_area = {}
    
    for r in respuestas_db:
        rol_obj = Rol.query.get(r.pregunta.rol_asignado_id)
        nombre_area = rol_obj.nombre if rol_obj else 'ÁREA TÉCNICA'
        respuestas_por_area.setdefault(nombre_area, []).append({'pregunta': r.pregunta.enunciado, 'valor': r.valor_respuesta})

    # SOLUCIÓN DE LA RUTA: current_app.root_path encuentra la ruta exacta sin duplicar carpetas
    directorio_temp = os.path.join(current_app.root_path, 'static', 'temp')
    os.makedirs(directorio_temp, exist_ok=True) # Crea la carpeta si no existe
    
    ruta_pdf = os.path.join(directorio_temp, f'PazSalvo_{solicitud.id}.pdf')
    
    log = LogAuditoria(usuario_id=current_user.id, modulo='Reportes', accion='DESCARGA PDF', detalle=f"Descargó borrador PDF del trámite #{solicitud.id}")
    db.session.add(log)
    db.session.commit()
    
    try:
        usuario_obj = Usuario.query.get(solicitud.ex_funcionario_id)
        # Asegúrate de que esta función esté guardando correctamente el PDF en ruta_pdf
        generar_documento_paz_salvo(solicitud, usuario_obj, respuestas_por_area, ruta_pdf)
    except Exception as e:
        flash(f'Ocurrió un error al generar el PDF: {str(e)}', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud.id))
    
    if os.path.exists(ruta_pdf):
        return send_file(ruta_pdf, as_attachment=True, download_name=f"Paz_y_Salvo_{solicitud.id}.pdf")
    else:
        flash('El archivo PDF aún no se ha generado correctamente en el servidor.', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud.id))

# ==========================================
# 5. RUTA: VALIDACIÓN Y SUBIDA DE FIRMA
# ==========================================
@paz_salvo_bp.route('/paz-salvo/subir-firma/<int:solicitud_id>', methods=['POST'])
@login_required
def subir_firma_digital(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    archivo = request.files.get('pdf_firmado')
    
    if not archivo or not archivo.filename.endswith('.pdf'):
        flash('Por favor, suba un archivo PDF válido.', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud_id))

    ruta_final = os.path.join('app', 'static', 'documentos_firmados', f'Final_{solicitud.id}.pdf')
    os.makedirs(os.path.dirname(ruta_final), exist_ok=True)
    archivo.save(ruta_final)
    
    valido, mensaje = validar_firma_p12(ruta_final)
    
    if valido:
        solicitud.estado = 'COMPLETADO'
        solicitud.pdf_firmado_path = ruta_final
        
        log = LogAuditoria(
            usuario_id=current_user.id, modulo='Firma Digital', accion='FIRMA APROBADA', 
            detalle=f"FirmaEC validada para trámite #{solicitud.id}. Metadata: {mensaje}"
        )
        db.session.add(log)
        db.session.commit()
        
        flash(f'¡Trámite finalizado con éxito! {mensaje}', 'success')
    else:
        if os.path.exists(ruta_final):
            os.remove(ruta_final)
        
        log = LogAuditoria(usuario_id=current_user.id, modulo='Seguridad', accion='ALERTA FIRMA', detalle=f"Intento de firma inválida en trámite #{solicitud.id}")
        db.session.add(log)
        db.session.commit()
            
        flash(mensaje, 'danger')
            
    return redirect(url_for('dashboard.index'))


# ==========================================
# 6. RUTA: Firma Criptográfica
# ==========================================

import os
from flask import request, jsonify, current_app
from flask_login import login_required, current_user
# Importaciones para Firma Criptográfica
from pyhanko.sign import signers
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.fields import SigFieldSpec, append_signature_field

@paz_salvo_bp.route('/paz-salvo/subir-firma/<int:solicitud_id>', methods=['POST'])
@login_required
def subir_firma_pades(solicitud_id):
    # 1. Recibir los datos del modal
    if 'pdf_firmado' not in request.files:
        return jsonify({'mensaje': 'No se adjuntó el certificado .p12'}), 400
        
    archivo_p12 = request.files['pdf_firmado']
    password = request.form.get('password', '')
    campo_firma = request.form.get('campo', 'Firma_Desconocida')

    try:
        # 2. Desencriptar el certificado .p12/.pfx usando la contraseña
        p12_data = archivo_p12.read()
        signer = signers.SimpleSigner.load_pkcs12(p12_data, bpassword=password.encode('utf-8'))
    except Exception as e:
        return jsonify({'mensaje': 'La contraseña es incorrecta o el certificado es inválido.'}), 400

    # 3. Ubicar el PDF a firmar
    directorio_temp = os.path.join(current_app.root_path, 'static', 'temp')
    ruta_pdf_original = os.path.join(directorio_temp, f'PazSalvo_{solicitud_id}.pdf')
    
    # IMPORTANTE: Si ya fue firmado antes por otra persona, debemos seguir firmando SOBRE ese mismo archivo
    if not os.path.exists(ruta_pdf_original):
        return jsonify({'mensaje': 'El PDF base no ha sido generado. Primero guarde el formulario o haga clic en PDF.'}), 404

    # 4. Proceso de firma PAdES con pyHanko
    try:
        # Abrimos el PDF existente de forma incremental (para no romper firmas anteriores)
        with open(ruta_pdf_original, 'rb') as inf:
            w = IncrementalPdfFileWriter(inf)
            
            # Añadimos el campo de metadatos invisible para FirmaEC
            append_signature_field(w, SigFieldSpec(sig_field_name=campo_firma))
            
            # Escribimos la firma matemática en el documento
            with open(ruta_pdf_original, 'r+b') as outf:
                signers.sign_pdf(
                    w, signers.PdfSignatureMetadata(field_name=campo_firma),
                    signer=signer,
                    outf=outf
                )
        
        # 5. Extraer el nombre real de la persona del certificado (Para guardarlo en BD)
        nombre_firmante = signer.cert.subject.human_friendly
        
        # Opcional: Aquí debes actualizar tu base de datos para registrar que este campo fue firmado
        # respuesta = Respuesta.query.filter_by(solicitud_id=solicitud_id, campo=campo_firma).first()
        # respuesta.valor = "FIRMADO"
        # respuesta.firmado_por = nombre_firmante
        # db.session.commit()

        return jsonify({
            'mensaje': 'Documento encriptado y firmado con éxito.',
            'firmado_por': nombre_firmante
        }), 200

    except Exception as e:
        return jsonify({'mensaje': f'Error al estampar la firma en el PDF: {str(e)}'}), 500
    

    