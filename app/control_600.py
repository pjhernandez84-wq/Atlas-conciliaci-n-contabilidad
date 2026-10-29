"""Control de signos de compras. Lee CSV; nunca modifica los datos originales.

Uso: python -m app.control_600 extracto.csv --empresa Jabardo --mes 2024-04
Importes: 1234.56 o "1.234,56". CSV UTF-8, delimitador coma o punto y coma.
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date
from decimal import Decimal


FIELDS = {'id', 'empresa', 'fecha', 'cuenta', 'proveedor', 'asiento', 'concepto', 'debe', 'haber'}


def importe(value):
    value = value.strip()
    if not value:
        return Decimal('0')
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d{3})*,\d{1,2}|\d+(?:\.\d{1,2})?)', value):
        raise ValueError(f'Importe no válido: {value!r}')
    if ',' in value:
        value = value.replace('.', '').replace(',', '.')
    return Decimal(value)


def comprobar(rows, empresa, mes):
    date.fromisoformat(mes + '-01')
    if not re.fullmatch(r'\d{4}-\d{2}', mes) or not empresa.strip():
        raise ValueError('Empresa y mes YYYY-MM obligatorios')
    groups = defaultdict(lambda: {'debe': Decimal(0), 'haber': Decimal(0), 'apuntes': 0})
    incidencias, ids = [], set()
    leidos = seleccionados = 0
    for line, raw in enumerate(rows, 2):
        leidos += 1
        if not FIELDS.issubset(raw) or None in raw or any(raw[k] is None for k in FIELDS):
            raise ValueError(f'Fila {line}: faltan campos o sobran columnas')
        row = {k: raw[k].strip() for k in FIELDS}
        if any(not row[k] for k in ('id', 'empresa', 'fecha', 'cuenta', 'asiento')):
            raise ValueError(f'Fila {line}: identificadores obligatorios vacíos')
        date.fromisoformat(row['fecha'])
        if not re.fullmatch(r'\d{3,}', row['cuenta']):
            raise ValueError(f'Fila {line}: cuenta no válida; importar como texto sin puntos')
        key_id = (row['empresa'], row['id'])
        if key_id in ids:
            raise ValueError(f'Fila {line}: id repetido {key_id}; no se descarta automáticamente')
        ids.add(key_id)
        debe, haber = importe(row['debe']), importe(row['haber'])
        if row['empresa'] != empresa or row['fecha'][:7] != mes or not row['cuenta'].startswith('600'):
            continue
        seleccionados += 1
        key = (row['cuenta'], row['proveedor'])
        group = groups[key]
        group['debe'] += debe
        group['haber'] += haber
        group['apuntes'] += 1
        motivos = []
        if haber != 0:
            motivos.append('MOVIMIENTO_EN_HABER_600')
        if debe < 0 or haber < 0:
            motivos.append('IMPORTE_NEGATIVO_REVISAR_SIGNO')
        if debe != 0 and haber != 0:
            motivos.append('DEBE_Y_HABER_SIMULTANEOS')
        if not row['proveedor']:
            motivos.append('PROVEEDOR_SIN_IDENTIFICAR')
        if motivos:
            incidencias.append({**row, 'debe': str(debe), 'haber': str(haber),
                                'neto': str(debe - haber), 'motivos': motivos,
                                'estado': 'pendiente_revision',
                                'causa': 'Sin determinar: revisar asiento completo y documento'})
    resumen = [{'cuenta': key[0], 'proveedor': key[1], 'apuntes': g['apuntes'],
                'debe': str(g['debe']), 'haber': str(g['haber']),
                'neto': str(g['debe'] - g['haber'])} for key, g in sorted(groups.items())]
    total_debe = sum((g['debe'] for g in groups.values()), Decimal(0))
    total_haber = sum((g['haber'] for g in groups.values()), Decimal(0))
    return {'empresa': empresa, 'mes': mes, 'filas_leidas': leidos,
            'apuntes_600': seleccionados, 'incidencias': incidencias,
            'resumen_por_subcuenta_proveedor': resumen,
            'totales': {'debe': str(total_debe), 'haber': str(total_haber),
                        'neto': str(total_debe - total_haber)},
            'estado': 'sin_datos' if not seleccionados else 'pendiente_revision' if incidencias else 'sin_alertas_de_signo',
            'alcance': 'Control de signos; no confirma conciliacion, causa ni ajuste. No incluye otras cuentas del subgrupo 60.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv')
    parser.add_argument('--empresa', required=True)
    parser.add_argument('--mes', required=True)
    args = parser.parse_args()
    try:
        with open(args.csv, encoding='utf-8-sig', newline='') as source:
            sample = source.read(8192)
            source.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=';,')
            reader = csv.DictReader(source, dialect=dialect)
            if not FIELDS.issubset(reader.fieldnames or []) or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError('Cabecera obligatoria y única: ' + ', '.join(sorted(FIELDS)))
            result = comprobar(reader, args.empresa, args.mes)
    except (ValueError, OSError, csv.Error) as exc:
        parser.exit(2, f'Control no completado: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
