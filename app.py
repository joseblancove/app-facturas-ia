# app.py - VERSIÓN 13.1 (CORRECCIÓN FINAL DE CREDENCIALES DE DRIVE)
import os
import json
import datetime
import traceback
from flask import Flask, request, render_template, jsonify
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from google.api_core import exceptions as google_exceptions
import PIL.Image
import gspread
from google.oauth2 import service_account # Usaremos esta librería para ambas credenciales
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 1. CONFIGURACIÓN DE PRODUCCIÓN ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
SHEET_ID = os.environ.get("SHEET_ID")
WORKSHEET_NAME = 'Master_Data'
GOOGLE_CREDS_JSON_STRING = os.environ.get("GOOGLE_CREDS_JSON_STRING")

genai.configure(api_key=GEMINI_API_KEY)

GOOGLE_CREDS_DICT = json.loads(GOOGLE_CREDS_JSON_STRING)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# --- 2. INICIALIZACIÓN ---
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- FUNCIÓN DE DRIVE CON LA CORRECCIÓN APLICADA ---
def create_drive_folder_and_upload(files_to_upload, folder_name):
    try:
        # ¡CORRECCIÓN! Ahora usa from_service_account_info para leer del diccionario
        creds = service_account.Credentials.from_service_account_info(GOOGLE_CREDS_DICT, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        
        folder_metadata = {'name': folder_name, 'parents': [DRIVE_FOLDER_ID], 'mimeType': 'application/vnd.google-apps.folder'}
        folder = service.files().create(body=folder_metadata, fields='id, webViewLink').execute()
        new_folder_id = folder.get('id')
        folder_link = folder.get('webViewLink')
        
        for filepath, filename in files_to_upload:
            file_metadata = {'name': filename, 'parents': [new_folder_id]}
            media = MediaFileUpload(filepath, mimetype='image/png', resumable=True)
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        return folder_link
    except Exception as e:
        print(f"Error al interactuar con Drive: {e}")
        return None

# --- 3. RUTAS DE LA APLICACIÓN ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        # ... (lógica para recibir formulario no cambia) ...
        campaign = request.form['campaign_name']
        influencer = request.form['influencer_name']
        platform = request.form['platform']
        format_type = request.form['format']
        content_id = request.form.get('content_id', '')
        image_files = request.files.getlist('metric_images[]')

        if not image_files:
            return jsonify({'status': 'error', 'message': 'No se recibieron archivos.'}), 400

        # ... (lógica de Gemini no cambia) ...
        content_for_ai, files_for_drive = [], []
        prompt = f"""
INSTRUCCIÓN CRÍTICA: Recibirás un lote de {len(image_files)} imágenes que pertenecen a la MISMA publicación o contenido. Tu tarea es actuar como un analista de datos y consolidar toda la información que encuentres en UN ÚNICO objeto JSON.

REGLAS DE CONSOLIDACIÓN:
1. Examina TODAS las imágenes antes de responder.
2. Si una misma métrica (ej: 'likes') aparece en varias imágenes, utiliza el valor numérico más alto y más completo que encuentres.
3. Rellena cada campo del JSON con la mejor información disponible entre todas las imágenes.
4. ¡IMPORTANTE! Convierte siempre abreviaturas ('K', 'M') a números completos (ej: 2.5K a 2500, 1.2M a 1200000).
5. Si después de examinar todas las imágenes, no encuentras NINGUNA métrica, debes explicar por qué en el campo 'extraction_notes'. Por ejemplo: "Las imágenes no contienen contadores numéricos visibles de métricas."
6. Tu respuesta DEBE ser ÚNICAMENTE el objeto JSON, sin ningún otro texto.

El formato requerido es:
{{"likes": null, "comments": null, "shares": null, "saves": null, "views": null, "reach": null, "link_clicks": null, "clicks_stickers": null, "extraction_notes": "Extracción exitosa."}}
"""
        content_for_ai.append(prompt)
        for image_file in image_files:
            filepath = os.path.join(UPLOAD_FOLDER, image_file.filename)
            image_file.save(filepath)
            files_for_drive.append((filepath, image_file.filename))
            content_for_ai.append(PIL.Image.open(filepath))
        model = genai.GenerativeModel('gemini-1.5-flash-latest', generation_config=GenerationConfig(response_mime_type="application/json"))
        response = model.generate_content(content_for_ai)
        consolidated_metrics = json.loads(response.text)
        
        # ... (lógica para subir a Drive no cambia) ...
        folder_name = f"{campaign} - {influencer} - {content_id or 'General'}-{datetime.datetime.now().strftime('%Y%m%d')}"
        drive_folder_link = create_drive_folder_and_upload(files_for_drive, folder_name)

        # --- Conexión a Google Sheets usando el diccionario de credenciales ---
        creds_gspread = gspread.service_account_from_dict(GOOGLE_CREDS_DICT)
        workbook = creds_gspread.open_by_key(SHEET_ID)
        sheet = workbook.worksheet(WORKSHEET_NAME)
        
# --- PREPARAMOS LA NUEVA FILA CON 17 COLUMNAS ---
        # Obtenemos el nuevo campo del formulario
        organic_paid = request.form.get('organic_paid', 'Organic')

        # NOTA: En la columna 'image_link', guardaremos el enlace a la CARPETA de Drive.
        # Esto es más robusto ya que a menudo subes varias capturas, 
        # y así tienes toda la evidencia en un solo lugar.
        evidence_link = drive_folder_link

        new_row = [
            # 1. timestamp
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            # 2. campaign_name
            campaign,
            # 3. influencer_name
            influencer,
            # 4. platform
            platform,
            # 5. format
            format_type,
            # 6. content_id
            content_id,
            # 7. Organic_Paid (NUEVO)
            organic_paid,
            # 8. Reach
            consolidated_metrics.get('reach'),
            # 9. Views
            consolidated_metrics.get('views'),
            # 10. Likes
            consolidated_metrics.get('likes'),
            # 11. Comments
            consolidated_metrics.get('comments'),
            # 12. Saved
            consolidated_metrics.get('saves'),
            # 13. Shares
            consolidated_metrics.get('shares'),
            # 14. Link_Clicks (NUEVO)
            consolidated_metrics.get('link_clicks'),
            # 15. Clicks_Stickers (NUEVO)
            consolidated_metrics.get('clicks_stickers'),
            # 16. image_link (es el link a la carpeta de Drive)
            evidence_link,
            # 17. extraction_notes
            consolidated_metrics.get('extraction_notes')
        ]
        
        sheet.append_row(new_row, table_range="A1")

        # MEJORA DE FEEDBACK: Devolvemos los datos procesados al cliente
        response_data = {
            'status': 'success',
            'message': 'Datos procesados y guardados exitosamente.',
            'processed_data': {
                'metrics': consolidated_metrics,
                'drive_folder_link': evidence_link
            }
        }
        return jsonify(response_data), 200
    except google_exceptions.RetryError as e:
        return jsonify({'status': 'error', 'message': 'El servicio de IA está sobrecargado. Inténtalo más tarde.'}), 503
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)