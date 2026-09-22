"""
Chequea que toda publicacion activa (la foto mas reciente de
stock_valorizado.json) tenga un costo cargado en data/Costos.xlsx -- si no lo
tiene (o el costo cargado es 0), compute_base_ventas.py calcula esa venta con
costo $0 y el margen queda inflado sin que nadie lo note.

Pensada para correr como parte de /actualizar-tablero, despues de
compute_stock_valorizado.py (usa su foto del dia, no vuelve a pegarle a la
API de MercadoLibre).

Uso:
    python check_productos_sin_costo.py
"""
import json

import openpyxl

COSTS_FILE = 'data/Costos.xlsx'
wb = openpyxl.load_workbook(COSTS_FILE, data_only=True)
ws = wb.active
item_ids_con_costo = set()
for row in ws.iter_rows(min_row=2, values_only=True):
    if row[0] is None:
        continue
    _, item_id, _, costo, _ = row
    if costo:
        item_ids_con_costo.add(item_id)

stock = json.load(open('stock_valorizado.json', encoding='utf-8'))
if not stock:
    print('stock_valorizado.json vacio -- correr compute_stock_valorizado.py primero')
    raise SystemExit(1)
fecha_mas_reciente = max(r['fecha'] for r in stock)
activos = [r for r in stock if r['fecha'] == fecha_mas_reciente]

faltantes = [r for r in activos if r['item_id'] not in item_ids_con_costo]

if not faltantes:
    print(f'{fecha_mas_reciente}: todas las {len(activos)} publicaciones activas tienen costo cargado.')
else:
    print(f'{fecha_mas_reciente}: {len(faltantes)}/{len(activos)} publicaciones activas SIN costo cargado en data/Costos.xlsx:')
    for r in sorted(faltantes, key=lambda r: -r['importe']):
        print(f"  SKU {r['sku'] or '(sin SKU)'} -- {r['item_id']} -- {r['producto']} -- stock {r['stock']} x ${r['precio']:,.2f} = ${r['importe']:,.2f}")
