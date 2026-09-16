"""
Arma la tabla "publicaciones_recibis": una foto de cuanto RECIBE Lucas neto
por cada publicacion ACTIVA si se vende hoy a su precio de lista --
Precio - Comision (cargo por vender + cuotas) - Envio absorbido (cuando el
envio es gratis y lo paga el vendedor) -- fechada al dia que se corre.

Metodologia confirmada a mano con Lucas comparando contra el desglose real
del panel de MercadoLibre (icono "i" junto a "Recibis" en Mis publicaciones),
2026-09-15:

1. Comision: GET /sites/MLA/listing_prices con category_id, price,
   listing_type_id, logistic_type, shipping_mode, billable_weight (estos
   4 ultimos son OBLIGATORIOS en Argentina -- sin ellos el fixed_fee que
   devuelve no coincide con lo que ML cobra realmente) y tags=<campaña de
   cuotas activa> si el item tiene sale_terms.INSTALLMENTS_CAMPAIGN.
   sale_fee_amount ya es el costo total por vender (cargo por vender +
   costo fijo por unidad + costo de cuotas, todo sumado) -- no hay que
   sumarle nada mas.
2. Envio absorbido: SOLO si shipping.free_shipping es true. GET
   /users/{seller_id}/shipping_options/free con dimensions
   ("LxWxH,peso_gramos" de los atributos SELLER_PACKAGE_*, o PACKAGE_* si
   el vendedor no cargo los propios), item_price, listing_type_id,
   mode (shipping.mode), condition, logistic_type, free_shipping=true.
   coverage.all_country.list_cost es el envio que absorbe el vendedor.
   Si free_shipping es false, el comprador paga el envio y esto es 0.
3. Recibis = Precio - Comision - Envio absorbido.

Validado exacto contra 3 capturas reales del panel de Lucas (Treonato De
Magnesio $15.174, Creatina ENA Sport $20.510, Cuchillo Asado Nicols Delta
$29.067,56 con promocion activa incluida).

Catalogo + tradicional duplicados: igual que en stock_valorizado, cuando
dos publicaciones activas comparten el mismo "user_product_id" es el MISMO
producto fisico publicado dos veces. A diferencia de stock_valorizado (que
se queda con la de MENOR PRECIO), aca nos quedamos con la de MENOR RECIBIS
-- confirmado con Lucas 2026-09-15 que un precio mas alto no siempre es
mejor negocio (ej. real: gold_pro a $21.000 daba Recibis $12.191, gold_special
a $18.000 del mismo producto daba Recibis $12.470 -- el de menor precio
recibia MAS neto). El objetivo de esta tabla es el peor caso real de
ingreso, no el precio de lista.

Uso:
    python compute_publicaciones_recibis.py

Mergea sobre publicaciones_recibis.json existente por fecha -- si se corre
mas de una vez el mismo dia, reemplaza la foto de ese dia en vez de
duplicarla; no toca fotos de otros dias.
"""
import json
import os
import re
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


def numero(value_name):
    """'80 g' -> 80.0, '9.6 cm' -> 9.6. None si no hay valor."""
    if not value_name:
        return None
    m = re.search(r'[\d.]+', value_name.replace(',', '.'))
    return float(m.group()) if m else None


def atributo(attrs, attr_id):
    for a in attrs:
        if a.get('id') == attr_id:
            return numero(a.get('value_name'))
    return None


def campana_cuotas(sale_terms):
    for st in sale_terms:
        if st.get('id') == 'INSTALLMENTS_CAMPAIGN':
            return st.get('value_name')
    return None


def comision(item):
    attrs = item.get('attributes', [])
    weight = (atributo(attrs, 'SELLER_PACKAGE_WEIGHT') or atributo(attrs, 'PACKAGE_WEIGHT'))
    sh = item.get('shipping', {})
    params = {
        'price': item['price'], 'currency_id': 'ARS', 'category_id': item['category_id'],
        'listing_type_id': item['listing_type_id'],
        'logistic_type': sh.get('logistic_type') or 'not_specified',
        'shipping_mode': sh.get('mode') or 'not_specified',
    }
    if weight:
        params['billable_weight'] = weight
    tags = campana_cuotas(item.get('sale_terms', []))
    if tags:
        params['tags'] = tags
    d = get('https://api.mercadolibre.com/sites/MLA/listing_prices', params)
    if isinstance(d, list):
        d = d[0]
    return d.get('sale_fee_amount') or 0.0


def envio_absorbido(item):
    sh = item.get('shipping', {})
    if not sh.get('free_shipping'):
        return 0.0
    attrs = item.get('attributes', [])
    largo = atributo(attrs, 'SELLER_PACKAGE_LENGTH') or atributo(attrs, 'PACKAGE_LENGTH')
    ancho = atributo(attrs, 'SELLER_PACKAGE_WIDTH') or atributo(attrs, 'PACKAGE_WIDTH')
    alto = atributo(attrs, 'SELLER_PACKAGE_HEIGHT') or atributo(attrs, 'PACKAGE_HEIGHT')
    peso = atributo(attrs, 'SELLER_PACKAGE_WEIGHT') or atributo(attrs, 'PACKAGE_WEIGHT')
    if not all([largo, ancho, alto, peso]):
        print(f"  ADVERTENCIA: {item['id']} tiene envio gratis pero sin dimensiones/peso cargados -- "
              f"no se puede calcular el envio absorbido, queda en 0 (subestima el costo real).")
        return 0.0
    params = {
        'dimensions': f'{largo:g}x{ancho:g}x{alto:g},{peso:g}',
        'verbose': 'true',
        'item_price': item['price'],
        'listing_type_id': item['listing_type_id'],
        'mode': sh.get('mode') or 'me2',
        'condition': item.get('condition') or 'new',
        'logistic_type': sh.get('logistic_type') or 'not_specified',
        'free_shipping': 'true',
    }
    d = get(f'https://api.mercadolibre.com/users/{SELLER_ID}/shipping_options/free', params)
    return d.get('coverage', {}).get('all_country', {}).get('list_cost') or 0.0


if __name__ == '__main__':
    fecha = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    item_ids = []
    offset = 0
    while True:
        d = get('https://api.mercadolibre.com/users/{}/items/search'.format(SELLER_ID),
                 params={'offset': offset, 'limit': 100, 'status': 'active'})
        ids = d.get('results', [])
        item_ids.extend(ids)
        paging = d.get('paging', {})
        if offset + 100 >= paging.get('total', 0):
            break
        offset += 100

    items = []
    for i in range(0, len(item_ids), 20):
        chunk = item_ids[i:i + 20]
        d = get('https://api.mercadolibre.com/items', params={'ids': ','.join(chunk)})
        for entry in d:
            it = entry.get('body', {})
            if entry.get('code') == 200:
                items.append(it)

    n_kits_excluidos = 0
    nuevos = []
    for idx, it in enumerate(items):
        if 'bundle' in (it.get('tags') or []):
            n_kits_excluidos += 1
            continue
        precio = it.get('price') or 0.0
        try:
            c = comision(it)
            e = envio_absorbido(it)
        except Exception as exc:
            print(f"  ERROR en {it.get('id')}: {exc} -- se saltea")
            continue
        recibis = round(precio - c - e, 2)
        sku = it.get('seller_custom_field')
        if not sku:
            for attr in it.get('attributes', []):
                if attr.get('id') == 'SELLER_SKU':
                    sku = attr.get('value_name')
        nuevos.append({
            'fecha': fecha, 'item_id': it.get('id'), 'sku': sku or '', 'producto': it.get('title'),
            'precio': precio, 'comision': round(c, 2), 'envio_absorbido': round(e, 2), 'recibis': recibis,
            'user_product_id': it.get('user_product_id'),
        })
        if (idx + 1) % 10 == 0:
            print(f'  {idx + 1}/{len(items)} publicaciones procesadas')
            time.sleep(1)

    # catalogo + tradicional duplicados: mismo user_product_id = mismo producto
    # fisico publicado dos veces -- dejar solo la de MENOR RECIBIS (peor caso).
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
            grupo.sort(key=lambda r: r['recibis'])
            for r in grupo[1:]:
                excluir_item_ids.add(r['item_id'])
                n_duplicados_excluidos += 1
    nuevos = [r for r in nuevos if r['item_id'] not in excluir_item_ids]
    for r in nuevos:
        del r['user_product_id']

    existing = json.load(open('publicaciones_recibis.json', encoding='utf-8')) if os.path.exists('publicaciones_recibis.json') else []
    existing = [r for r in existing if r['fecha'] != fecha]
    registros = existing + nuevos
    registros.sort(key=lambda r: (r['fecha'], r['recibis']))

    json.dump(registros, open('publicaciones_recibis.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    total = sum(r['recibis'] for r in nuevos)
    print(f'{fecha}: {len(nuevos)} publicaciones ({n_kits_excluidos} kits excluidos, '
          f'{n_duplicados_excluidos} duplicados catalogo/tradicional excluidos por peor Recibis), '
          f'Recibis total si se vendiera todo hoy: ${total:,.2f}')
    print(f'Guardado publicaciones_recibis.json ({len(registros)} filas en total, '
          f'{len(set(r["fecha"] for r in registros))} fechas distintas)')
