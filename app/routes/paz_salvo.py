from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, send_file, abort, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
import os
import io

# Generador de Códigos QR nativos en formato SVG (Vectores, no imágenes)
import qrcode
import qrcode.image.svg

# Modelos
from app.models.base import db, Usuario, Rol, SolicitudPazSalvo, Respuesta, LogAuditoria
from app.services.pdf_service import generar_documento_paz_salvo

# Librerías criptográficas para la firma PAdES
from pyhanko.sign import signers
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.fields import SigFieldSpec, append_signature_field


paz_salvo_bp = Blueprint('paz_salvo', __name__)

# ====================================================================
# FUNCIÓN GLOBAL: GENERADOR DE QR VECTORIAL EXACTO A FIRMAEC
# ====================================================================
@paz_salvo_bp.app_template_global()
def generar_qr_svg(nombre):
    """Genera un QR real en formato SVG para que WeasyPrint lo dibuje nativamente en el PDF"""
    if not nombre:
        nombre = "RESPONSABLE"
        
    # Datos que hacen que el QR se vea complejo e idéntico al de la foto
    data = f"Validar únicamente en FirmaEC.\nFirmado electrónicamente por:\n{nombre}"
    
    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=4, # Versión 4 garantiza esa densidad visual del QR de la foto
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=0,
        image_factory=factory
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image()
    
    # Extraer únicamente la etiqueta <svg> limpia
    svg_str = img.to_string(encoding='unicode')
    if "<?xml" in svg_str:
        svg_str = svg_str.split("?>")[-1].strip()
        
    # Inyectar la clase CSS para que coincida con tu diseño
    svg_str = svg_str.replace('<svg ', '<svg class="firmaec-qr" preserveAspectRatio="xMidYMid meet" ')
    return svg_str


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
# 3. RUTA: LLENAR FORMULARIO (SEMÁFORO Y VISTAS AISLADAS)
# ====================================================================
@paz_salvo_bp.route('/paz-salvo/llenar/<int:solicitud_id>', methods=['GET'])
@login_required
def llenar_formulario(solicitud_id):
    solicitud = SolicitudPazSalvo.query.get_or_404(solicitud_id)
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    usuarios_disponibles = Usuario.query.filter(Usuario.rol_id != 1).all() 
    
    respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
    datos_diccionario = {r.campo_formulario: r.valor_respuesta for r in respuestas_db}
    
    asignaciones_dict = {}
    for r in respuestas_db:
        if r.usuario_asignado_id:
            user_asignado = Usuario.query.get(r.usuario_asignado_id)
            if user_asignado:
                asignaciones_dict[r.campo_formulario] = f"{user_asignado.nombres} {user_asignado.apellidos}"

    campos_asignados_al_usuario = []
    campos_bloqueados = []
    
    for r in respuestas_db:
        es_su_campo = (r.usuario_asignado_id == current_user.id)
        
        if es_su_campo:
            campos_asignados_al_usuario.append(r.campo_formulario)
            if r.valor_respuesta and r.valor_respuesta.strip() != "":
                campos_bloqueados.append(r.campo_formulario)

        if current_user.rol.nombre != 'Administrador' and not es_su_campo:
            campos_bloqueados.append(r.campo_formulario)

    return render_template('paz_salvo/llenar_formulario.html', 
                           solicitud=solicitud, 
                           usuarios_disponibles=usuarios_disponibles,
                           campos_bloqueados=campos_bloqueados,
                           campos_asignados_al_usuario=campos_asignados_al_usuario,
                           asignaciones_dict=asignaciones_dict,
                           datos=datos_diccionario)

# ====================================================================
# 4. RUTA: GUARDADO ATÓMICO (REGLA 5) - "TODO O NADA"
# ====================================================================
@paz_salvo_bp.route('/paz-salvo/guardar/<int:solicitud_id>', methods=['POST'])
@login_required
def guardar_formulario(solicitud_id):
    datos_formulario = request.form.to_dict()
    datos_formulario.pop('solicitud_id', None) 

    try:
        for campo, valor in datos_formulario.items():
            if not valor or valor.strip() == '' or valor == 'FIRMADO':
                continue 
            
            respuesta_existente = Respuesta.query.filter_by(solicitud_id=solicitud_id, campo_formulario=campo).first()
            
            if respuesta_existente:
                if respuesta_existente.valor_respuesta != 'FIRMADO':
                    respuesta_existente.valor_respuesta = str(valor).upper()
            else:
                db.session.add(Respuesta(
                    solicitud_id=solicitud_id, 
                    campo_formulario=campo, 
                    usuario_asignado_id=current_user.id, 
                    valor_respuesta=str(valor).upper()
                ))

        db.session.commit()
        
        solicitud = SolicitudPazSalvo.query.get(solicitud_id)
        solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
        respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
        
        directorio_temp = os.path.join(current_app.root_path, 'static', 'temp')
        os.makedirs(directorio_temp, exist_ok=True)
        ruta_pdf = os.path.join(directorio_temp, f'PazSalvo_{solicitud.id}.pdf')
        
        generar_documento_paz_salvo(solicitud, solicitud.ex_funcionario, respuestas_db, ruta_pdf)
        
        flash('Trámite guardado exitosamente. Los datos han sido sellados de forma inmutable.', 'success')
        
    except Exception as e:
        db.session.rollback() 
        print(f"Error en guardado atómico: {e}")
        flash('Error de conexión. No se guardó ninguna información para proteger el trámite.', 'danger')

    return redirect(url_for('paz_salvo.llenar_formulario', solicitud_id=solicitud_id))

# ====================================================================
# 5. RUTA: ESPEJO EN TIEMPO REAL (HTMX - SIN GUARDADO BD)
# ====================================================================
@paz_salvo_bp.route('/actualizar-espejo', methods=['POST'])
@login_required
def actualizar_espejo():
    datos_en_vivo = request.form.to_dict()
    solicitud_id = datos_en_vivo.get('solicitud_id')
    
    if not solicitud_id:
        return ""
        
    solicitud = SolicitudPazSalvo.query.get(solicitud_id)
    if not solicitud:
         return ""
         
    solicitud.ex_funcionario = Usuario.query.get(solicitud.ex_funcionario_id)
    
    respuestas_db = Respuesta.query.filter_by(solicitud_id=solicitud.id).all()
    datos_combinados = {r.campo_formulario: r.valor_respuesta for r in respuestas_db}
    
    for k, v in datos_en_vivo.items():
        if v.strip() != "":
            datos_combinados[k] = str(v).upper()

    return render_template('paz_salvo/partials/hoja_espejo.html', 
                           solicitud=solicitud, 
                           datos=datos_combinados)

# ====================================================================
# 6. RUTA: GENERACIÓN Y DESCARGA DEL PDF A4
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
# 7. RUTA: FIRMA CRIPTOGRÁFICA PAdES (INVISIBLE A NIVEL PDF)
# ====================================================================

from pyhanko.sign import signers
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign.fields import SigFieldSpec, append_signature_field
import os

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
        # A. Cargar Certificado y extraer nombre limpio
        signer = signers.SimpleSigner.load_pkcs12(ruta_temp_p12, passphrase=password.encode('utf-8'))
        diccionario_certificado = signer.signing_cert.subject.native
        if 'common_name' in diccionario_certificado:
            nombre_firmante = diccionario_certificado['common_name']
        else:
            texto_bruto = signer.signing_cert.subject.human_friendly
            nombre_firmante = texto_bruto.split(',')[0].replace('COMMON NAME:', '').strip()

        # B. Guardar variables en BD
        res_firma = Respuesta.query.filter_by(solicitud_id=solicitud_id, campo_formulario=campo_firma).first()
        if res_firma: res_firma.valor_respuesta = 'FIRMADO'
        else: db.session.add(Respuesta(solicitud_id=solicitud_id, campo_formulario=campo_firma, usuario_asignado_id=current_user.id, valor_respuesta='FIRMADO'))
        
        campo_nombre_firma = f"{campo_firma}_nombre"
        resp_nombre = Respuesta.query.filter_by(solicitud_id=solicitud_id, campo_formulario=campo_nombre_firma).first()
        if resp_nombre: resp_nombre.valor_respuesta = nombre_firmante.upper()
        else: db.session.add(Respuesta(solicitud_id=solicitud_id, campo_formulario=campo_nombre_firma, usuario_asignado_id=current_user.id, valor_respuesta=nombre_firmante.upper()))
        db.session.commit()

        # C. Generar PDF (El HTML dibujará tu QR y tu nombre)
        ruta_pdf_original = os.path.join(directorio_temp, f'PazSalvo_{solicitud_id}.pdf')
        solicitud_temp = SolicitudPazSalvo.query.get(solicitud_id)
        solicitud_temp.ex_funcionario = Usuario.query.get(solicitud_temp.ex_funcionario_id)
        resp_temp = Respuesta.query.filter_by(solicitud_id=solicitud_id).all()
        generar_documento_paz_salvo(solicitud_temp, solicitud_temp.ex_funcionario, resp_temp, ruta_pdf_original)

        # D. FIRMA CRIPTOGRÁFICA INVISIBLE (Sin "style" para evitar el error 500)
        from pyhanko.sign import fields # Importación necesaria para el PAdES estricto
        
        with open(ruta_pdf_original, 'rb') as inf:
            w = IncrementalPdfFileWriter(inf)
            
            # Caja en 0,0,0,0 asegura que pyHanko no tape tu diseño HTML
            append_signature_field(w, SigFieldSpec(sig_field_name=campo_firma, box=(0, 0, 0, 0)))
            
            # Subfilter PADES asegura validación del Gobierno (FirmaEC)
            meta = signers.PdfSignatureMetadata(
                field_name=campo_firma,
                subfilter=fields.SigSeedSubFilter.PADES
            )
            
            # Firmamos SIN el argumento style
            pdf_en_memoria = signers.sign_pdf(w, signature_meta=meta, signer=signer)

        with open(ruta_pdf_original, 'wb') as outf:
            pdf_en_memoria.seek(0)
            outf.write(pdf_en_memoria.read())
        
        if os.path.exists(ruta_temp_p12): os.remove(ruta_temp_p12)
        return jsonify({'status': 'success', 'mensaje': 'Firma estampada'}), 200

    except Exception as e:
        if os.path.exists(ruta_temp_p12): os.remove(ruta_temp_p12)
        return jsonify({'mensaje': f'Error de firma: {str(e)}'}), 500