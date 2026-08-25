"""
Desglosa ingresos y egresos de envio (los que vienen de una venta puntual,
no informativos) por logistic_type del shipment (self_service=Flex,
fulfillment=Full, xd_drop_off, etc.), para un rango de fechas dentro de un
archivo ordenes_<archivo>.json ya guardado.

Uso:
    python compute_envio_por_tipo.py <archivo_ordenes> <fecha_desde> <fecha_hasta>
    python compute_envio_por_tipo.py julio 2026-07-01 2026-07-20

Imprime, por logistic_type: ingreso (credito Flex via regla en cascada),
egreso (cargos reales type=shipping en charges_details del pago), y cantidad
de shipments. Autonomos/Alan Jalef/etc. no entran aca porque no estan atados
a un envio puntual.
"""
import json
import os
import sys
import time
from collections import defaultdict

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


def get_payment(payment_id):
    for _ in range(5):
        r = requests.get(f'https://api.mercadopago.com/v1/payments/{payment_id}', headers=HEADERS)
        if r.status_code == 429:
            time.sleep(5)
            continue
        return r.json()
    raise RuntimeError('too many retries')


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


def compute(orders):
    # shipment_id -> lista de order_ids (para no pedir el shipment mas de una vez)
    shipment_to_orders = defaultdict(list)
    for o in orders:
        sid = o.get('shipping', {}).get('id')
        if sid:
            shipment_to_orders[sid].append(o['id'])

    shipment_type = {}
    for i, sid in enumerate(shipment_to_orders):
        s = get_shipment(sid)
        shipment_type[sid] = s.get('logistic_type') or 'sin_tipo'
        if (i + 1) % 20 == 0:
            time.sleep(1)

    ingreso_flex_por_shipment = {}
    for sid, ltype in shipment_type.items():
        if ltype == 'self_service':
            c = get_shipment_costs(sid)
            receiver_cost = c.get('receiver', {}).get('cost', 0) or 0
            senders_save = c.get('senders', [{}])[0].get('save', 0) or 0
            gross = c.get('gross_amount', 0) or 0
            ingreso_flex_por_shipment[sid] = receiver_cost or senders_save or gross

    breakdown = defaultdict(lambda: {'ingreso': 0.0, 'egreso': 0.0, 'shipments': set()})

    # ingreso: una vez por shipment (no por orden, para no contarlo N veces
    # si un shipment tiene varias ordenes del mismo pack)
    for sid, ltype in shipment_type.items():
        if sid in ingreso_flex_por_shipment:
            breakdown[ltype]['ingreso'] += ingreso_flex_por_shipment[sid]
        breakdown[ltype]['shipments'].add(sid)

    # egreso: por pago (charges_details type=shipping), atribuido al tipo del
    # shipment de esa orden
    order_to_sid = {o['id']: o.get('shipping', {}).get('id') for o in orders}
    for i, o in enumerate(orders):
        pid = o['payments'][0]['id']
        p = get_payment(pid)
        sid = order_to_sid[o['id']]
        ltype = shipment_type.get(sid, 'sin_tipo')
        for c in p.get('charges_details', []):
            if c.get('type') == 'shipping':
                breakdown[ltype]['egreso'] += c['amounts']['original']
        if (i + 1) % 20 == 0:
            time.sleep(1)

    return {ltype: {'ingreso': round(d['ingreso'], 2), 'egreso': round(d['egreso'], 2), 'shipments': len(d['shipments'])}
            for ltype, d in breakdown.items()}


if __name__ == '__main__':
    archivo, start_local, end_local = sys.argv[1], sys.argv[2], sys.argv[3]
    all_orders = json.load(open(f'ordenes_{archivo}.json', encoding='utf-8'))
    orders = [o for o in all_orders if start_local <= o['date_created'][:10] <= end_local]
    print(f'{len(orders)} ordenes en {start_local}..{end_local}')
    result = compute(orders)
    print(json.dumps(result, indent=2, ensure_ascii=False))
