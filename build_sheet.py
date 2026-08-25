"""
Arma (o actualiza) el Google Sheet de P&L.

Uso:
    python build_sheet.py

Lee pnl_data.json (P&L por mes, generado por build_pnl_data.py) y
base_ventas.json + base_envios.json + cat_names.json para las tablas de
Rentabilidad por Producto / Categoria / Distribucion de envios -- las tres
pivotadas con los meses como columnas (no repitiendo filas por mes) para no
duplicar la misma info varias veces. Requiere google_token.json (de
auth_google.py).

Si existe sheet_id.txt, actualiza esa hoja en vez de crear una nueva -- borrar
ese archivo si se quiere crear una hoja nueva en vez de actualizar la actual.
"""
import json
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file('google_token.json')
sheets = build('sheets', 'v4', credentials=creds)

# ---------- P&L consolidado (uno o mas meses) ----------
PNL = json.load(open('pnl_data.json', encoding='utf-8'))

meses = list(PNL.keys())
pnl_rows = [
    ['Concepto'] + meses,
    ['INGRESOS'] + [''] * len(meses),
    ['Ventas'] + [PNL[m]['ventas'] for m in PNL],
    ['Ingresos por envio Flex (real)'] + [PNL[m]['envios_ingreso_flex'] for m in PNL],
    ['Envio pasante Full/Colecta (comprador financia, se cancela)'] + [PNL[m]['envio_pasante'] for m in PNL],
    ['Total Ingresos'] + [PNL[m]['ventas'] + PNL[m]['envios_ingreso'] for m in PNL],
    ['EGRESOS'] + [''] * len(meses),
    ['Costo de Mercaderia Vendida'] + [PNL[m]['cogs'] for m in PNL],
    ['Cargos por ventas'] + [PNL[m]['cargo_venta'] for m in PNL],
    ['Egresos por envio Full/Colecta (real)'] + [PNL[m]['egreso_envio_real'] for m in PNL],
    ['Envio pasante Full/Colecta (comprador financia, se cancela)'] + [PNL[m]['envio_pasante'] for m in PNL],
    ['Publicidad'] + [PNL[m]['publicidad'] for m in PNL],
    ['Cargo por colecta Full'] + [PNL[m]['cargo_colecta_full'] for m in PNL],
    ['Cargo por almacenamiento Full'] + [PNL[m]['cargo_almacenamiento_full'] for m in PNL],
    ['Adelanto de disponibilidad de dinero'] + [PNL[m]['adelanto'] for m in PNL],
    ['Logistica Flex (informativo)'] + [PNL[m]['logistica_flex'] for m in PNL],
    ['Otros cargos logisticos (informativo)'] + [PNL[m]['otros_log'] for m in PNL],
    ['Otros cargos (informativo)'] + [PNL[m]['otros_cargos'] for m in PNL],
    ['Gastos de Agencia (informativo)'] + [PNL[m]['gastos_agencia'] for m in PNL],
]
total_egresos = {m: PNL[m]['cogs'] + PNL[m]['cargo_venta'] + PNL[m]['egreso_envio'] + PNL[m]['publicidad']
                  + PNL[m]['logistica_flex'] + PNL[m]['otros_log'] + PNL[m]['otros_cargos'] + PNL[m]['gastos_agencia']
                  + PNL[m]['cargo_colecta_full'] + PNL[m]['cargo_almacenamiento_full'] + PNL[m]['adelanto'] for m in PNL}
total_ingresos = {m: PNL[m]['ventas'] + PNL[m]['envios_ingreso'] for m in PNL}
resultado_bruto = {m: total_ingresos[m] - total_egresos[m] for m in PNL}
margen_bruto = {m: resultado_bruto[m] / PNL[m]['ventas'] if PNL[m]['ventas'] else 0 for m in PNL}
total_impuestos = {m: PNL[m]['autonomos'] + (PNL[m]['percepciones'] or 0) + PNL[m]['iibb'] for m in PNL}
resultado_neto = {m: resultado_bruto[m] - total_impuestos[m] for m in PNL}
margen_neto = {m: (resultado_neto[m] / PNL[m]['ventas']) if PNL[m]['ventas'] else 0 for m in PNL}

pnl_rows += [
    ['Total Egresos'] + [total_egresos[m] for m in PNL],
    ['RESULTADO BRUTO'] + [resultado_bruto[m] for m in PNL],
    ['MARGEN BRUTO %'] + [margen_bruto[m] for m in PNL],
    ['IMPUESTOS'] + [''] * len(meses),
    ['Autonomos (informativo)'] + [PNL[m]['autonomos'] for m in PNL],
    ['Percepciones y Retenciones'] + [PNL[m]['percepciones'] if PNL[m]['percepciones'] is not None else 'pendiente' for m in PNL],
    ['Pago de Ingresos Brutos (informativo)'] + [PNL[m]['iibb'] for m in PNL],
    ['Total Impuestos'] + [total_impuestos[m] for m in PNL],
    ['RESULTADO NETO'] + [resultado_neto[m] for m in PNL],
    ['MARGEN NETO %'] + [margen_neto[m] for m in PNL],
]

# Punto de equilibrio: clasificacion fijo/variable pedida por Lucas. Autonomos
# pasa a Costo Fijo aca (aunque en el bloque de arriba vive en Impuestos);
# IIBB y Percepciones quedan afuera del calculo por ser impuestos, no costos.
# cargo_colecta_full/cargo_almacenamiento_full/adelanto (2026-07-31)
# tambien son Costo Variable, per Lucas.
costos_variables = {m: PNL[m]['cogs'] + PNL[m]['cargo_venta'] + PNL[m]['egreso_envio']
                     + PNL[m]['logistica_flex'] + PNL[m]['otros_log']
                     + PNL[m]['cargo_colecta_full'] + PNL[m]['cargo_almacenamiento_full'] + PNL[m]['adelanto'] for m in PNL}
costos_fijos = {m: PNL[m]['publicidad'] + PNL[m]['otros_cargos'] + PNL[m]['gastos_agencia'] + PNL[m]['autonomos'] for m in PNL}
margen_contribucion = {m: total_ingresos[m] - costos_variables[m] for m in PNL}
margen_contribucion_pct = {m: margen_contribucion[m] / PNL[m]['ventas'] if PNL[m]['ventas'] else 0 for m in PNL}
punto_equilibrio = {m: (costos_fijos[m] / margen_contribucion_pct[m]) if margen_contribucion_pct[m] > 0 else None for m in PNL}
pct_punto_equilibrio = {m: (PNL[m]['ventas'] / punto_equilibrio[m]) if punto_equilibrio[m] else None for m in PNL}

pnl_rows += [
    ['PUNTO DE EQUILIBRIO'] + [''] * len(meses),
    ['Costos Variables'] + [costos_variables[m] for m in PNL],
    ['Costos Fijos (incl. Autonomos)'] + [costos_fijos[m] for m in PNL],
    ['Margen de Contribucion'] + [margen_contribucion[m] for m in PNL],
    ['Margen de Contribucion %'] + [margen_contribucion_pct[m] for m in PNL],
    ['Punto de Equilibrio ($ ventas)'] + [punto_equilibrio[m] if punto_equilibrio[m] is not None else 'sin margen positivo' for m in PNL],
    ['% Ventas / Punto de Equilibrio'] + [pct_punto_equilibrio[m] if pct_punto_equilibrio[m] is not None else '' for m in PNL],
]

# ---------- base_ventas + base_envios: fuente unica, pivotada por mes (sin repetir filas) ----------
CAT_NAMES = json.load(open('cat_names.json', encoding='utf-8'))
PERIODOS = [
    ('mayo', '2026-05-01', '2026-05-31'),
    ('junio', '2026-06-01', '2026-06-30'),
    ('julio', '2026-07-01', '2026-07-31'),
    ('agosto', '2026-08-01', '2026-08-23'),
]
mes_label = {m.lower().split(' ')[0]: m for m in meses}

base_ventas_all = list(json.load(open('base_ventas.json', encoding='utf-8')).values())
base_envios_all = list(json.load(open('base_envios.json', encoding='utf-8')).values())
envio_neto_by_order = {r['order_id']: r['costo_c'] - r['ingreso_c'] for r in base_envios_all}

prod_data = {}   # item_id -> {sku, title, cat, meses: {periodo: {venta,costo,margen}}}
cat_data = {}    # cat_name -> {meses: {periodo: {venta,costo,margen}}}
tipo_data = {}   # tipo -> {meses: {periodo: venta}}
venta_total_mes = {}  # periodo -> venta total del mes (denominador del % de envios)

periodos_presentes = [p for p, _, _ in PERIODOS if p in mes_label]

for periodo, desde, hasta in PERIODOS:
    if periodo not in mes_label:
        continue
    registros = [r for r in base_ventas_all if desde <= r['fecha'] <= hasta]
    if not registros:
        continue
    by_item = {}
    by_tipo = {}
    for r in registros:
        venta = r['importe_c']; costo = -r['costo_c']; cargo = -(r['cargo_var_c'] + r['cargo_fij_c'])
        envio = envio_neto_by_order.get(r['order_id'], 0.0)
        item = by_item.setdefault(r['item_id'], {'sku': r['sku'], 'title': r['title'], 'cat_id': r.get('cat_id'), 'venta': 0.0, 'costo': 0.0, 'cargo': 0.0, 'envio': 0.0})
        item['venta'] += venta; item['costo'] += costo; item['cargo'] += cargo; item['envio'] += envio
        t = by_tipo.setdefault(r['tipo_envio'], {'venta': 0.0})
        t['venta'] += venta

    venta_total_mes[periodo] = sum(t['venta'] for t in by_tipo.values())
    for tipo, t in by_tipo.items():
        tipo_data.setdefault(tipo, {})[periodo] = t['venta']

    for item_id, d in by_item.items():
        resultado_neto = d['venta'] - d['cargo'] - d['envio'] - d['costo']
        cat_name = CAT_NAMES.get(d['cat_id'], d['cat_id'])
        pd = prod_data.setdefault(item_id, {'sku': d['sku'], 'title': d['title'], 'cat': cat_name, 'meses': {}})
        pd['meses'][periodo] = {'venta': d['venta'], 'costo': d['costo'], 'margen': resultado_neto}

        cm = cat_data.setdefault(cat_name, {'meses': {}})['meses'].setdefault(periodo, {'venta': 0.0, 'costo': 0.0, 'margen': 0.0})
        cm['venta'] += d['venta']; cm['costo'] += d['costo']; cm['margen'] += resultado_neto


def total_margen(meses_dict):
    return sum(v['margen'] for v in meses_dict.values())


def build_pivot_rows(entries, id_cols_fn, sort_key):
    """entries: iterable de (row_id, datos con .meses). id_cols_fn(row_id, datos) -> lista de columnas fijas.
    Devuelve filas con, por cada periodo presente + Total: Ventas, Costo, Resultado Neto, Margen %."""
    rows = []
    for row_id, datos in sorted(entries, key=sort_key, reverse=True):
        row = id_cols_fn(row_id, datos)
        tot_venta = tot_costo = tot_margen = 0.0
        for p in periodos_presentes:
            md = datos['meses'].get(p, {'venta': 0.0, 'costo': 0.0, 'margen': 0.0})
            venta, costo, margen = md['venta'], md['costo'], md['margen']
            pct = margen / venta if venta else 0
            row += [venta, costo, margen, pct]
            tot_venta += venta; tot_costo += costo; tot_margen += margen
        tot_pct = tot_margen / tot_venta if tot_venta else 0
        row += [tot_venta, tot_costo, tot_margen, tot_pct]
        rows.append(row)
    return rows


mes_headers = [mes_label[p] for p in periodos_presentes] + ['Total']
metric_headers = ['Ventas', 'Costo', 'Resultado Neto', 'Margen %']

prod_header_1 = ['', '', '', ''] + [h for m in mes_headers for h in [m, '', '', '']]
prod_header_2 = ['SKU', 'Item ID', 'Producto', 'Categoria'] + metric_headers * len(mes_headers)
prod_rows = [prod_header_1, prod_header_2] + build_pivot_rows(
    prod_data.items(),
    lambda item_id, d: [d['sku'], item_id, d['title'], d['cat']],
    sort_key=lambda x: total_margen(x[1]['meses']),
)

cat_header_1 = [''] + [h for m in mes_headers for h in [m, '', '', '']]
cat_header_2 = ['Categoria'] + metric_headers * len(mes_headers)
cat_rows = [cat_header_1, cat_header_2] + build_pivot_rows(
    cat_data.items(),
    lambda cat_name, d: [cat_name],
    sort_key=lambda x: total_margen(x[1]['meses']),
)

ship_header_1 = [''] + [h for m in mes_headers for h in [m, '']]
ship_header_2 = ['Tipo de envio'] + ['Ventas $', 'Ventas %'] * len(mes_headers)
ship_rows = [ship_header_1, ship_header_2]
tot_all_meses = sum(venta_total_mes.get(p, 0) for p in periodos_presentes)
for tipo, td in sorted(tipo_data.items(), key=lambda x: -sum(x[1].values())):
    row = [tipo]
    tot_venta = 0.0
    for p in periodos_presentes:
        venta = td.get(p, 0.0)
        pct = venta / venta_total_mes[p] if venta_total_mes.get(p) else 0
        row += [venta, pct]
        tot_venta += venta
    tot_pct = tot_venta / tot_all_meses if tot_all_meses else 0
    row += [tot_venta, tot_pct]
    ship_rows.append(row)

# ---------- crear (tabs que falten) o actualizar spreadsheet ----------
TABS = ['P&L', 'Rentabilidad por Producto', 'Por Categoria', 'Envios por Tipo']
if os.path.exists('sheet_id.txt'):
    spreadsheet_id = open('sheet_id.txt').read().strip()
    print('Actualizando sheet existente:', spreadsheet_id)
    meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_titles = {s['properties']['title'] for s in meta['sheets']}
    faltantes = [t for t in TABS if t not in existing_titles]
    if faltantes:
        sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={
            'requests': [{'addSheet': {'properties': {'title': t}}} for t in faltantes]
        }).execute()
        print('Tabs agregadas:', faltantes)
else:
    body = {
        'properties': {'title': 'Deleite - P&L Mayo-Julio 2026'},
        'sheets': [{'properties': {'title': t}} for t in TABS],
    }
    spreadsheet = sheets.spreadsheets().create(body=body).execute()
    spreadsheet_id = spreadsheet['spreadsheetId']
    open('sheet_id.txt', 'w').write(spreadsheet_id)
    print('Sheet creado:', spreadsheet['spreadsheetUrl'])

# limpiar las 3 tabs pivotadas antes de escribir -- el ancho/alto cambia con
# la cantidad de productos/categorias, y values().update() no achica la hoja
for t in ['Rentabilidad por Producto', 'Por Categoria', 'Envios por Tipo']:
    sheets.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=f"'{t}'!A:ZZ", body={}).execute()

data = [
    {'range': 'P&L!A1', 'values': pnl_rows},
    {'range': 'Rentabilidad por Producto!A1', 'values': prod_rows},
    {'range': 'Por Categoria!A1', 'values': cat_rows},
    {'range': 'Envios por Tipo!A1', 'values': ship_rows},
]
sheets.spreadsheets().values().batchUpdate(
    spreadsheetId=spreadsheet_id,
    body={'valueInputOption': 'USER_ENTERED', 'data': data},
).execute()

meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
sheet_id_by_title = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}

fmt_requests = []
for title in TABS:
    sid = sheet_id_by_title[title]
    header_rows = 2 if title != 'P&L' else 1
    fmt_requests.append({
        'repeatCell': {
            'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': header_rows},
            'cell': {'userEnteredFormat': {'textFormat': {'bold': True}, 'backgroundColor': {'red': 0.85, 'green': 0.85, 'blue': 0.85}}},
            'fields': 'userEnteredFormat(textFormat,backgroundColor)',
        }
    })
    fmt_requests.append({
        'updateSheetProperties': {
            'properties': {'sheetId': sid, 'gridProperties': {'frozenRowCount': header_rows}},
            'fields': 'gridProperties.frozenRowCount',
        }
    })

# moneda para columnas B:D de P&L (filas de montos)
fmt_requests.append({
    'repeatCell': {
        'range': {'sheetId': sheet_id_by_title['P&L'], 'startRowIndex': 1, 'endRowIndex': len(pnl_rows), 'startColumnIndex': 1, 'endColumnIndex': 4},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }
})
for i, row in enumerate(pnl_rows):
    if '%' in row[0]:
        fmt_requests.append({
            'repeatCell': {
                'range': {'sheetId': sheet_id_by_title['P&L'], 'startRowIndex': i, 'endRowIndex': i + 1, 'startColumnIndex': 1, 'endColumnIndex': 4},
                'cell': {'userEnteredFormat': {'numberFormat': {'type': 'PERCENT', 'pattern': '0.00%'}}},
                'fields': 'userEnteredFormat.numberFormat',
            }
        })


def merge_and_format_month_headers(title, n_id_cols, cols_per_month, n_months_plus_total):
    """Fusiona las celdas de la fila 1 (nombre del mes) cada cols_per_month
    columnas, y aplica moneda/porcentaje a las columnas de datos (filas 3+)."""
    sid = sheet_id_by_title[title]
    reqs = []
    for i in range(n_months_plus_total):
        start = n_id_cols + i * cols_per_month
        reqs.append({'mergeCells': {
            'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': start, 'endColumnIndex': start + cols_per_month},
            'mergeType': 'MERGE_ALL',
        }})
        reqs.append({'repeatCell': {
            'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': start, 'endColumnIndex': start + cols_per_month},
            'cell': {'userEnteredFormat': {'horizontalAlignment': 'CENTER'}},
            'fields': 'userEnteredFormat.horizontalAlignment',
        }})
    return reqs


n_months_total = len(mes_headers)

# Rentabilidad por Producto: 4 columnas fijas (SKU, Item ID, Producto, Categoria), 4 metricas x mes
fmt_requests += merge_and_format_month_headers('Rentabilidad por Producto', 4, 4, n_months_total)
for i in range(n_months_total):
    start = 4 + i * 4
    fmt_requests.append({'repeatCell': {
        'range': {'sheetId': sheet_id_by_title['Rentabilidad por Producto'], 'startRowIndex': 2, 'endRowIndex': len(prod_rows), 'startColumnIndex': start, 'endColumnIndex': start + 3},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }})
    fmt_requests.append({'repeatCell': {
        'range': {'sheetId': sheet_id_by_title['Rentabilidad por Producto'], 'startRowIndex': 2, 'endRowIndex': len(prod_rows), 'startColumnIndex': start + 3, 'endColumnIndex': start + 4},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'PERCENT', 'pattern': '0.00%'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }})

# Por Categoria: 1 columna fija (Categoria), 4 metricas x mes
fmt_requests += merge_and_format_month_headers('Por Categoria', 1, 4, n_months_total)
for i in range(n_months_total):
    start = 1 + i * 4
    fmt_requests.append({'repeatCell': {
        'range': {'sheetId': sheet_id_by_title['Por Categoria'], 'startRowIndex': 2, 'endRowIndex': len(cat_rows), 'startColumnIndex': start, 'endColumnIndex': start + 3},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }})
    fmt_requests.append({'repeatCell': {
        'range': {'sheetId': sheet_id_by_title['Por Categoria'], 'startRowIndex': 2, 'endRowIndex': len(cat_rows), 'startColumnIndex': start + 3, 'endColumnIndex': start + 4},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'PERCENT', 'pattern': '0.00%'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }})

# Envios por Tipo: 1 columna fija (Tipo de envio), 2 metricas x mes (Ventas $, Ventas %)
fmt_requests += merge_and_format_month_headers('Envios por Tipo', 1, 2, n_months_total)
for i in range(n_months_total):
    start = 1 + i * 2
    fmt_requests.append({'repeatCell': {
        'range': {'sheetId': sheet_id_by_title['Envios por Tipo'], 'startRowIndex': 2, 'endRowIndex': len(ship_rows), 'startColumnIndex': start, 'endColumnIndex': start + 1},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }})
    fmt_requests.append({'repeatCell': {
        'range': {'sheetId': sheet_id_by_title['Envios por Tipo'], 'startRowIndex': 2, 'endRowIndex': len(ship_rows), 'startColumnIndex': start + 1, 'endColumnIndex': start + 2},
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'PERCENT', 'pattern': '0.00%'}}},
        'fields': 'userEnteredFormat.numberFormat',
    }})

sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': fmt_requests}).execute()

print('Listo. URL: https://docs.google.com/spreadsheets/d/' + spreadsheet_id)
