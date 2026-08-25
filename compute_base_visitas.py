"""
Arma "base_visitas": una fila por dia con Visitas (API de MercadoLibre,
nivel cuenta -- todas las publicaciones sumadas), Compras (cantidad de
ORDENES pagas ese dia, de base_ventas.json -- Lucas confirmo 2026-08-20 que
CVR se calcula sobre cantidad de ordenes, no unidades vendidas) y
CVR = Compras / Visitas.

Fuente de Visitas: /users/{seller_id}/items_visits/time_window?last=N&unit=day
-- endpoint a nivel de CUENTA (no hay que sumar item por item), un solo
llamado. Limite duro confirmado 2026-08-20: last=120 funciona, last=180 tira
400 Bad Request -- no se puede pedir mas de 120 dias hacia atras de una. Como
el historico de ventas de Deleite arranca 2026-05-02 (bien dentro de los 120
dias desde hoy), un solo llamado alcanza para cubrir todo por ahora. Cuando
en el futuro el historico supere los 120 dias, los dias mas viejos que ya
esten guardados en base_visitas.json se conservan tal cual (nunca se pueden
re-pedir retroactivamente si no se llegaron a guardar a tiempo -- mismo
gotcha que stock_valorizado, "no hay forma de reconstruir para atras").

Uso:
    python compute_base_visitas.py

Mergea sobre base_visitas.json existente por fecha (upsert) -- no duplica ni
toca otros dias. El dia de hoy va a quedar parcial hasta que termine (las
visitas siguen sumando durante el dia); volver a correr el mismo dia lo
actualiza.
"""
import json
import os
import time
from collections import defaultdict
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
    d = get(f'https://api.mercadolibre.com/users/{SELLER_ID}/items_visits/time_window',
             params={'last': 120, 'unit': 'day'})

    visitas_por_dia = {}
    for entry in d.get('results', []):
        fecha = entry['date'][:10]
        visitas_por_dia[fecha] = entry.get('total', 0)

    base_ventas = json.load(open('base_ventas.json', encoding='utf-8'))
    ordenes_por_dia = defaultdict(set)
    for r in base_ventas.values():
        ordenes_por_dia[r['fecha']].add(r['order_id'])
    compras_por_dia = {fecha: len(ids) for fecha, ids in ordenes_por_dia.items()}

    todas_fechas = sorted(set(visitas_por_dia) | set(compras_por_dia))
    nuevos = []
    for fecha in todas_fechas:
        visitas = visitas_por_dia.get(fecha, 0)
        compras = compras_por_dia.get(fecha, 0)
        cvr = compras / visitas if visitas else 0.0
        nuevos.append({'fecha': fecha, 'visitas': visitas, 'compras': compras, 'cvr': round(cvr, 4)})

    existing = json.load(open('base_visitas.json', encoding='utf-8')) if os.path.exists('base_visitas.json') else []
    fechas_nuevas = {r['fecha'] for r in nuevos}
    existing = [r for r in existing if r['fecha'] not in fechas_nuevas]
    registros = existing + nuevos
    registros.sort(key=lambda r: r['fecha'])

    json.dump(registros, open('base_visitas.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'{len(nuevos)} dias actualizados ({todas_fechas[0]}..{todas_fechas[-1]})')
    print(f'Guardado base_visitas.json ({len(registros)} dias en total)')
