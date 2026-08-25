"""
Sube base_full.json (generado por compute_base_full.py) a la pestana
"base_full" del Google Sheet.

Uso:
    python build_base_full_sheet.py
"""
import json

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file('google_token.json')
sheets = build('sheets', 'v4', credentials=creds)

registros = json.load(open('base_full.json', encoding='utf-8'))

HEADER = ['Fecha', 'Factura', 'Envio a deposito Full (colecta) s/IVA', 'Envio a deposito Full (colecta) c/IVA', 'Almacenamiento Full s/IVA', 'Almacenamiento Full c/IVA']
rows = [HEADER]
for r in sorted(registros, key=lambda r: r['fecha'], reverse=True):
    rows.append([r['fecha'], r['factura'], r['deposito_full_s'], r['deposito_full_c'], r['almacenamiento_full_s'], r['almacenamiento_full_c']])

spreadsheet_id = open('sheet_id.txt').read().strip()
meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
existing_titles = {s['properties']['title'] for s in meta['sheets']}
if 'base_full' not in existing_titles:
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
        'requests': [{'addSheet': {'properties': {'title': 'base_full'}}}]
    }).execute()
    print('Tab base_full creada')

sheets.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range='base_full!A:F', body={}).execute()
sheets.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id, range='base_full!A1',
    valueInputOption='USER_ENTERED', body={'values': rows},
).execute()

meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
sid = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}['base_full']

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
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 2, 'endColumnIndex': 6},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
]
sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': fmt}).execute()
print('Listo. URL: https://docs.google.com/spreadsheets/d/' + spreadsheet_id)
