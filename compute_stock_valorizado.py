"""
Arma la tabla "stock_valorizado": una foto del stock de cada publicacion
ACTIVA (excluyendo kits/combos) con su precio publicado y el importe
(stock x precio), fechada al dia que se corre. Pensada para correr una vez
por dia como parte de /actualizar-tablero y asi ir construyendo un
historico -- hoy no existe ningun otro lado del pipeline que guarde stock,
solo ventas, asi que sin esta tabla "el stock de tal dia" no se puede
reconstruir despues (Lucas, 2026-08-03).

Kits: se excluyen los items que tengan el tag "bundle" en su publicacion --
son combos armados a partir de otros productos individuales (que si estan
en la tabla), no tienen stock propio real (confirmado 2026-08-03 revisando
un caso real con Lucas: un item con tag "bundle" resulto ser exactamente
eso, compuesto por otros productos ya listados aparte).

Catalogo + tradicional duplicados: cuando dos publicaciones activas
comparten el mismo "user_product_id", son el MISMO stock fisico mostrado
dos veces (confirmado 2026-08-10 con un caso real: L-arginina M1 Energy
tenia dos item_id con el mismo user_product_id y el mismo stock, precios
distintos) -- sumar las dos duplica el valor. Se deja solo la de menor
precio del grupo (Lucas confirmo que esa es la de catalogo en el caso que
motivo esto).

Uso:
    python compute_stock_valorizado.py

Mergea sobre stock_valorizado.json existente por (fecha, item_id) -- si se
corre mas de una vez el mismo dia, reemplaza la foto de ese dia en vez de
duplicarla; no toca fotos de otros dias.
"""
import json
import os
import sys
import time
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()
SELLER_ID = 42206571


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
        if r.status_code == 401:
            TOKEN = refresh_token()
            HEADERS = {'Authorization': f'Bearer {TOKEN}'}
            continue
        if r.status_code == 429:
            time.sleep(15)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f'too many retries: {url}')


if __name__ == '__main__':
    fecha = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    item_ids = []
    offset = 0
    while True:
        d = get(f'https://api.mercadolibre.com/users/{SELLER_ID}/items/search', params={'offset': offset, 'limit': 100, 'status': 'active'})
        ids = d.get('results', [])
        item_ids.extend(ids)
        paging = d.get('paging', {})
        if offset + 100 >= paging.get('total', 0):
            break
        offset += 100

    nuevos = []
    n_kits_excluidos = 0
    for i in range(0, len(item_ids), 20):
        chunk = item_ids[i:i + 20]
        d = get('https://api.mercadolibre.com/items', params={'ids': ','.join(chunk)})
        for entry in d:
            it = entry.get('body', {})
            if 'bundle' in (it.get('tags') or []):
                n_kits_excluidos += 1
                continue
            sku = it.get('seller_custom_field')
            if not sku:
                for attr in it.get('attributes', []):
                    if attr.get('id') == 'SELLER_SKU':
                        sku = attr.get('value_name')
            stock = it.get('available_quantity') or 0
            precio = it.get('price') or 0
            nuevos.append({
                'fecha': fecha, 'item_id': it.get('id'), 'sku': sku or '',
                'producto': it.get('title'), 'stock': stock, 'precio': precio,
                'importe': round(stock * precio, 2),
                'user_product_id': it.get('user_product_id'),
            })

    # catalogo + tradicional duplicados: mismo user_product_id = mismo stock
    # fisico mostrado dos veces -- dejar solo la de menor precio del grupo.
    por_user_product = {}
    for r in nuevos:
        upid = r['user_product_id']
        if not upid:
            continue
        por_user_product.setdefault(upid, []).append(r)
    n_duplicados_excluidos = 0
    excluir_item_ids = set()
    for upid, grupo in por_user_product.items():
        if len(grupo) > 1:
            grupo.sort(key=lambda r: r['precio'])
            for r in grupo[1:]:
                excluir_item_ids.add(r['item_id'])
                n_duplicados_excluidos += 1
    nuevos = [r for r in nuevos if r['item_id'] not in excluir_item_ids]
    for r in nuevos:
        del r['user_product_id']

    existing = json.load(open('stock_valorizado.json', encoding='utf-8')) if os.path.exists('stock_valorizado.json') else []
    existing = [r for r in existing if r['fecha'] != fecha]
    registros = existing + nuevos
    registros.sort(key=lambda r: (r['fecha'], -r['importe']))

    json.dump(registros, open('stock_valorizado.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    total = sum(r['importe'] for r in nuevos)
    print(f'{fecha}: {len(nuevos)} publicaciones ({n_kits_excluidos} kits excluidos, {n_duplicados_excluidos} duplicados catalogo/tradicional excluidos), valor total ${total:,.2f}')
    print(f'Guardado stock_valorizado.json ({len(registros)} filas en total, {len(set(r["fecha"] for r in registros))} fechas distintas)')
