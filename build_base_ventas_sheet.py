"""
Sube base_ventas.json (generado por compute_base_ventas.py) a la pestaña
"base_ventas" del Google Sheet, agrupado por pack_id con una fila de TOTAL
por pack (suma de $, margen recalculado como Resultado Neto total / Importe
total -- no promedio de porcentajes).

Uso:
    python build_base_ventas_sheet.py
"""
import json
import os
from collections import defaultdict

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file('google_token.json')
sheets = build('sheets', 'v4', credentials=creds)

base = json.load(open('base_ventas.json', encoding='utf-8'))
CAT_NAMES = json.load(open('cat_names.json', encoding='utf-8'))

HEADER = [
    'Orden_id', 'Pack_id', 'Fecha', 'ITEM_ID', 'SKU', 'Título producto', 'Categoría', 'Cantidad', 'Tipo de envío',
    'Precio', 'Importe', 'Cargos variables (comisión)', 'Cargos fijos', 'Cargos por envíos',
    'Ingresos por envíos', 'Impuestos de la operación (percepción/retención)', 'Importe recibido',
    'Costo de mercadería vendida', 'Resultado Neto', 'Margen Neto',
    'Resultado Neto sin Flex', 'Margen Neto sin Flex',
    'Precio s/IVA', 'Importe s/IVA', 'Cargos variables (comisión) s/IVA', 'Cargos fijos s/IVA',
    'Cargos por envíos s/IVA', 'Ingresos por envíos s/IVA', 'Importe recibido s/IVA',
    'Costo de mercadería vendida s/IVA', 'Resultado Neto s/IVA', 'Margen Neto s/IVA',
    'Resultado Neto sin Flex s/IVA', 'Margen Neto sin Flex s/IVA',
]

N_MONEY_C = 12  # precio..costo (con IVA), columnas I..T antes de margen
N_MONEY_S = 12  # idem sin IVA


def row_of(r):
    return [
        f"'{r['order_id']}", f"'{r['pack_id']}", r['fecha'], r['item_id'], r['sku'], r['title'],
        CAT_NAMES.get(r.get('cat_id'), r.get('cat_id') or ''), r['qty'], r['tipo_envio'],
        r['precio_c'], r['importe_c'], r['cargo_var_c'], r['cargo_fij_c'], r['envio_cargo_c'],
        r['envio_ingreso_c'], r['impuestos'], r['importe_recibido_c'], r['costo_c'], r['resultado_neto_c'],
        r['margen_c'], r['resultado_neto_sinflex_c'], r['margen_sinflex_c'],
        r['precio_s'], r['importe_s'], r['cargo_var_s'], r['cargo_fij_s'], r['envio_cargo_s'],
        r['envio_ingreso_s'], r['importe_recibido_s'], r['costo_s'], r['resultado_neto_s'],
        r['margen_s'], r['resultado_neto_sinflex_s'], r['margen_sinflex_s'],
    ]


by_pack = defaultdict(list)
for r in base.values():
    by_pack[r['pack_id']].append(r)

rows = [HEADER]
for pack_id, ords in sorted(by_pack.items(), key=lambda x: x[1][0]['fecha'], reverse=True):
    ords = sorted(ords, key=lambda r: r['order_id'])
    for r in ords:
        rows.append(row_of(r))

spreadsheet_id = open('sheet_id.txt').read().strip()
meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
existing_titles = {s['properties']['title'] for s in meta['sheets']}
if 'base_ventas' not in existing_titles:
    sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
        'requests': [{'addSheet': {'properties': {'title': 'base_ventas'}}}]
    }).execute()
    print('Tab base_ventas creada')

sheets.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range='base_ventas!A:AG', body={}).execute()

sheets.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id, range='base_ventas!A1',
    valueInputOption='USER_ENTERED', body={'values': rows},
).execute()

meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
sid = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}['base_ventas']

fmt = [
    {'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1},
        'cell': {'userEnteredFormat': {'textFormat': {'bold': True}, 'backgroundColor': {'red': 0.85, 'green': 0.85, 'blue': 0.85}}},
        'fields': 'userEnteredFormat(textFormat,backgroundColor)',
    }},
    {'updateSheetProperties': {
        'properties': {'sheetId': sid, 'gridProperties': {'frozenRowCount': 1, 'frozenColumnCount': 9}},
        'fields': 'gridProperties(frozenRowCount,frozenColumnCount)',
    }},
    # moneda: dos bloques de 12 columnas (con IVA, luego sin IVA) arrancando despues de las columnas de identificacion
    {'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 9, 'endColumnIndex': 21},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
    {'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': 21, 'endColumnIndex': 33},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }},
    # margenes en % -> columnas S(18),U(20 es precio_s, ojo) -- recalculamos indices reales abajo
]

# columnas de margen (0-indexed): Margen Neto=18, Margen Neto sin Flex=20 -> pero U es col21 (Precio s/IVA)
# Recalculo con los indices reales del HEADER:
margin_cols = [HEADER.index('Margen Neto'), HEADER.index('Margen Neto sin Flex'),
               HEADER.index('Margen Neto s/IVA'), HEADER.index('Margen Neto sin Flex s/IVA')]
for col in margin_cols:
    fmt.append({'repeatCell': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': len(rows), 'startColumnIndex': col, 'endColumnIndex': col + 1},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'PERCENT', 'pattern': '0.00%'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }})

sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': fmt}).execute()
print('Listo. URL: https://docs.google.com/spreadsheets/d/' + spreadsheet_id)
