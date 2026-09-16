"""
Sube balance_salida.json (generado por compute_balance_salida.py) a la
pestana "balance_salida" del Google Sheet.

Uso:
    python build_balance_salida_sheet.py
"""
import json

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file('google_token.json')
sheets = build('sheets', 'v4', credentials=creds)

registros = json.load(open('balance_salida.json', encoding='utf-8'))

HEADER = [
    'Fecha', 'Total Stock Valorizado', 'Total Stock Recibido',
    'Autónomos', 'Autónomos (fecha pago)', 'IIBB', 'IIBB (fecha pago)',
    'Percepciones y Retenciones', 'Percepciones (período)', 'Deudas Pendientes',
    'Balance de Salida',
]
rows = [HEADER]
for r in sorted(registros, key=lambda r: r['fecha'], reverse=True):
    rows.append([
        r['fecha'], r['total_stock_valorizado'], r['total_stock_recibido'],
        r['autonomos'], r['autonomos_fecha_pago'], r['iibb'], r['iibb_fecha_pago'],
        r['percepciones_retenciones'], r['percepciones_retenciones_periodo'], r['deudas_pendientes'],
        r['balance_salida'],
    ])

spreadsheet_id = open('sheet_id.txt').read().strip()
meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
existing_titles = {s['properties']['title'] for s in meta['sheets']}
if 'balance_salida' not in existing_titles:
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
        'requests': [{'addSheet': {'properties': {'title': 'balance_salida'}}}]
    }).execute()
    print('Tab balance_salida creada')

sheets.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range='balance_salida!A:K', body={}).execute()
sheets.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id, range='balance_salida!A1',
    valueInputOption='USER_ENTERED', body={'values': rows},
).execute()

meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
sid = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}['balance_salida']

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
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 1, 'endColumnIndex': 4},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
    {'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 5, 'endColumnIndex': 6},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
    {'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 7, 'endColumnIndex': 8},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
    {'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 9, 'endColumnIndex': 11},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
    {'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 10, 'endColumnIndex': 11},
        'cell': {'userEnteredFormat': {'textFormat': {'bold': True}}},
        'fields': 'userEnteredFormat.textFormat',
    }},
]
sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': fmt}).execute()
print('Listo. URL: https://docs.google.com/spreadsheets/d/' + spreadsheet_id)
