"""
Calcula, por cada ORDEN (que en los datos reales de Lucas siempre es 1
producto, ver nota abajo), todos los componentes del Resultado Neto:

    Resultado Neto = Venta - Cargo por venta + Descuentos - Envio - Costo

- Venta, Costo: igual que compute_producto_detalle.py (costo con logica de
  reposicion).
- Cargo por venta, Descuentos: vienen DIRECTO de la Facturacion (Billing
  API, marketplace CORE) por order_id -- no hace falta prorratear porque
  cada orden en estos datos tiene un solo producto.
- Envio: neto (egreso real - ingreso Flex) del SHIPMENT de esa orden,
  prorrateado por venta cuando el shipment es compartido por varias ordenes
  de un mismo pack.
- logistic_type del shipment, para poder agrupar por tipo de envio.

Uso:
    python compute_venta_detalle.py <archivo_ordenes> <fecha_desde> <fecha_hasta>
    python compute_venta_detalle.py julio 2026-07-01 2026-07-20

Escribe venta_detalle_<archivo_ordenes>_<fecha_desde>_<fecha_hasta>.json con
una lista de registros, uno por orden:
    {order_id, item_id, title, sku, cat_id, qty, logistic_type,
     venta, costo, cargo, descuento, envio}

NOTA: si en el futuro aparece una orden con mas de un producto distinto,
este script no la prorratea (asume 1 orden = 1 item, como es en todos los
casos vistos hasta ahora) -- revisar si eso cambia.
"""
import glob
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date

import openpyxl
import requests
from dotenv import load_dotenv

load_dotenv()


def get_token():
    token_data = json.load(open('token.json'))
    headers = {'Authorization': f'Bearer {token_data["access_token"]}'}
    r = requests.get('https://api.mercadolibre.com/users/me', headers=headers)
    if r.status_code == 401:
        r = requests.post('https://api.mercadolibre.com/oauth/token', data={
            'grant_type': 'refresh_token',
            'client_id': os.environ['ML_CLIENT_ID'],
            'client_secret': os.environ['ML_CLIENT_SECRET'],
            'refresh_token': token_data['refresh_token'],
        })
        r.raise_for_status()
        token_data = r.json()
        json.dump(token_data, open('token.json', 'w'), indent=2)
    return token_data['access_token']


TOKEN = get_token()
HEADERS = {'Authorization': f'Bearer {TOKEN}'}


def get_shipment(sid):
    for _ in range(5):
        r = requests.get(f'https://api.mercadolibre.com/shipments/{sid}', headers=HEADERS)
        if r.status_code == 429:
            time.sleep(5)
            continue
        return r.json()
    raise RuntimeError('too many retries')


def get_shipment_costs(sid):
    for _ in range(5):
        r = requests.get(f'https://api.mercadolibre.com/shipments/{sid}/costs', headers=HEADERS)
        if r.status_code == 429:
            time.sleep(5)
            continue
        return r.json()
    raise RuntimeError('too many retries')


def get_payment(payment_id):
    for _ in range(5):
        r = requests.get(f'https://api.mercadopago.com/v1/payments/{payment_id}', headers=HEADERS)
        if r.status_code == 429:
            time.sleep(5)
            continue
        return r.json()
    raise RuntimeError('too many retries')


def billing_period_for_date(d):
    dd = date.fromisoformat(d)
    if dd.day >= 7:
        y, m = dd.year, dd.month + 1
    else:
        y, m = dd.year, dd.month
    if m > 12:
        y, m = y + 1, m - 12
    return f'{y}-{m:02d}-01'


def fetch_billing_for_order(period_key, order_id):
    """Trae los cargos CORE de UNA sola orden. El parametro order_ids de esta
    API esta roto para mas de un id (con 2+ ids siempre da total:0 aunque
    los datos existan). Incluso con 1 solo id, ocasionalmente devuelve 0
    resultados de forma transitoria para una orden que si tiene datos --
    por eso reintentamos tambien cuando la respuesta viene vacia, no solo
    cuando falla el request."""
    last_empty = None
    for attempt in range(6):
        r = requests.get(f'https://api.mercadolibre.com/billing/integration/periods/key/{period_key}/group/ML/details',
            headers=HEADERS, params={'document_type': 'BILL', 'order_ids': order_id})
        if r.status_code != 200:
            time.sleep(5)
            continue
        results = r.json().get('results', [])
        if results:
            return results
        last_empty = results
        time.sleep(1.5)
    return last_empty or []


# ---------- costos (misma logica que compute_producto_detalle.py) ----------
candidatos = glob.glob(os.path.expanduser(r'~\Downloads\Costos*.xlsx'))
COSTS_FILE = max(candidatos, key=os.path.getmtime)
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

EXCLUIR_ITEM_IDS = {'MLA1612895659'}


IVA = 1.21  # los costos en Costos.xlsx vienen sin IVA; venta (total_amount) es con IVA


def costo_vigente(item_id, fecha_venta):
    entries = costs_by_item.get(item_id)
    if not entries:
        return None
    candidato = None
    for d, costo, _ in entries:
        if d <= fecha_venta:
            candidato = (d, costo)
        else:
            if candidato is None:
                return costo * IVA
            break
    costo_sin_iva = candidato[1] if candidato else entries[0][1]
    return costo_sin_iva * IVA


def compute(orders, neto=False):
    if any(len(o.get('order_items', [])) > 1 for o in orders):
        print('ADVERTENCIA: hay una orden con mas de 1 producto distinto -- '
              'este script no la prorratea, revisar a mano.')

    cargo_by_order = defaultdict(float)
    descuento_by_order = defaultdict(float)

    if neto:
        # Periodo de facturacion todavia ABIERTO: la Billing API no tiene
        # todavia el registro CORE de muchas ordenes recientes (se genera de
        # forma asincronica), asi que el desglose bruto/descuento no es
        # confiable (crece entre corridas incluso con reintentos -- ver
        # mercadolibre-pnl-pipeline en memoria). En su lugar usamos el cargo
        # NETO ya cobrado por MercadoPago (charges_details type=="fee"), que
        # es estable y viene por orden (no prorateado). descuento queda en 0
        # porque ya esta neteado dentro de ese monto.
        print('  modo --neto: cargo por orden desde MercadoPago (charges_details fee)')
        for i, o in enumerate(orders):
            oid = str(o['id'])
            p = get_payment(o['payments'][0]['id'])
            for c in p.get('charges_details', []):
                if c.get('type') == 'fee':
                    cargo_by_order[oid] += c['amounts']['original']
            if (i + 1) % 20 == 0:
                time.sleep(1)
    else:
        # ---- cargo y descuento por order_id (Facturacion, orden por orden) ----
        for i, o in enumerate(orders):
            oid = str(o['id'])
            pk = billing_period_for_date(o['date_created'][:10])
            entries = fetch_billing_for_order(pk, oid)
            for e in entries:
                if e['marketplace_info']['marketplace'] != 'CORE':
                    continue
                disc = e['discount_info']['discount_amount'] or 0.0
                gross = e['discount_info']['charge_amount_without_discount']
                if gross is None:
                    gross = e['charge_info']['detail_amount'] + disc
                # detail_amount ya es el cargo NETO cobrado; para "cargo por venta"
                # como concepto de egreso usamos el neto (lo que realmente se cobro)
                cargo_by_order[oid] += e['charge_info']['detail_amount']
                descuento_by_order[oid] += disc
            if (i + 1) % 20 == 0:
                time.sleep(1)
                print(f'  facturacion: {i + 1}/{len(orders)} ordenes consultadas')

    # ---- envio neto por shipment, prorrateado por venta entre sus ordenes ----
    shipment_orders = defaultdict(list)
    for o in orders:
        sid = o.get('shipping', {}).get('id')
        if sid:
            shipment_orders[sid].append(o)

    shipment_type = {}
    shipment_envio_neto = {}
    for i, (sid, ords) in enumerate(shipment_orders.items()):
        s = get_shipment(sid)
        ltype = s.get('logistic_type') or 'sin_tipo'
        shipment_type[sid] = ltype

        egreso_real = 0.0
        for o in ords:
            p = get_payment(o['payments'][0]['id'])
            for c in p.get('charges_details', []):
                if c.get('type') == 'shipping':
                    egreso_real += c['amounts']['original']

        ingreso_flex = 0.0
        if ltype == 'self_service':
            c = get_shipment_costs(sid)
            receiver_cost = c.get('receiver', {}).get('cost', 0) or 0
            senders_save = c.get('senders', [{}])[0].get('save', 0) or 0
            gross = c.get('gross_amount', 0) or 0
            ingreso_flex = receiver_cost or senders_save or gross

        shipment_envio_neto[sid] = egreso_real - ingreso_flex
        if (i + 1) % 20 == 0:
            time.sleep(1)

    # ---- armar el registro por orden/producto ----
    registros = []
    for sid, ords in shipment_orders.items():
        total_venta_shipment = sum(o['total_amount'] for o in ords) or 1
        for o in ords:
            item = o['order_items'][0]['item']
            item_id = item['id']
            if item_id in EXCLUIR_ITEM_IDS:
                continue
            fecha_venta = date.fromisoformat(o['date_created'][:10])
            qty = o['order_items'][0]['quantity']
            venta = o['total_amount']
            costo_unit = costo_vigente(item_id, fecha_venta)
            costo = (costo_unit or 0) * qty
            envio = shipment_envio_neto[sid] * (venta / total_venta_shipment)
            registros.append({
                'order_id': o['id'], 'item_id': item_id, 'title': item['title'],
                'sku': item.get('seller_sku') or '', 'cat_id': item['category_id'],
                'qty': qty, 'logistic_type': shipment_type[sid],
                'venta': round(venta, 2), 'costo': round(costo, 2),
                'cargo': round(cargo_by_order.get(str(o['id']), 0.0), 2),
                'descuento': round(descuento_by_order.get(str(o['id']), 0.0), 2),
                'envio': round(envio, 2),
            })
    return registros


if __name__ == '__main__':
    archivo, start_local, end_local = sys.argv[1], sys.argv[2], sys.argv[3]
    neto = '--neto' in sys.argv[4:]
    all_orders = json.load(open(f'ordenes_{archivo}.json', encoding='utf-8'))
    orders = [o for o in all_orders if start_local <= o['date_created'][:10] <= end_local]
    print(f'{len(orders)} ordenes en {start_local}..{end_local}')
    registros = compute(orders, neto=neto)
    out_path = f'venta_detalle_{archivo}.json'
    json.dump(registros, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Guardado {out_path} ({len(registros)} registros)')
