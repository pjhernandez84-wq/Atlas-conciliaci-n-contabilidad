"""Strict CSV preview: every source record is retained, never auto-approved."""
import csv
import io
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation


def amount(value):
    value = value.strip()
    if not re.fullmatch(r'-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?', value):
        raise ValueError('Importe inválido: use formato español, por ejemplo -1.234,56')
    try:
        return Decimal(value.replace('.', '').replace(',', '.'))
    except InvalidOperation as exc:
        raise ValueError('Importe inválido') from exc


def parse_csv(text, source):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), delimiter=';', strict=True)
    required = ['fecha', 'concepto', 'importe']
    if reader.fieldnames != required:
        raise ValueError('Cabecera requerida: fecha;concepto;importe')
    rows = []
    for number, row in enumerate(reader, 2):
        if len(rows) >= 5000:
            raise ValueError('Máximo 5.000 movimientos por archivo')
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f'{source}, registro {number}: columnas incompletas o sobrantes')
        try:
            date = datetime.strptime(row['fecha'].strip(), '%d/%m/%Y').date().isoformat()
            value = amount(row['importe'])
        except ValueError as exc:
            raise ValueError(f'{source}, registro {number}: {exc}') from exc
        if not row['concepto'].strip():
            raise ValueError(f'{source}, registro {number}: falta concepto')
        rows.append({'id': f'{source}-{number}', 'registro': number, 'fecha': date,
                     'concepto': row['concepto'], 'importe': str(value), 'original': row,
                     'estado': 'pendiente de revisión', 'candidatos': []})
    if not rows:
        raise ValueError(f'{source}: archivo sin movimientos')
    counts = Counter((r['fecha'], r['concepto'].strip().casefold(), r['importe']) for r in rows)
    for row in rows:
        row['posible_duplicado'] = counts[(row['fecha'], row['concepto'].strip().casefold(), row['importe'])] > 1
    return rows


def preview(bank_text, ledger_text, balances):
    bank, ledger = parse_csv(bank_text, 'banco'), parse_csv(ledger_text, 'mayor')
    # Candidate lookup includes date, concept, signed amount. No record is consumed.
    def key(row):
        return row['fecha'], row['concepto'].strip().casefold(), Decimal(row['importe'])
    for source, other in [(bank, ledger), (ledger, bank)]:
        index = {}
        for row in other:
            index.setdefault(key(row), []).append(row['id'])
        for row in source:
            row['candidatos'] = index.get(key(row), [])
            row['estado'] = ('coincidencia propuesta' if len(row['candidatos']) == 1 and not row['posible_duplicado']
                             else 'ambigua' if row['candidatos'] else 'sin pareja')
    controls = {}
    for name, rows in [('banco', bank), ('mayor', ledger)]:
        opening, closing = amount(balances[name + '_inicial']), amount(balances[name + '_final'])
        total = sum((Decimal(r['importe']) for r in rows), Decimal(0))
        controls[name] = {'movimientos': len(rows), 'inicial': str(opening), 'final': str(closing),
                          'suma': str(total), 'descuadre': str(opening + total - closing)}
    controls['diferencia_inicial'] = str(amount(balances['banco_inicial']) - amount(balances['mayor_inicial']))
    controls['diferencia_final'] = str(amount(balances['banco_final']) - amount(balances['mayor_final']))
    return {'banco': bank, 'mayor': ledger, 'controles': controls, 'definitiva': False,
            'aviso': 'Revisión pendiente de todos los movimientos, duplicados y cobros agrupados. Ninguna propuesta queda conciliada automáticamente.'}
