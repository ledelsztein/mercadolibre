"""
Sube base_ads.json (generado por compute_base_ads.py) a la pestana
"base_ads" del Google Sheet.

Uso:
    python build_base_ads_sheet.py
"""
import json

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file('google_token.json')
sheets = build('sheets', 'v4', credentials=creds)

registros = json.load(open('base_ads.json', encoding='utf-8'))

HEADER = ['Fecha', 'Factura', 'Costo s/IVA', 'Costo c/IVA', 'Ventas atr s/IVA', 'Ventas atr c/IVA', 'Impresiones', 'Clics']
rows = [HEADER]
for r in sorted(registros, key=lambda r: r['fecha'], reverse=True):
    rows.append([r['fecha'], r['factura'], r['costo_s'], r['costo_c'], r['ventas_s'], r['ventas_c'],
                 r['impresiones'], r['clicks']])

spreadsheet_id = open('sheet_id.txt').read().strip()
meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
existing_titles = {s['properties']['title'] for s in meta['sheets']}
if 'base_ads' not in existing_titles:
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
        'requests': [{'addSheet': {'properties': {'title': 'base_ads'}}}]
    }).execute()
    print('Tab base_ads creada')

sheets.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range='base_ads!A:H', body={}).execute()
sheets.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id, range='base_ads!A1',
    valueInputOption='USER_ENTERED', body={'values': rows},
).execute()

meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
sid = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}['base_ads']

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
