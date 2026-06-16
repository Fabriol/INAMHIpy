from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
import os

def validar_firma_p12(ruta_pdf):
    """
    Lee el PDF y busca firmas criptográficas estándar (.p12/.pfx).
    Retorna (Booleano_Validez, Mensaje_o_Metadata).
    """
    try:
        with open(ruta_pdf, 'rb') as doc:
            reader = PdfFileReader(doc)
            firmas = reader.embedded_signatures
            
            if not firmas:
                return False, "Error: El documento NO contiene firmas electrónicas reales. No se aceptan imágenes."
            
            # Tomamos la firma incrustada
            firma = firmas[0]
            
            # Validamos que el hash del documento coincida y no haya sido alterado
            # (skip_revocation evita buscar listas de revocación en internet para agilizar)
            status = validate_pdf_signature(firma, skip_revocation=True)
            
            # Extraemos la metadata legal del certificado .p12
            cert = status.signer_info.signing_cert
            nombre_firmante = cert.subject.human_friendly
            fecha_caducidad = cert.not_valid_after.strftime('%Y-%m-%d')
            
            if status.intact:
                metadata = f"Firma Íntegra. Firmante: {nombre_firmante}. Certificado válido hasta: {fecha_caducidad}."
                return True, metadata
            else:
                return False, "Error Criptográfico: El documento fue modificado o alterado después de ser firmado."
                
    except Exception as e:
        return False, f"Error al procesar el archivo o leer el certificado: {str(e)}"