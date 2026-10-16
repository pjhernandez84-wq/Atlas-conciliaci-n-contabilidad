import unittest
from app.reconciliation import preview, parse_csv

CSV = 'fecha;concepto;importe\n01/01/2026;Ingreso;100,00\n02/01/2026;Pago;-30,00\n'
BALANCES = dict(banco_inicial='10,00', banco_final='80,00', mayor_inicial='10,00', mayor_final='80,00')


class ReconciliationTests(unittest.TestCase):
    def test_no_automatic_approval_and_balances(self):
        result = preview(CSV, CSV, BALANCES)
        self.assertFalse(result['definitiva'])
        self.assertEqual(result['controles']['banco']['descuadre'], '0.00')
        self.assertEqual(len(result['banco']), 2)
        self.assertEqual(result['banco'][0]['estado'], 'propuesta pendiente de revisión')

    def test_duplicates_preserved_and_ambiguous(self):
        repeated = CSV + '01/01/2026;Ingreso;100,00\n'
        result = preview(repeated, CSV, BALANCES)
        self.assertEqual(len(result['banco']), 3)
        self.assertTrue(result['banco'][0]['posible_duplicado'])
        self.assertEqual(result['banco'][0]['estado'], 'ambigua')
        self.assertEqual(len(result['mayor'][0]['candidatos']), 2)

    def test_sign_and_month_boundaries(self):
        for altered in [CSV.replace('-30,00', '30,00'), CSV.replace('02/01', '02/02')]:
            self.assertEqual(preview(CSV, altered, BALANCES)['banco'][1]['candidatos'], [])

    def test_different_date_retained_and_reason_shown(self):
        result = preview(CSV, CSV.replace('02/01', '31/01'), BALANCES)
        row = result['banco'][1]
        self.assertEqual(row['fecha'], '2026-01-02')
        self.assertEqual(row['detalle_candidatos'][0]['fecha'], '2026-01-31')
        self.assertIn('fecha distinta', row['detalle_candidatos'][0]['motivo'])
        self.assertFalse(result['definitiva'])

    def test_amount_only_not_presented_as_supported(self):
        result = preview(CSV, CSV.replace('Pago', 'Otro'), BALANCES)
        self.assertEqual(result['banco'][1]['estado'], 'solo importe: revisar concepto')

    def test_competing_claims_ambiguous_on_both_sides(self):
        repeated = CSV + '03/01/2026;Otro;-30,00\n'
        result = preview(repeated, CSV, BALANCES)
        self.assertEqual(result['banco'][1]['estado'], 'ambigua')
        self.assertEqual(result['mayor'][1]['estado'], 'ambigua')

    def test_invalid_rows_fail_whole_import(self):
        for invalid in [CSV+'03/01/2026;Error;1.20\n', CSV+'03/01/2026;Error\n', CSV+'31/02/2026;Error;1,00\n']:
            with self.assertRaises(ValueError):
                parse_csv(invalid, 'banco')

    def test_grouped_receipts_stay_unmatched(self):
        ledger = 'fecha;concepto;importe\n01/01/2026;Ingreso;40,00\n01/01/2026;Ingreso;60,00\n'
        result = preview(CSV, ledger, BALANCES)
        self.assertEqual(result['banco'][0]['estado'], 'sin candidato individual')
        self.assertEqual(len(result['mayor']), 2)

    def test_original_concept_retained(self):
        text = 'fecha;concepto;importe\n01/01/2026;"Ingreso; cliente";1.234,56\n'
        row = parse_csv(text, 'banco')[0]
        self.assertEqual(row['original']['importe'], '1.234,56')
        self.assertEqual(row['concepto'], 'Ingreso; cliente')
