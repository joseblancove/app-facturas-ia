# app.py - VERSIÓN FINAL (LÓGICA DE FACTURAS)
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
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 1. CONFIGURACIÓN ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
SHEET_ID = os.environ.get("SHEET_ID")
GOOGLE_CREDS_JSON_STRING = os.environ.get("GOOGLE_CREDS_JSON_STRING")

genai.configure(api_key=GEMINI_API_KEY)

GOOGLE_CREDS_DICT = json.loads(GOOGLE_CREDS_JSON_STRING)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
WORKSHEET_NAME = 'Master_Data'

# --- 2. INICIALIZACIÓN ---
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- FUNCIONES AUXILIARES ---
def create_drive_folder_and_upload(files_to_upload, folder_name):
    try:
        creds = service_account.Credentials.from_service_account_info(GOOGLE_CREDS_DICT, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        folder_metadata = {'name': folder_name, 'parents': [DRIVE_FOLDER_ID], 'mimeType': 'application/vnd.google-apps.folder'}
        folder = service.files().create(body=folder_metadata, fields='id, webViewLink').execute()
        new_folder_id = folder.get('id')
        folder_link = folder.get('webViewLink')
        for filepath, filename in files_to_upload:
            file_metadata = {'name': filename, 'parents': [new_folder_id]}
            media = MediaFileUpload(filepath, mimetype='image/jpeg', resumable=True)
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return folder_link
    except Exception as e:
        print(f"Error al interactuar con Drive: {e}")
        return None

# --- RUTAS ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        # Nombres de variables actualizados para la lógica de facturas
        entity_name = request.form['entity_name']
        project_name = request.form['project_name']
        doc_type = request.form['doc_type']
        accounting_month = request.form['accounting_month']
        batch_id = request.form.get('batch_id', '')

        image_files = request.files.getlist('invoice_images[]')
        if not image_files:
            return jsonify({'status': 'error', 'message': 'No se recibieron archivos.'}), 400

        content_for_ai, files_for_drive = [], []
        
        prompt = f"""
        INSTRUCCIÓN CRÍTICA: Eres un experto contable que extrae datos de facturas y tickets de España. Recibirás un lote de {len(image_files)} imágenes que pertenecen al MISMO documento o evento. Tu tarea es consolidar toda la información en UN ÚNICO objeto JSON.

        REGLAS:
        1. Examina TODAS las imágenes para obtener una visión completa.
        2. Si una misma métrica aparece en varias imágenes, usa el valor que parezca más correcto.
        3. Extrae los siguientes campos: 'emisor_nombre', 'emisor_cif', 'numero_factura', 'fecha_factura', 'base_imponible', 'tipo_iva', 'cuota_iva', 'total_factura'.
        4. Los montos deben ser números (usando punto decimal), las fechas en formato AAAA-MM-DD.
        5. Tu respuesta DEBE ser ÚNICAMENTE el objeto JSON. No incluyas explicaciones ni formato markdown.
        """
        content_for_ai.append(prompt)

        for image_file in image_files:
            filepath = os.path.join(UPLOAD_FOLDER, image_file.filename)
            image_file.save(filepath)
            files_for_drive.append((filepath, image_file.filename))
            content_for_ai.append(PIL.Image.open(filepath))
            
        generation_config = GenerationConfig(response_mime_type="application/json")
        model = genai.GenerativeModel('gemini-1.5-flash-latest', generation_config=generation_config)
        response = model.generate_content(content_for_ai)
        consolidated_metrics = json.loads(response.text)

        folder_name = f"{entity_name} - {project_name} - {batch_id or 'General'}-{datetime.datetime.now().strftime('%Y%m%d')}"
        drive_folder_link = create_drive_folder_and_upload(files_for_drive, folder_name)

        creds_gspread = gspread.service_account_from_dict(GOOGLE_CREDS_DICT)
        workbook = creds_gspread.open_by_key(SHEET_ID)
        sheet = workbook.worksheet(WORKSHEET_NAME)
        
        new_row = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            entity_name, project_name, doc_type, accounting_month, batch_id,
            consolidated_metrics.get('emisor_nombre'),
            consolidated_metrics.get('emisor_cif'),
            consolidated_metrics.get('numero_factura'),
            consolidated_metrics.get('fecha_factura'),
            consolidated_metrics.get('base_imponible'),
            consolidated_metrics.get('tipo_iva'),
            consolidated_metrics.get('cuota_iva'),
            consolidated_metrics.get('total_factura'),
            drive_folder_link
        ]
        sheet.append_row(new_row, table_range="A1")

        return jsonify({'status': 'success', 'message': 'Lote procesado y consolidado con éxito.'}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)