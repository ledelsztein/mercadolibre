"""
Sube base_envios.json (generado por compute_base_envios.py) a la pestaña
"base_envios" del Google Sheet.

Uso:
    python build_base_envios_sheet.py
"""
import json

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file('google_token.json')
sheets = build('sheets', 'v4', credentials=creds)

base = json.load(open('base_envios.json', encoding='utf-8'))

HEADER = ['Order_id', 'Pack_id', 'Fecha', 'Shipment_id', 'Tipo de envío',
          'Ingreso por envío', 'Ingreso por envío s/IVA', 'Costo por envío', 'Costo por envío s/IVA']

rows = [HEADER]
for r in sorted(base.values(), key=lambda r: r['fecha'], reverse=True):
    rows.append([
        f"'{r['order_id']}", f"'{r['pack_id']}", r['fecha'], f"'{r['shipment_id']}", r['tipo_envio'],
        r['ingreso_c'], r['ingreso_s'], r['costo_c'], r['costo_s'],
    ])

spreadsheet_id = open('sheet_id.txt').read().strip()
meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
existing_titles = {s['properties']['title'] for s in meta['sheets']}
if 'base_envios' not in existing_titles:
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
        'requests': [{'addSheet': {'properties': {'title': 'base_envios'}}}]
    }).execute()
    print('Tab base_envios creada')

sheets.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range='base_envios!A:I', body={}).execute()
sheets.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id, range='base_envios!A1',
    valueInputOption='USER_ENTERED', body={'values': rows},
).execute()

meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
sid = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}['base_envios']

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
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 5, 'endColumnIndex': 9},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
]
sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': fmt}).execute()
print('Listo. URL: https://docs.google.com/spreadsheets/d/' + spreadsheet_id)
