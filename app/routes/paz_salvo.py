from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, send_file, abort, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
import os

# Modelos
from app.models.base import db, Usuario, Rol, SolicitudPazSalvo, Respuesta, LogAuditoria
from app.services.pdf_service import generar_documento_paz_salvo

# Librerías criptográficas (ESTO ES TODO LO QUE NECESITAS)
from pyhanko.sign import signers
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.fields import SigFieldSpec, append_signature_field

paz_salvo_bp = Blueprint('paz_salvo', __name__)

# ====================================================================
# 1. RUTA: CREAR NUEVA SOLICITUD
# ====================================================================
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

# ====================================================================
# 2. RUTA: DELEGAR CAMPOS (PANEL ADMINISTRADOR)
# ====================================================================
@paz_salvo_bp.route('/paz-salvo/asignar-campos/<int:solicitud_id>', methods=['POST'])
@login_required
def asignar_campos(solicitud_id):
    if current_user.rol.nombre != 'Administrador':
        return "<div class='alert alert-danger py-2 mt-2'>No tiene permisos.</div>"
        
    campos_seleccionados = request.form.getlist('campos')
    usuario_asignado_id = request.form.get('usuario_asignado_id')
    
    if not campos_seleccionados or not usuario_asignado_id:
        return "<div class='alert alert-danger py-2 mt-2'>Debe seleccionar campos y un servidor.</div>"
        
    try:
        for campo in campos_seleccionados:
            respuesta_existente = Respuesta.query.filter_by(solicitud_id=solicitud_id, campo_formulario=campo).first()
            if respuesta_existente:
                respuesta_existente.usuario_asignado_id = usuario_asignado_id
            else:
                nueva_resp = Respuesta(
                    solicitud_id=solicitud_id,
                    campo_formulario=campo,
                    usuario_asignado_id=usuario_asignado_id,
                    valor_respuesta=""
                )
                db.session.add(nueva_resp)
        db.session.commit()
        return f"<div class='alert alert-success py-2 mt-2 fw-bold'><i class='bi bi-check-circle-fill'></i> Se delegaron {len(campos_seleccionados)} campos exitosamente.</div>"
    except Exception as e:
        db.session.rollback()
        return f"<div class='alert alert-danger py-2 mt-2'>Error en BD: {str(e)}</div>"

# ====================================================================
# 3. RUTA: LLENAR FORMULARIO (Carga la vista con bloqueos)
# ====================================================================
@paz_salvo_bp.route('/paz-salvo/llenar/<int:solicitud_id>', methods=['GET'])
@login_required
def llenar_formulario(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    # Extraemos todos los usuarios (excepto ex funcionarios)
    usuarios_disponibles = Usuario.query.filter(Usuario.rol_id != 1).all() 
    
    respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
    datos_diccionario = {r.campo_formulario: r.valor_respuesta for r in respuestas_db}
    
    # Bloqueos de seguridad
    campos_bloqueados = []
    if current_user.rol.nombre != 'Administrador':
        for r in respuestas_db:
            if r.usuario_asignado_id != current_user.id:
                campos_bloqueados.append(r.campo_formulario)
            if r.valor_respuesta == 'FIRMADO':
                campos_bloqueados.append(r.campo_formulario)

    return render_template('paz_salvo/llenar_formulario.html', 
                           solicitud=solicitud, 
                           usuarios_disponibles=usuarios_disponibles,
                           campos_bloqueados=campos_bloqueados,
                           datos=datos_diccionario)

# ====================================================================
# 4. RUTA: AUTOGUARDADO HTMX
# ====================================================================
@paz_salvo_bp.route('/actualizar-espejo', methods=['POST'])
@login_required
def actualizar_espejo():
    datos = request.form.to_dict()
    solicitud_id = datos.get('solicitud_id')
    solicitud = SolicitudPazSalvo.query.get(solicitud_id)
    
    if solicitud:
        solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
        
        for key, value in datos.items():
            if key != 'solicitud_id' and value.strip() != "":
                respuesta = Respuesta.query.filter_by(solicitud_id=solicitud_id, campo_formulario=key).first()
                if respuesta:
                    respuesta.valor_respuesta = value.upper()
                else:
                    nueva_resp = Respuesta(
                        solicitud_id=solicitud_id,
                        campo_formulario=key,
                        usuario_asignado_id=current_user.id,
                        valor_respuesta=value.upper()
                    )
                    db.session.add(nueva_resp)
        db.session.commit()
        
    return render_template('paz_salvo/partials/hoja_espejo.html', datos=datos, solicitud=solicitud)

# ====================================================================
# 5. RUTA: GENERACIÓN Y DESCARGA DEL PDF A4
# ====================================================================
@paz_salvo_bp.route('/paz-salvo/descargar-pdf/<int:solicitud_id>')
@login_required
def descargar_pdf(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    directorio_temp = os.path.join(current_app.root_path, 'static', 'temp')
    os.makedirs(directorio_temp, exist_ok=True)
    ruta_pdf = os.path.join(directorio_temp, f'PazSalvo_{solicitud.id}.pdf')
    
    respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
    
    try:
        generar_documento_paz_salvo(solicitud, solicitud.ex_funcionario, respuestas_db, ruta_pdf)
    except Exception as e:
        flash(f'Error al procesar el PDF: {str(e)}', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud.id))
    
    if os.path.exists(ruta_pdf):
        return send_file(ruta_pdf, as_attachment=True, download_name=f"Paz_y_Salvo_{solicitud.id}.pdf")
    else:
        flash('El archivo PDF no se pudo generar.', 'danger')
        return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud.id))

# ====================================================================
# 6. RUTA: FIRMA CRIPTOGRÁFICA PAdES (SOLUCIÓN DIRECTA)
# ====================================================================
@paz_salvo_bp.route('/paz-salvo/subir-firma/<int:solicitud_id>', methods=['POST'])
@login_required
def subir_firma_pades(solicitud_id):
    if 'pdf_firmado' not in request.files:
        return jsonify({'mensaje': 'No se adjuntó el certificado .p12'}), 400
        
    archivo_p12 = request.files['pdf_firmado']
    password = request.form.get('password', '')
    campo_firma = request.form.get('campo', 'Firma_Desconocida')

    directorio_temp = os.path.abspath(os.path.join(current_app.root_path, 'static', 'temp'))
    os.makedirs(directorio_temp, exist_ok=True)
    ruta_temp_p12 = os.path.join(directorio_temp, f"firma_{solicitud_id}_{current_user.id}.p12")
    archivo_p12.save(ruta_temp_p12)

    try:
        # CARGA FORZADA Y MANUAL
        # Al usar argumentos nombrados (pfx_file, password, ca_chain_files), 
        # eliminamos el riesgo de "múltiples valores"
        signer = signers.SimpleSigner.load_pkcs12(
            ruta_temp_p12, 
            password.encode('utf-8')
        )
        
        # Validar signer inmediatamente
        if signer is None:
            raise Exception("El certificado cargado es nulo.")

        nombre_firmante = signer.cert.subject.human_friendly

        # ESTAMPAR FIRMA
        ruta_pdf_original = os.path.join(directorio_temp, f'PazSalvo_{solicitud_id}.pdf')
        if not os.path.exists(ruta_pdf_original):
            raise Exception("El PDF base no existe. Genere el PDF primero.")

        with open(ruta_pdf_original, 'rb') as inf:
            w = IncrementalPdfFileWriter(inf)
            append_signature_field(w, SigFieldSpec(sig_field_name=campo_firma))
            
            with open(ruta_pdf_original, 'r+b') as outf:
                signers.sign_pdf(
                    w, signers.PdfSignatureMetadata(field_name=campo_firma),
                    signer=signer,
                    outf=outf
                )

        # ACTUALIZAR BD
        respuesta_firma = Respuesta.query.filter_by(solicitud_id=solicitud_id, campo_formulario=campo_firma).first()
        if respuesta_firma:
            respuesta_firma.valor_respuesta = 'FIRMADO'
        else:
            db.session.add(Respuesta(solicitud_id=solicitud_id, campo_formulario=campo_firma, usuario_asignado_id=current_user.id, valor_respuesta='FIRMADO'))
            
        nombre_label = campo_firma.replace('_r', '_nombre_resp').replace('_sig', '_responsable')
        resp_nombre = Respuesta.query.filter_by(solicitud_id=solicitud_id, campo_formulario=nombre_label).first()
        if resp_nombre:
            resp_nombre.valor_respuesta = nombre_firmante.upper()
        else:
            db.session.add(Respuesta(solicitud_id=solicitud_id, campo_formulario=nombre_label, usuario_asignado_id=current_user.id, valor_respuesta=nombre_firmante.upper()))
            
        db.session.commit()
        
        if os.path.exists(ruta_temp_p12): os.remove(ruta_temp_p12)
        return jsonify({'status': 'success', 'mensaje': 'Firma estampada', 'firmado_por': nombre_firmante}), 200

    except Exception as e:
        if os.path.exists(ruta_temp_p12): os.remove(ruta_temp_p12)
        # Esto nos mostrará el error real en la terminal sin romper el servidor
        print(f"ERROR DE FIRMA: {str(e)}") 
        return jsonify({'mensaje': f'Error de firma: {str(e)}'}), 500