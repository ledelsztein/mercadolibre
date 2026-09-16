"""
Arma la tabla "balance_salida": si Lucas vendiera TODO el stock activo hoy,
con cuanta plata le queda despues de descontar los gastos fijos de pago
unico pendientes y las deudas pendientes de pago a la fecha.

Balance de salida = Total Stock Recibido
                     - Autonomos (ultimo pago cargado)
                     - IIBB (ultimo pago cargado)
                     - Percepciones y Retenciones (ultimo periodo de base_impositiva)
                     - Deudas pendientes a la fecha (tab "deudas_pendientes" del Sheet)

Fuentes (pedido de Lucas, 2026-09-16):
- Total Stock Recibido: suma de "recibis_total" (Recibis por unidad x stock)
  de la fecha mas reciente en publicaciones_recibis.json. Requiere haber
  corrido compute_publicaciones_recibis.py el mismo dia antes que esto.
- Total Stock Valorizado: solo de referencia (no resta del balance) -- suma
  de "importe" de la fecha mas reciente en stock_valorizado.json.
- Autonomos / IIBB: de base_informativa.json, categoria "Autónomos"/"IIBB",
  se toma la fila con la fecha MAS RECIENTE de cada una (es un pago unico,
  no se suman todos los pagos historicos).
- Percepciones y Retenciones: de base_impositiva.json, se toma el
  period_key mas reciente y se suman TODAS las filas de ese periodo
  (son varias lineas por grupo/categoria/jurisdiccion).
- Deudas pendientes: a diferencia de todas las demas tablas de este
  pipeline, "deudas_pendientes" es una pestaña que Lucas carga A MANO
  directo en el Google Sheet (no hay JSON local que la refleje -- el
  Sheet ES la fuente). Columnas: Fecha de la deuda | Concepto | Monto |
  Fecha de pago (vacio = todavia pendiente). Una deuda cuenta como
  pendiente a la fecha F si: fecha_deuda <= F Y (fecha_pago vacia O
  fecha_pago > F). Ejemplo real que motivo esto: un cheque emitido el
  dia X y pagado el dia X+4 cuenta como deuda pendiente solo en esos 4
  dias intermedios, no antes ni despues.

Uso:
    python compute_balance_salida.py

Mergea sobre balance_salida.json existente por fecha -- si se corre mas de
una vez el mismo dia, reemplaza la foto de ese dia en vez de duplicarla.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()


def excel_serial_a_fecha(serial):
    return (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()


def parsear_fecha(valor):
    """Una celda de fecha puede volver como texto ISO o como numero de
    serie de Excel/Sheets, segun como Lucas la haya tipeado. None si esta
    vacia."""
    if valor is None or valor == '':
        return None
    if isinstance(valor, (int, float)):
        return excel_serial_a_fecha(valor)
    valor = str(valor).strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date().isoformat()
    except ValueError:
        pass
    for fmt in ('%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(valor, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f'No se pudo interpretar la fecha: {valor!r}')


def parsear_monto(valor):
    if valor is None or valor == '':
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    limpio = str(valor).replace('$', '').replace('.', '').replace(',', '.').strip()
    return float(limpio) if limpio else 0.0


def deudas_pendientes_a_fecha(sheets, spreadsheet_id, fecha):
    result = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range='deudas_pendientes!A2:D1000',
    ).execute()
    filas = result.get('values', [])
    total = 0.0
    detalle = []
    for fila in filas:
        fila = fila + [''] * (4 - len(fila))
        fecha_deuda_raw, concepto, monto_raw, fecha_pago_raw = fila[:4]
        fecha_deuda = parsear_fecha(fecha_deuda_raw)
        fecha_pago = parsear_fecha(fecha_pago_raw)
        if not fecha_deuda:
            continue
        if fecha_deuda > fecha:
            continue
        if fecha_pago and fecha_pago <= fecha:
            continue
        monto = parsear_monto(monto_raw)
        total += monto
        detalle.append({'concepto': concepto, 'monto': monto, 'fecha_deuda': fecha_deuda, 'fecha_pago': fecha_pago})
    return total, detalle


if __name__ == '__main__':
    fecha = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()

    creds = Credentials.from_authorized_user_file('google_token.json')
    sheets = build('sheets', 'v4', credentials=creds)
    spreadsheet_id = open('sheet_id.txt').read().strip()

    publicaciones = json.load(open('publicaciones_recibis.json', encoding='utf-8'))
    fechas_pub = sorted(set(r['fecha'] for r in publicaciones))
    if not fechas_pub:
        raise RuntimeError('publicaciones_recibis.json esta vacio -- correr compute_publicaciones_recibis.py primero')
    fecha_pub = fechas_pub[-1]
    if fecha_pub != fecha:
        print(f'ADVERTENCIA: la foto mas reciente de publicaciones_recibis es del {fecha_pub}, no de hoy ({fecha}) -- '
              f'se usa igual, pero convendria correr compute_publicaciones_recibis.py antes.')
    total_stock_recibido = sum(r['recibis_total'] for r in publicaciones if r['fecha'] == fecha_pub)

    total_stock_valorizado = 0.0
    if os.path.exists('stock_valorizado.json'):
        stock = json.load(open('stock_valorizado.json', encoding='utf-8'))
        fechas_stock = sorted(set(r['fecha'] for r in stock))
        if fechas_stock:
            if fechas_stock[-1] != fecha:
                print(f'ADVERTENCIA: la foto mas reciente de stock_valorizado es del {fechas_stock[-1]}, no de hoy ({fecha}) -- '
                      f'"Total Stock Valorizado" queda desactualizado (es solo referencia, no afecta el balance).')
            total_stock_valorizado = sum(r['importe'] for r in stock if r['fecha'] == fechas_stock[-1])

    informativa = json.load(open('base_informativa.json', encoding='utf-8'))
    autonomos_rows = sorted([r for r in informativa if r['categoria'] == 'Autónomos'], key=lambda r: r['fecha'])
    iibb_rows = sorted([r for r in informativa if r['categoria'] == 'IIBB'], key=lambda r: r['fecha'])
    if not autonomos_rows:
        raise RuntimeError('No hay ninguna fila de "Autónomos" en base_informativa.json')
    if not iibb_rows:
        raise RuntimeError('No hay ninguna fila de "IIBB" en base_informativa.json')
    autonomos = autonomos_rows[-1]['importe_con_iva']
    autonomos_fecha = autonomos_rows[-1]['fecha']
    iibb = iibb_rows[-1]['importe_con_iva']
    iibb_fecha = iibb_rows[-1]['fecha']

    impositiva = json.load(open('base_impositiva.json', encoding='utf-8'))
    periodos = sorted(set(r['period_key'] for r in impositiva))
    if not periodos:
        raise RuntimeError('base_impositiva.json esta vacio')
    ultimo_periodo = periodos[-1]
    percepciones_retenciones = sum(r['importe'] for r in impositiva if r['period_key'] == ultimo_periodo)

    deudas, detalle_deudas = deudas_pendientes_a_fecha(sheets, spreadsheet_id, fecha)

    balance = round(
        total_stock_recibido - autonomos - iibb - percepciones_retenciones - deudas, 2
    )

    registro = {
        'fecha': fecha,
        'total_stock_valorizado': round(total_stock_valorizado, 2),
        'total_stock_recibido': round(total_stock_recibido, 2),
        'autonomos': round(autonomos, 2),
        'autonomos_fecha_pago': autonomos_fecha,
        'iibb': round(iibb, 2),
        'iibb_fecha_pago': iibb_fecha,
        'percepciones_retenciones': round(percepciones_retenciones, 2),
        'percepciones_retenciones_periodo': ultimo_periodo,
        'deudas_pendientes': round(deudas, 2),
        'balance_salida': balance,
    }

    existing = json.load(open('balance_salida.json', encoding='utf-8')) if os.path.exists('balance_salida.json') else []
    existing = [r for r in existing if r['fecha'] != fecha]
    registros = existing + [registro]
    registros.sort(key=lambda r: r['fecha'])
    json.dump(registros, open('balance_salida.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    print(f'{fecha}:')
    print(f'  Total Stock Valorizado (ref.): ${total_stock_valorizado:,.2f}')
    print(f'  Total Stock Recibido:          ${total_stock_recibido:,.2f}')
    print(f'  - Autónomos ({autonomos_fecha}):     ${autonomos:,.2f}')
    print(f'  - IIBB ({iibb_fecha}):           ${iibb:,.2f}')
    print(f'  - Percepciones/Retenciones ({ultimo_periodo}): ${percepciones_retenciones:,.2f}')
    print(f'  - Deudas pendientes ({len(detalle_deudas)} filas): ${deudas:,.2f}')
    print(f'  = BALANCE DE SALIDA: ${balance:,.2f}')
    print('Guardado balance_salida.json')
