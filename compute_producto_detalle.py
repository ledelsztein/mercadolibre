"""
Calcula ventas, costo (con logica de reposicion) y margen por producto,
para cada mes que tenga un archivo ordenes_<mes>.json. El archivo cuyo rango
de fechas incluye HOY se separa en dos grupos de salida: el mes en curso con
solo dias cerrados (< hoy), y un grupo "hoy" aparte (== hoy) -- asi el P&L
mensual siempre queda a dia cerrado y "hoy" se puede mostrar por separado.

Uso:
    python compute_producto_detalle.py

Requiere:
- ordenes_<mes>.json por cada mes (generado por fetch_orders.py)
- un archivo de costos "Costos (*).xlsx" con columnas SKU, Item ID,
  Producto, Costo s/IVA, Fecha (la fecha desde la que ese costo esta vigente)

Escribe producto_detalle.json: {mes: {item_id: {title, sku, cat_id, qty, ventas, costo}}}
"""
import glob
import json
import os
import sys
from datetime import date

import openpyxl

# "Hoy" se puede pasar como argumento (python compute_producto_detalle.py 2026-07-21)
# para no depender del reloj del sistema, que puede haberse corrido de dia
# durante una sesion larga.
HOY = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

# El archivo de costos mas nuevo por fecha de modificacion (no alfabetico:
# "Costos (2).xlsx" ordena antes que "Costos.xlsx" por el espacio). Debe
# tener columnas SKU, Item ID, Producto, Costo s/IVA, Fecha.
candidatos = glob.glob(os.path.expanduser(r'~\Downloads\Costos*.xlsx'))
COSTS_FILE = max(candidatos, key=os.path.getmtime)
print('Usando archivo de costos (mas reciente):', COSTS_FILE)

wb = openpyxl.load_workbook(COSTS_FILE, data_only=True)
ws = wb.active

costs_by_item = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    if row[0] is None:
        continue
    sku, item_id, producto, costo, fecha = row
    d = fecha.date() if hasattr(fecha, 'date') else fecha
    costs_by_item.setdefault(item_id, []).append((d, costo, producto))
for item_id in costs_by_item:
    costs_by_item[item_id].sort(key=lambda x: x[0])

# Item IDs a excluir del calculo de costos/margen (ventas puntuales fuera del
# catalogo habitual). Agregar aca si aparecen mas casos como el Timberland.
EXCLUIR_ITEM_IDS = {'MLA1612895659'}


def costo_vigente(item_id, fecha_venta):
    """Costo de reposicion: el mas reciente con fecha <= fecha_venta;
    si no hay ninguno anterior/igual, el primero posterior disponible."""
    entries = costs_by_item.get(item_id)
    if not entries:
        return None
    candidato = None
    for d, costo, _ in entries:
        if d <= fecha_venta:
            candidato = (d, costo)
        else:
            if candidato is None:
                return costo
            break
    return candidato[1] if candidato else entries[0][1]


def acumular(orders, item_id_filter=None):
    by_prod = {}
    sin_costo = set()
    for o in orders:
        fecha_venta = date.fromisoformat(o['date_created'][:10])
        for item in o.get('order_items', []):
            item_id = item['item']['id']
            if item_id in EXCLUIR_ITEM_IDS:
                continue
            title = item['item']['title']
            sku = item['item'].get('seller_sku') or ''
            cat_id = item['item']['category_id']
            qty = item['quantity']
            venta = item['unit_price'] * qty
            costo_unit = costo_vigente(item_id, fecha_venta)
            if costo_unit is None:
                sin_costo.add((item_id, title))
            costo_total = (costo_unit or 0) * qty
            d = by_prod.setdefault(item_id, {'title': title, 'sku': sku, 'cat_id': cat_id, 'qty': 0, 'ventas': 0.0, 'costo': 0.0})
            d['qty'] += qty
            d['ventas'] += venta
            d['costo'] += costo_total
    return by_prod, sin_costo


resultado = {}
for path in sorted(glob.glob('ordenes_*.json')):
    mes = path.replace('ordenes_', '').replace('.json', '')
    orders = json.load(open(path, encoding='utf-8'))

    tiene_hoy = any(o['date_created'][:10] == HOY for o in orders)
    if tiene_hoy:
        cerrados = [o for o in orders if o['date_created'][:10] < HOY]
        de_hoy = [o for o in orders if o['date_created'][:10] == HOY]
        by_prod, sin_costo = acumular(cerrados)
        resultado[mes] = by_prod
        print(f'{mes} (cerrado, < {HOY}): {len(by_prod)} productos', f'| SIN COSTO: {sin_costo}' if sin_costo else '')
        by_prod_hoy, sin_costo_hoy = acumular(de_hoy)
        resultado['hoy'] = by_prod_hoy
        print(f'hoy ({HOY}): {len(by_prod_hoy)} productos', f'| SIN COSTO: {sin_costo_hoy}' if sin_costo_hoy else '')
    else:
        by_prod, sin_costo = acumular(orders)
        resultado[mes] = by_prod
        print(f'{mes}: {len(by_prod)} productos', f'| SIN COSTO: {sin_costo}' if sin_costo else '')

with open('producto_detalle.json', 'w', encoding='utf-8') as f:
    json.dump(resultado, f, ensure_ascii=False, indent=2)
print('Guardado producto_detalle.json')
