"""
Arma la tabla "base_full": una fila por DIA con los cargos de Fulfillment
(Full) que NO estan capturados en ninguna otra tabla. Fuente: FACTURACION
(Billing API), grupo ML, marketplace "SHIPPING":
- Envio al deposito Full: detail_sub_type CFCB ("Cargo por servicio de
  colecta Full" -- el courier de ML que recoge la mercaderia del vendedor
  para llevarla al deposito) + BFCB (reversa, si aparece).
- Almacenamiento Full: detail_sub_type CFWA ("Cargo por servicio de
  almacenamiento Full") + BFWA (reversa, si aparece).
Juntos (CFCB + CFWA) forman exactamente la linea "Cargos de envios full"
que Mercado Libre muestra en el detalle de la factura -- verificado al
centavo contra dos facturas reales de Lucas (julio: $596,40 = solo CFWA,
CFCB no existia todavia ese periodo; agosto: $52.700,69 = $48.587,69 CFCB +
$4.113,00 CFWA).

OJO -- CFF y CXD (tambien marketplace "SHIPPING") NO son de Full, son la
linea general "Cargos de envios de Mercado Libre" (verificado: CFF+CXD
matchea esa linea exacto en dos facturas distintas). Un intento anterior de
esta tabla incluyo CFF por error pensando que era "envio Full" -- eso
inflaba el numero ~1000x (contaba envios normales de cualquier tipo, no
solo Full). Corregido 2026-07-31 con las facturas reales de Lucas.

Decision de Lucas (2026-07-31): ninguno de los dos (CFCB, CFWA) esta
capturado en ningun otro lado del pipeline -- van en esta tabla nueva,
tratados como Costo Variable en el punto de equilibrio (ver
mercadolibre-pnl-pipeline). Los montos de Facturacion vienen CON IVA -- se
divide por 1.21 para sin IVA, igual que base_ads.

Cache agresivo igual que base_ads: un periodo se marca "cerrado" en cuanto
deja de ser el periodo abierto de "hoy" y nunca se vuelve a pedir. Cache en
base_full_cache_state.json.

Uso:
    python compute_base_full.py <fecha_desde> <fecha_hasta>
    python compute_base_full.py 2026-05-01 2026-07-31

Mergea sobre base_full.json existente (no lo pisa entero).
"""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()
IVA = 1.21
CACHE_STATE_FILE = 'base_full_cache_state.json'

CODES_DEPOSITO = {'CFCB', 'BFCB'}
CODES_ALMACENAMIENTO = {'CFWA', 'BFWA'}
CODES_BONUS = {'BFCB', 'BFWA'}  # detail_type BONUS -- resta en vez de sumar


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


def billing_period_for_date(d):
    dd = date.fromisoformat(d)
    if dd.day >= 7:
        y, m = dd.year, dd.month + 1
    else:
        y, m = dd.year, dd.month
    if m > 12:
        y, m = y + 1, m - 12
    return f'{y}-{m:02d}-01'


def fetch_billing_once(period_key, group):
    by_id = {}
    last_id = 0
    reported_total = None
    while True:
        params = {'document_type': 'BILL', 'limit': 150}
        if last_id:
            params['from_id'] = last_id
        d = get(f'https://api.mercadolibre.com/billing/integration/periods/key/{period_key}/group/{group}/details', params=params)
        if reported_total is None:
            reported_total = d.get('total', 0)
        page = d.get('results', [])
        for e in page:
            did = e.get('charge_info', {}).get('detail_id')
            if did is not None:
                by_id[did] = e
        nl = d.get('last_id', 0)
        if not nl or nl == last_id or len(page) < 150:
            break
        last_id = nl
        time.sleep(0.3)
    if reported_total and len(by_id) < reported_total:
        return None
    return by_id


def fetch_billing(period_key, group):
    for attempt in range(4):
        by_id = fetch_billing_once(period_key, group)
        if by_id is not None:
            return by_id
        print(f'  (billing {period_key}/{group}: conteo inconsistente, reintentando...)')
    raise RuntimeError(f'No se pudo traer un conteo consistente de billing para {period_key}/{group}')


if __name__ == '__main__':
    fecha_desde, fecha_hasta = sys.argv[1], sys.argv[2]
    d0 = date.fromisoformat(fecha_desde)
    d1 = date.fromisoformat(fecha_hasta)

    existing = {r['fecha']: r for r in json.load(open('base_full.json', encoding='utf-8'))} if os.path.exists('base_full.json') else {}
    cache_state = json.load(open(CACHE_STATE_FILE, encoding='utf-8')) if os.path.exists(CACHE_STATE_FILE) else {'periodos_cerrados': {}}
    periodos_cerrados = cache_state['periodos_cerrados']

    all_periods = set()
    d = d0
    while d <= d1:
        all_periods.add(billing_period_for_date(d.isoformat()))
        d = date.fromordinal(d.toordinal() + 1)

    current_period = billing_period_for_date(date.today().isoformat())

    deposito_by_day = defaultdict(float)
    almacen_by_day = defaultdict(float)
    factura_by_period = {}
    periodos_pedidos_ahora = set()
    for pk in sorted(all_periods):
        if pk != current_period and pk in periodos_cerrados:
            print(f'Facturacion: periodo {pk} ya cacheado (cerrado) -- no se vuelve a pedir')
            factura_by_period[pk] = periodos_cerrados[pk]
            continue
        periodos_pedidos_ahora.add(pk)
        print(f'Facturacion: trayendo periodo {pk}...')
        by_id = fetch_billing(pk, 'ML')
        if pk == current_period:
            factura_by_period[pk] = 'pendiente fc'
        else:
            algun_entry = next(iter(by_id.values()), None)
            # un periodo cerrado se cachea SIEMPRE, incluso sin entradas -- si
            # dependiera de encontrar una factura, un periodo con 0 entradas
            # totales nunca se cachearia y se volveria a pedir para siempre.
            factura_by_period[pk] = algun_entry['charge_info']['legal_document_number'] if algun_entry else 'sin cargos este periodo'
            periodos_cerrados[pk] = factura_by_period[pk]
        n_deposito = n_almacen = 0
        for e in by_id.values():
            if e.get('marketplace_info', {}).get('marketplace') != 'SHIPPING':
                continue
            code = e['charge_info']['detail_sub_type']
            if code not in CODES_DEPOSITO and code not in CODES_ALMACENAMIENTO:
                continue
            day = e['charge_info']['creation_date_time'][:10]
            if not (fecha_desde <= day <= fecha_hasta):
                continue
            amount = e['charge_info']['detail_amount']
            signed = -amount if code in CODES_BONUS else amount
            if code in CODES_DEPOSITO:
                deposito_by_day[day] += signed
                n_deposito += 1
            else:
                almacen_by_day[day] += signed
                n_almacen += 1
        print(f'  {n_deposito} entradas envio al deposito Full (CFCB), {n_almacen} entradas almacenamiento Full (CFWA) -- factura: {factura_by_period[pk]}')

    dias_frescos = set()
    d = d0
    while d <= d1:
        iso = d.isoformat()
        if billing_period_for_date(iso) in periodos_pedidos_ahora:
            dias_frescos.add(iso)
        d = date.fromordinal(d.toordinal() + 1)

    for day in dias_frescos:
        base = dict(existing.get(day, {'fecha': day, 'factura': 'pendiente fc', 'deposito_full_s': 0, 'deposito_full_c': 0, 'almacenamiento_full_s': 0, 'almacenamiento_full_c': 0}))
        deposito_c = deposito_by_day.get(day, 0.0)
        almacen_c = almacen_by_day.get(day, 0.0)
        base['deposito_full_s'] = round(deposito_c / IVA, 2)
        base['deposito_full_c'] = round(deposito_c, 2)
        base['almacenamiento_full_s'] = round(almacen_c / IVA, 2)
        base['almacenamiento_full_c'] = round(almacen_c, 2)
        base['factura'] = factura_by_period.get(billing_period_for_date(day), base.get('factura', 'pendiente fc'))
        existing[day] = base

    registros = [r for r in existing.values() if r['deposito_full_c'] or r['almacenamiento_full_c']]
    registros.sort(key=lambda r: r['fecha'])

    json.dump(registros, open('base_full.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    cache_state['periodos_cerrados'] = periodos_cerrados
    json.dump(cache_state, open(CACHE_STATE_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Guardado base_full.json ({len(registros)} dias) -- {len(periodos_cerrados)} periodos cacheados como cerrados')
