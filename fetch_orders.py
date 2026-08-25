"""
Trae y guarda las ordenes validas (sin canceladas/reembolsadas) de un rango
de fechas, filtrando por la fecha LOCAL real de la orden (no UTC). Mergea con
lo que ya haya en ordenes_<mes>.json (por order id) en vez de pisarlo, para
poder correr solo el rango de dias nuevo sin duplicar ni perder lo anterior.

Uso:
    python fetch_orders.py --status
        Muestra, para cada ordenes_<mes>.json que ya exista, hasta que fecha
        hay datos. Correr esto ANTES de pedirle a Lucas el rango a actualizar.

    python fetch_orders.py <nombre_mes> <fecha_desde> <fecha_hasta>
        python fetch_orders.py julio 2026-07-22 2026-07-25
        Trae ese rango y lo mergea (por id) dentro de ordenes_julio.json.
        Si un pedido que ya estaba paso a cancelado/reembolsado, se saca del
        archivo al re-fetchear su rango (el merge SIEMPRE re-aplica el filtro
        de validez sobre el resultado combinado).
"""
import glob
import json
import sys
from datetime import date, timedelta

import requests

SELLER_ID = 42206571


def refresh_token_if_needed():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    token_data = json.load(open('token.json'))
    r = requests.get('https://api.mercadolibre.com/users/me',
                      headers={'Authorization': f'Bearer {token_data["access_token"]}'})
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


def get_orders_raw(headers, start_local, end_local):
    """Todas las ordenes del rango (incluye canceladas/reembolsadas)."""
    q_from = (date.fromisoformat(start_local) - timedelta(days=1)).isoformat() + 'T00:00:00.000-00:00'
    q_to = (date.fromisoformat(end_local) + timedelta(days=2)).isoformat() + 'T00:00:00.000-00:00'
    orders = []
    offset = 0
    while True:
        r = requests.get('https://api.mercadolibre.com/orders/search', headers=headers,
            params={'seller': SELLER_ID, 'order.date_created.from': q_from,
                    'order.date_created.to': q_to, 'sort': 'date_desc', 'limit': 50, 'offset': offset})
        data = r.json()
        results = data.get('results', [])
        if not results:
            break
        orders.extend(results)
        offset += 50
        if offset >= data.get('paging', {}).get('total', 0):
            break
    return [o for o in orders if start_local <= o['date_created'][:10] <= end_local]


def is_valid(o):
    payment_status = o['payments'][0]['status'] if o.get('payments') else None
    return o['status'] != 'cancelled' and payment_status != 'refunded'


def show_status():
    files = sorted(glob.glob('ordenes_*.json'))
    if not files:
        print('No hay ningun ordenes_*.json todavia.')
        return
    for path in files:
        mes = path.replace('ordenes_', '').replace('.json', '')
        orders = json.load(open(path, encoding='utf-8'))
        if not orders:
            print(f'{mes}: archivo vacio')
            continue
        fechas = sorted(o['date_created'][:10] for o in orders)
        print(f'{mes}: {len(orders)} ordenes, desde {fechas[0]} hasta {fechas[-1]}')


def fetch_and_merge(nombre_mes, start_local, end_local):
    token = refresh_token_if_needed()
    headers = {'Authorization': f'Bearer {token}'}

    path = f'ordenes_{nombre_mes}.json'
    try:
        existentes = json.load(open(path, encoding='utf-8'))
    except FileNotFoundError:
        existentes = []

    por_id = {o['id']: o for o in existentes}
    n_antes = len(por_id)

    nuevas_raw = get_orders_raw(headers, start_local, end_local)
    for o in nuevas_raw:
        por_id[o['id']] = o  # la version recien traida siempre pisa (status mas fresco)

    merged_valid = [o for o in por_id.values() if is_valid(o)]
    merged_valid.sort(key=lambda o: o['date_created'])

    print(f'{nombre_mes}: {n_antes} ordenes ya guardadas, {len(nuevas_raw)} traidas en el rango '
          f'{start_local}..{end_local}, {len(por_id)} unicas en total, {len(merged_valid)} validas tras el merge')

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(merged_valid, f, ensure_ascii=False)
    print(f'Guardado {path}')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--status']:
        show_status()
    else:
        nombre_mes, start_local, end_local = sys.argv[1], sys.argv[2], sys.argv[3]
        fetch_and_merge(nombre_mes, start_local, end_local)
