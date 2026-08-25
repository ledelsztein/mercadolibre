"""
Arma la tabla "base_ads": una fila por DIA (sin desglose por campania), con:
- Costo: de FACTURACION (Billing API, marketplace MCLICS, grupo ML) -- es la
  plata real que cobra Mercado Libre, incluye Product Ads Y Display Ads
  (la API de Ads solo puede ver Product Ads, por eso el costo NO sale de ahi).
- Ventas atribuidas, Impresiones, Clicks: de la API de Ads (Product Ads),
  sumadas entre todas las campanias del dia.

Decision de Lucas (2026-07-24): "lo que es junio es junio, no me importa si
se facturo en julio" -- cada dia se atribuye por su FECHA REAL
(creation_date_time), no por el periodo de facturacion en el que cayo (los
periodos corren 7-a-6, no calendario -- ver mercadolibre-pnl-pipeline). Por
eso hay que traer todos los periodos que tocan el rango pedido y filtrar
despues por fecha real.

Cache agresivo (Lucas, 2026-07-31): no hace falta llamar siempre a las APIs.
- Costo (Facturacion): un periodo se marca "cerrado" en cuanto deja de ser el
  periodo abierto de "hoy" -- una vez cerrado, NUNCA se vuelve a pedir. Se
  guarda en base_ads_cache_state.json (periodos_cerrados: {period_key:
  factura}). El periodo abierto (el que cubre "hoy") se re-pide siempre,
  porque todavia esta acumulando.
- Ventas/Impresiones/Clicks (API de Ads): se trackea un watermark
  "ads_checked_hasta" -- solo se pide a la API el tramo de dias posterior a
  ese watermark, nunca lo ya chequeado (evita re-pedir dias ya confirmados,
  incluso los que dieron $0 de venta atribuida ese dia).
Ambos cachés viven en base_ads_cache_state.json. Si algun numero de un
periodo YA cerrado resultara estar mal (ML ajusto tarde, como paso una vez
con un +$107K dos dias despues de cerrado), hay que borrar esa entrada de
periodos_cerrados a mano para forzar un refetch.

Uso:
    python compute_base_ads.py <fecha_desde> <fecha_hasta>
    python compute_base_ads.py 2026-05-01 2026-07-31

Mergea sobre base_ads.json existente (no lo pisa entero) -- ver cache
agresivo arriba.
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
SITE_ID = 'MLA'
CACHE_STATE_FILE = 'base_ads_cache_state.json'


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
ADS_HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Api-Version': '2'}


def get(url, params=None, ads=False):
    global TOKEN, HEADERS, ADS_HEADERS
    h = ADS_HEADERS if ads else HEADERS
    for _ in range(5):
        r = requests.get(url, headers=h, params=params)
        if r.status_code == 401:
            TOKEN = refresh_token()
            HEADERS = {'Authorization': f'Bearer {TOKEN}'}
            ADS_HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Api-Version': '2'}
            h = ADS_HEADERS if ads else HEADERS
            continue
        if r.status_code == 429:
            time.sleep(5)
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


def get_advertiser_id():
    d = get('https://api.mercadolibre.com/advertising/advertisers', params={'product_id': 'PADS'}, ads=True)
    return d['advertisers'][0]['advertiser_id']


ADS_MAX_DAYS = 90


def chunks_90d(d0, d1):
    cur = d0
    while cur <= d1:
        end = min(d1, date.fromordinal(cur.toordinal() + ADS_MAX_DAYS - 1))
        yield cur.isoformat(), end.isoformat()
        cur = date.fromordinal(end.toordinal() + 1)


if __name__ == '__main__':
    fecha_desde, fecha_hasta = sys.argv[1], sys.argv[2]
    d0 = date.fromisoformat(fecha_desde)
    d1 = date.fromisoformat(fecha_hasta)

    existing = {r['fecha']: r for r in json.load(open('base_ads.json', encoding='utf-8'))} if os.path.exists('base_ads.json') else {}
    cache_state = json.load(open(CACHE_STATE_FILE, encoding='utf-8')) if os.path.exists(CACHE_STATE_FILE) else {'periodos_cerrados': {}, 'ads_checked_hasta': None}
    periodos_cerrados = cache_state['periodos_cerrados']

    # ---- Costo real: Facturacion, marketplace MCLICS (Product Ads + Display Ads) ----
    # Cache agresivo: un periodo cerrado no se vuelve a pedir NUNCA (solo el
    # periodo abierto de "hoy" se re-pide siempre, porque sigue acumulando).
    all_periods = set()
    d = d0
    while d <= d1:
        all_periods.add(billing_period_for_date(d.isoformat()))
        d = date.fromordinal(d.toordinal() + 1)

    current_period = billing_period_for_date(date.today().isoformat())

    costo_by_day = defaultdict(float)
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
        # la factura es unica por periodo (mismo document/legal_document_number
        # para TODOS los tipos de cargo, no solo MCLICS) -- si el periodo sigue
        # abierto (es el que cubre "hoy") todavia no tiene numero de comprobante.
        if pk == current_period:
            factura_by_period[pk] = 'pendiente fc'
        else:
            algun_entry = next(iter(by_id.values()), None)
            # un periodo cerrado se cachea SIEMPRE, incluso sin entradas (ver
            # bug real encontrado en compute_base_adelantos.py: si dependiera
            # de encontrar una factura, un periodo con 0 entradas totales
            # nunca se cachearia y se volveria a pedir para siempre).
            factura_by_period[pk] = algun_entry['charge_info']['legal_document_number'] if algun_entry else 'sin cargos este periodo'
            periodos_cerrados[pk] = factura_by_period[pk]
        mclics = [e for e in by_id.values() if e['marketplace_info']['marketplace'] == 'MCLICS']
        for e in mclics:
            day = e['charge_info']['creation_date_time'][:10]
            if fecha_desde <= day <= fecha_hasta:
                costo_by_day[day] += e['charge_info']['detail_amount']
        print(f'  {len(mclics)} entradas MCLICS en el periodo -- factura: {factura_by_period[pk]}')

    # dias cuyo periodo se pidio esta corrida (abierto o recien cerrado) --
    # incluye dias sin entradas MCLICS ese dia (costo $0 real, no "no chequeado")
    dias_con_costo_fresco = set()
    d = d0
    while d <= d1:
        iso = d.isoformat()
        if billing_period_for_date(iso) in periodos_pedidos_ahora:
            dias_con_costo_fresco.add(iso)
        d = date.fromordinal(d.toordinal() + 1)

    # ---- Ventas atribuidas / impresiones / clicks: API de Ads, sumado por dia ----
    # Cache agresivo: solo se pide el tramo posterior al watermark guardado.
    ads_checked_hasta = cache_state.get('ads_checked_hasta')
    ads_fetch_desde = fecha_desde
    if ads_checked_hasta and ads_checked_hasta >= fecha_desde:
        siguiente = date.fromisoformat(ads_checked_hasta)
        siguiente = date.fromordinal(siguiente.toordinal() + 1)
        ads_fetch_desde = siguiente.isoformat()

    ventas_by_day = defaultdict(float)
    impresiones_by_day = defaultdict(int)
    clicks_by_day = defaultdict(int)
    campaign_ids_total = set()
    if ads_fetch_desde <= fecha_hasta:
        advertiser_id = get_advertiser_id()
        base_url = f'https://api.mercadolibre.com/marketplace/advertising/{SITE_ID}/advertisers/{advertiser_id}/product_ads/campaigns/search'
        af0, af1 = date.fromisoformat(ads_fetch_desde), date.fromisoformat(fecha_hasta)
        for chunk_desde, chunk_hasta in chunks_90d(af0, af1):
            campanias = get(base_url, params={'date_from': chunk_desde, 'date_to': chunk_hasta, 'metrics': 'clicks', 'limit': 100}, ads=True)
            campaign_ids = [c['id'] for c in campanias['results']]
            campaign_ids_total.update(campaign_ids)
            for cid in campaign_ids:
                dd = get(base_url, params={
                    'date_from': chunk_desde, 'date_to': chunk_hasta,
                    'metrics': 'clicks,prints,total_amount',
                    'aggregation_type': 'daily', 'limit': 200,
                    'filters[campaign_ids]': cid,
                }, ads=True)
                for row in dd.get('results', []):
                    day = row['date']
                    ventas_by_day[day] += row.get('total_amount', 0.0)
                    impresiones_by_day[day] += row.get('prints', 0)
                    clicks_by_day[day] += row.get('clicks', 0)
        print(f'{len(campaign_ids_total)} campanias encontradas ({ads_fetch_desde}..{fecha_hasta})')
        cache_state['ads_checked_hasta'] = fecha_hasta
    else:
        print(f'Ads API: rango {fecha_desde}..{fecha_hasta} ya chequeado (watermark {ads_checked_hasta}) -- no se vuelve a pedir')

    # ---- merge sobre lo existente ----
    dias_ads_frescos = set(ventas_by_day) | set(impresiones_by_day) | set(clicks_by_day)
    if ads_fetch_desde <= fecha_hasta:
        d = date.fromisoformat(ads_fetch_desde)
        while d <= date.fromisoformat(fecha_hasta):
            dias_ads_frescos.add(d.isoformat())
            d = date.fromordinal(d.toordinal() + 1)

    dias_a_tocar = dias_con_costo_fresco | dias_ads_frescos
    for day in dias_a_tocar:
        base = dict(existing.get(day, {'fecha': day, 'factura': 'pendiente fc', 'costo_s': 0, 'costo_c': 0, 'ventas_s': 0, 'ventas_c': 0, 'impresiones': 0, 'clicks': 0}))
        if day in dias_con_costo_fresco:
            costo_c = costo_by_day.get(day, 0.0)
            base['costo_s'] = round(costo_c / IVA, 2)
            base['costo_c'] = round(costo_c, 2)
            base['factura'] = factura_by_period.get(billing_period_for_date(day), base.get('factura', 'pendiente fc'))
        if day in dias_ads_frescos:
            ventas_c = ventas_by_day.get(day, 0.0)
            base['ventas_s'] = round(ventas_c / IVA, 2)
            base['ventas_c'] = round(ventas_c, 2)
            base['impresiones'] = impresiones_by_day.get(day, 0)
            base['clicks'] = clicks_by_day.get(day, 0)
        existing[day] = base

    registros = [r for r in existing.values() if r['costo_c'] or r['ventas_c'] or r['impresiones'] or r['clicks']]
    registros.sort(key=lambda r: r['fecha'])

    json.dump(registros, open('base_ads.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    cache_state['periodos_cerrados'] = periodos_cerrados
    json.dump(cache_state, open(CACHE_STATE_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Guardado base_ads.json ({len(registros)} dias) -- {len(periodos_cerrados)} periodos cacheados como cerrados')
