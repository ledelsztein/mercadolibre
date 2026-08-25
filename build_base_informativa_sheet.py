"""
Sube base_informativa.json a la pestana "base_informativa" del Google Sheet.

base_informativa.json es una lista de registros cargados a mano (facturas,
gastos adicionales, y en general cualquier dato que Lucas pasa y no sale de
la API de MercadoLibre/MercadoPago):
    {"fecha": "YYYY-MM-DD", "categoria": "...", "detalle": "...",
     "importe_sin_iva": 0.0, "importe_con_iva": 0.0}

Uso:
    python build_base_informativa_sheet.py
"""
import json

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file('google_token.json')
sheets = build('sheets', 'v4', credentials=creds)

registros = json.load(open('base_informativa.json', encoding='utf-8'))

HEADER = ['Fecha', 'Categoría', 'Detalle', 'Importe s/IVA', 'Importe c/IVA']
rows = [HEADER]
for r in sorted(registros, key=lambda r: r['fecha'], reverse=True):
    rows.append([r['fecha'], r['categoria'], r.get('detalle', ''), r['importe_sin_iva'], r['importe_con_iva']])

spreadsheet_id = open('sheet_id.txt').read().strip()
meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
existing_titles = {s['properties']['title'] for s in meta['sheets']}
if 'base_informativa' not in existing_titles:
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
        'requests': [{'addSheet': {'properties': {'title': 'base_informativa'}}}]
    }).execute()
    print('Tab base_informativa creada')

sheets.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range='base_informativa!A:E', body={}).execute()
sheets.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id, range='base_informativa!A1',
    valueInputOption='USER_ENTERED', body={'values': rows},
).execute()

meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
sid = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}['base_informativa']

fmt = [
    {'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1},
        'cell': {'userEnteredFormat': {'textFormat': {'bold': True}, 'backgroundColor': {'red': 0.85, 'green': 0.85, 'blue': 0.85}}},
        'fields': 'userEnteredFormat(textFormat,backgroundColor)',
    }},
    {'updateSheetProperties': {
        'properties': {'sheetId': sid, 'gridProperties': {'frozenRowCount': 1}},
        'fields': 'gridProperties.frozenRowCount',
    }},
    {'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 3, 'endColumnIndex': 5},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
]
sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': fmt}).execute()
print('Listo. URL: https://docs.google.com/spreadsheets/d/' + spreadsheet_id)
