"""
Sube stock_valorizado.json (generado por compute_stock_valorizado.py) a la
pestana "stock_valorizado" del Google Sheet.

Uso:
    python build_stock_valorizado_sheet.py
"""
import json

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file('google_token.json')
sheets = build('sheets', 'v4', credentials=creds)

registros = json.load(open('stock_valorizado.json', encoding='utf-8'))

HEADER = ['Fecha', 'SKU', 'Item ID', 'Producto', 'Stock', 'Precio', 'Importe']
rows = [HEADER]
for r in sorted(registros, key=lambda r: (r['fecha'], -r['importe']), reverse=True):
    rows.append([r['fecha'], r['sku'], r['item_id'], r['producto'], r['stock'], r['precio'], r['importe']])

spreadsheet_id = open('sheet_id.txt').read().strip()
meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
existing_titles = {s['properties']['title'] for s in meta['sheets']}
if 'stock_valorizado' not in existing_titles:
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
        'requests': [{'addSheet': {'properties': {'title': 'stock_valorizado'}}}]
    }).execute()
    print('Tab stock_valorizado creada')

sheets.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range='stock_valorizado!A:G', body={}).execute()
sheets.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id, range='stock_valorizado!A1',
    valueInputOption='USER_ENTERED', body={'values': rows},
).execute()

meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
sid = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}['stock_valorizado']

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
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 5, 'endColumnIndex': 7},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
]
sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': fmt}).execute()
print('Listo. URL: https://docs.google.com/spreadsheets/d/' + spreadsheet_id)
