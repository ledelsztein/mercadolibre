"""
Sube base_cargos_ml.json (generado por compute_base_cargos_ml.py) a la pestana
"base_cargos_ml" del Google Sheet.

Uso:
    python build_base_cargos_ml_sheet.py
"""
import json

from google_creds import get_creds
from googleapiclient.discovery import build

creds = get_creds()
sheets = build('sheets', 'v4', credentials=creds)

registros = json.load(open('base_cargos_ml.json', encoding='utf-8'))

HEADER = ['Fecha', 'Factura', 'Mantenimiento Mi pagina s/IVA', 'Mantenimiento Mi pagina c/IVA', 'Devoluciones s/IVA', 'Devoluciones c/IVA']
rows = [HEADER]
for r in sorted(registros, key=lambda r: r['fecha'], reverse=True):
    rows.append([r['fecha'], r['factura'], r['mi_pagina_s'], r['mi_pagina_c'], r['devoluciones_s'], r['devoluciones_c']])

spreadsheet_id = open('sheet_id.txt').read().strip()
meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
existing_titles = {s['properties']['title'] for s in meta['sheets']}
if 'base_cargos_ml' not in existing_titles:
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
        'requests': [{'addSheet': {'properties': {'title': 'base_cargos_ml'}}}]
    }).execute()
    print('Tab base_cargos_ml creada')

sheets.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range='base_cargos_ml!A:F', body={}).execute()
sheets.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id, range='base_cargos_ml!A1',
    valueInputOption='USER_ENTERED', body={'values': rows},
).execute()

meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
sid = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}['base_cargos_ml']

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
