"""
Arma la tabla "base_envios": una fila por ORDEN pagada, con el detalle de
envio (tipo de logistica, ingreso y costo real), en pesos con IVA y sin IVA.

Mismos criterios que compute_base_ventas.py (ver memoria
mercadolibre-base-ventas / mercadolibre-base-envios):
- Solo ordenes con status=="paid".
- Costo por envio = charges_details type=="shipping" del pago (solo aparece
  cuando es un costo real; Full seguido lava a $0).
- Ingreso por envio = solo si logistic_type=="self_service" (Flex), desde
  /shipments/{id}/costs (receiver.cost -> senders[0].save -> gross_amount).
- Si el shipment lo comparten varias ordenes del mismo pack, ingreso y costo
  se prorratean entre ellas por el peso de cada una en el importe total del
  shipment (mismo criterio que base_ventas) -- solo funciona bien si todas
  las ordenes que comparten un shipment se procesan en la misma corrida.
- IDs de orden/pack como texto en el Sheet (evita que Excel los rompa).
- Ingreso/Costo con IVA tal cual vienen de la API; version sin IVA = /1.21.

Uso:
    python compute_base_envios.py <order_id> [<order_id> ...]

Escribe/actualiza base_envios.json (dict order_id -> fila).
"""
import json
import os
import sys
import time
from collections import defaultdict

import requests
from dotenv import load_dotenv

load_dotenv()
IVA = 1.21

SHIP_TYPE_NAMES = {
    'self_service': 'Flex',
    'fulfillment': 'Full',
    'xd_drop_off': 'Colecta/Cross-docking',
    'sin_tipo': 'Sin tipo',
}


def refresh_token():
    token_data = json.load(open('token.json'))
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


def get_token():
    token_data = json.load(open('token.json'))
    headers = {'Authorization': f'Bearer {token_data["access_token"]}'}
    r = requests.get('https://api.mercadolibre.com/users/me', headers=headers)
    if r.status_code == 401:
        return refresh_token()
    return token_data['access_token']


TOKEN = get_token()
HEADERS = {'Authorization': f'Bearer {TOKEN}'}


def get(url, params=None):
    global TOKEN, HEADERS
    for _ in range(5):
        r = requests.get(url, headers=HEADERS, params=params)
        if r.status_code == 429:
            time.sleep(5)
            continue
        if r.status_code == 401:
            TOKEN = refresh_token()
            HEADERS = {'Authorization': f'Bearer {TOKEN}'}
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f'too many retries: {url}')


def get_mp(url):
    return get(url)


def fetch_order_base(order_id):
    """Datos propios de la orden. Devuelve None si no esta 'paid'."""
    o = get(f'https://api.mercadolibre.com/orders/{order_id}')
    if o['status'] != 'paid':
        print(f'  orden {order_id}: status={o["status"]!r}, no es "paid" -- se excluye')
        return None

    # sumar TODOS los payments aprobados, no solo payments[0] -- ver el mismo
    # fix en compute_base_ventas.py / mercadolibre-base-ventas
    envio_cargo_propio = 0.0
    for pago in o['payments']:
        if pago.get('status') != 'approved':
            continue
        p = get_mp(f'https://api.mercadopago.com/v1/payments/{pago["id"]}')
        envio_cargo_propio += sum(
            c['amounts']['original'] for c in p.get('charges_details', []) if c.get('type') == 'shipping'
        )

    return {
        'order_id': o['id'], 'pack_id': o.get('pack_id'), 'fecha': o['date_created'][:10],
        'importe': o['total_amount'], 'envio_cargo_propio': envio_cargo_propio,
        'shipment_id': o.get('shipping', {}).get('id'),
    }


if __name__ == '__main__':
    order_ids = [int(x) for x in sys.argv[1:]]
    if not order_ids:
        print('Uso: python compute_base_envios.py <order_id> [<order_id> ...]')
        sys.exit(1)

    print('Trayendo datos de cada orden...')
    order_base = {}
    excluidas = []
    for oid in order_ids:
        b = fetch_order_base(oid)
        if b is not None:
            order_base[oid] = b
        else:
            excluidas.append(oid)

    shipment_orders = defaultdict(list)
    for oid, b in order_base.items():
        if b['shipment_id']:
            shipment_orders[b['shipment_id']].append(oid)

    envio_cargo_final = {}
    envio_ingreso_final = {}
    envio_pasante_final = {}
    tipo_final = {}
    for sid, oids in shipment_orders.items():
        s = get(f'https://api.mercadolibre.com/shipments/{sid}')
        ltype = s.get('logistic_type') or 'sin_tipo'
        total_egreso = sum(order_base[o]['envio_cargo_propio'] for o in oids)
        total_ingreso = 0.0
        es_pasante = False
        if ltype == 'self_service':
            costs = get(f'https://api.mercadolibre.com/shipments/{sid}/costs')
            receiver_cost = costs.get('receiver', {}).get('cost', 0) or 0
            senders_save = costs.get('senders', [{}])[0].get('save', 0) or 0
            gross = costs.get('gross_amount', 0) or 0
            total_ingreso = receiver_cost or senders_save or gross
        elif total_egreso > 0:
            # Full/Colecta con cargo real -- puede ser pasante financiado por
            # el comprador (senders[0].cost == 0), ver compute_base_ventas.py
            # para el detalle completo de por que se agrego este chequeo. Se
            # guarda aparte en envio_pasante_final para separarlo del costo
            # real en el P&L/dashboard (pedido de Lucas 2026-08-18).
            costs = get(f'https://api.mercadolibre.com/shipments/{sid}/costs')
            senders_cost = costs.get('senders', [{}])[0].get('cost', 0) or 0
            if senders_cost == 0:
                total_ingreso = total_egreso
                es_pasante = True
        total_importe = sum(order_base[o]['importe'] for o in oids) or 1
        for o in oids:
            share = order_base[o]['importe'] / total_importe
            envio_cargo_final[o] = total_egreso * share
            envio_ingreso_final[o] = total_ingreso * share
            envio_pasante_final[o] = (total_egreso * share) if es_pasante else 0.0
            tipo_final[o] = ltype
        if len(oids) > 1:
            print(f'  shipment {sid} compartido por {len(oids)} ordenes -> prorrateado por importe')

    for oid, b in order_base.items():
        if not b['shipment_id']:
            envio_cargo_final[oid] = 0.0
            envio_ingreso_final[oid] = 0.0
            envio_pasante_final[oid] = 0.0
            tipo_final[oid] = 'sin_tipo'

    base = {}
    if os.path.exists('base_envios.json'):
        base = json.load(open('base_envios.json', encoding='utf-8'))

    # una orden que estaba guardada (paid en su momento) puede pasar a
    # cancelled/refunded despues -- si eso paso, hay que sacarla del archivo,
    # no dejarla con los datos viejos de cuando todavia era paid.
    for oid in excluidas:
        if str(oid) in base:
            print(f'  orden {oid} ya no es "paid" -- se elimina de base_envios.json (tenia datos guardados de cuando si lo era)')
            del base[str(oid)]

    for oid, b in order_base.items():
        ingreso_c = envio_ingreso_final[oid]
        costo_c = envio_cargo_final[oid]
        pasante_c = envio_pasante_final[oid]
        base[str(oid)] = {
            'order_id': b['order_id'], 'pack_id': b['pack_id'], 'fecha': b['fecha'],
            'shipment_id': b['shipment_id'], 'tipo_envio': SHIP_TYPE_NAMES.get(tipo_final[oid], tipo_final[oid]),
            'ingreso_c': round(ingreso_c, 2), 'ingreso_s': round(ingreso_c / IVA, 2),
            'costo_c': round(costo_c, 2), 'costo_s': round(costo_c / IVA, 2),
            'pasante_c': round(pasante_c, 2), 'pasante_s': round(pasante_c / IVA, 2),
        }

    json.dump(base, open('base_envios.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Guardado base_envios.json ({len(base)} ordenes en total)')
