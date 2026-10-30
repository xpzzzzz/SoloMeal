import asyncio
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.receipt_recognition import ReceiptRecognizer
from app.services.receipt_rules import extract_fields


def lines(*values, score=.99):
    return [{'text': value, 'confidence': score, 'order': index,
             'box': [[0, index * 50], [700, index * 50], [700, index * 50 + 30], [0, index * 50 + 30]]}
            for index, value in enumerate(values)]


class OCR:
    def __init__(self, result=None, broken=False):
        self.result, self.broken = result, broken
    def extract(self, _):
        if self.broken:
            raise ImportError('private runtime path')
        return self.result


class VLM:
    is_mock = True
    def __init__(self, result=None, broken=False):
        self.calls, self.result, self.broken = 0, result, broken
    async def parse(self, *_):
        self.calls += 1
        if self.broken:
            raise TimeoutError('private provider response')
        return self.result


def test_rules_explicit_total_packages_units_and_per_fruit_note():
    parsed, evidence, issues = extract_fields(lines('购买日期2026-10-15',
        '牛奶250ml/盒 ×2 小计6.50', '鸡蛋(3颗装) ×2盒 小计8.00',
        '苹果750g(单果100g+) 小计9.00', '包菜2kg ×1 小计4.00'), .85)
    assert parsed['purchased_on'] == '2026-10-15'
    assert [item['name'] for item in parsed['items']] == ['牛奶', '鸡蛋(3颗装)', '苹果', '包菜']
    assert [Decimal(item['quantity']) for item in parsed['items']] == [500, 6, 750, 2000]
    assert [item['unit'] for item in parsed['items']] == ['ml', 'piece', 'g', 'g']
    assert issues == [] and all(item['uncertain'] for item in parsed['items'])
    assert evidence[0]['package_spec'] == '250ml' and evidence[0]['purchase_count'] == '2'


@pytest.mark.parametrize('text', ['[不定重]土豆约2kg/袋 ×2 小计7.00',
                                 '鸡蛋(3颗装) 小计6.00', '苹果500-600g 小计8.00',
                                 '鸡蛋0.5个 小计1.00'])
def test_high_confidence_never_resolves_ambiguous_quantity(text):
    parsed, _, issues = extract_fields(lines(text, score=.9999), .85)
    assert parsed['items'][0]['quantity'] is None and parsed['items'][0]['unit'] is None
    assert issues and parsed['items'][0]['uncertain']


def test_hybrid_clear_receipt_does_not_call_vlm():
    vlm = VLM()
    recognizer = ReceiptRecognizer(Settings(_env_file=None), ocr=OCR(lines('牛奶250ml/盒 ×2 小计6.50')), vlm=vlm)
    result = asyncio.run(recognizer.parse_mode(b'image', 'image/png', 'hybrid'))
    assert vlm.calls == 0 and result.metadata['path'] == ['ocr']
    assert result.parsed['items'][0]['quantity'] == '500'


def test_low_confidence_uses_assistance_and_conflicting_quantity_stays_unknown():
    vlm = VLM({'items': [{'name': '牛奶', 'quantity': '750', 'unit': 'ml', 'amount': '6.50'}]})
    result = asyncio.run(ReceiptRecognizer(Settings(_env_file=None),
        ocr=OCR(lines('牛奶250ml/盒 ×2 小计6.50', score=.4)), vlm=vlm).parse_mode(b'image', 'image/png', 'hybrid'))
    assert vlm.calls == 1 and result.parsed['items'][0]['quantity'] is None
    assert result.metadata['conflicts'][0]['field'] == 'quantity'
    assert result.metadata['ocr_lines'][0]['box'] and result.metadata['ocr_lines'][0]['confidence'] == .4


def test_vlm_cannot_replace_approximate_weight_with_a_claimed_number():
    vlm = VLM({'items': [{'name': '[不定重]土豆约2kg', 'quantity': '2000', 'unit': 'g', 'amount': '7.00'}]})
    result = asyncio.run(ReceiptRecognizer(Settings(_env_file=None),
        ocr=OCR(lines('[不定重]土豆约2kg/袋 ×2 小计7.00')), vlm=vlm).parse_mode(b'image', 'image/png', 'hybrid'))
    assert result.parsed['items'][0]['quantity'] is None
    assert result.metadata['conflicts'][0]['reason'] == 'unresolved_quantity'


def test_modes_and_unavailable_ocr_fallback_are_explicit():
    vlm = VLM({'items': [{'name': 'egg'}]})
    recognizer = ReceiptRecognizer(Settings(_env_file=None), ocr=OCR(broken=True), vlm=vlm)
    result = asyncio.run(recognizer.parse_mode(b'image', 'image/png', 'hybrid'))
    assert result.metadata['path'] == ['vlm'] and 'ocr_unavailable' in result.metadata['issues']
    with pytest.raises(AppError):
        asyncio.run(recognizer.parse_mode(b'image', 'image/png', 'ocr_only'))
    assert vlm.calls == 1
    result = asyncio.run(recognizer.parse_mode(b'image', 'image/png', 'vlm_only'))
    assert vlm.calls == 2 and result.metadata['ocr_lines'] == []


def test_vlm_failure_is_not_success_and_ocr_evidence_is_retained():
    recognizer = ReceiptRecognizer(Settings(_env_file=None), ocr=OCR(lines('牛奶250ml/盒 ×2', score=.4)), vlm=VLM(broken=True))
    with pytest.raises(AppError):
        asyncio.run(recognizer.parse_mode(b'image', 'image/png', 'hybrid'))
    assert recognizer.last_metadata['ocr_lines'][0]['text'] == '牛奶250ml/盒 ×2'


def test_vlm_invalid_schema_is_rejected():
    vlm = VLM({'user_id': 'foreign', 'items': [{'name': 'egg', 'quantity': 'NaN'}]})
    with pytest.raises(ValueError):
        asyncio.run(ReceiptRecognizer(Settings(_env_file=None), vlm=vlm).parse_mode(b'image', 'image/png', 'vlm_only'))


def test_equivalent_mass_units_are_not_a_conflict_but_amount_conflicts_remain_unknown():
    vlm = VLM({'items': [{'name': '包菜', 'quantity': '2', 'unit': 'kg', 'amount': '5.00'}]})
    result = asyncio.run(ReceiptRecognizer(Settings(_env_file=None),
        ocr=OCR(lines('包菜2kg ×1 小计4.00', score=.4)), vlm=vlm).parse_mode(b'image', 'image/png', 'hybrid'))
    assert result.parsed['items'][0]['quantity'] == '2000'
    assert result.parsed['items'][0]['amount'] is None
    assert [r['field'] for r in result.metadata['conflicts']] == ['amount']


def test_negative_weight_is_not_turnable_into_a_positive_purchase():
    result, _, issues = extract_fields(lines('苹果-1kg 小计2.00'), .85)
    assert result['items'][0]['quantity'] is None and 'refund_or_negative' in issues


def test_both_unavailable_fails_with_manual_entry_instead_of_empty_success():
    from app.services.receipt_parser import UnconfiguredParser
    recognizer = ReceiptRecognizer(Settings(_env_file=None), ocr=OCR(broken=True), vlm=UnconfiguredParser())
    with pytest.raises(AppError):
        asyncio.run(recognizer.parse_mode(b'image', 'image/png', 'hybrid'))


def test_vlm_fractional_piece_count_fails_original_business_validation():
    vlm = VLM({'items': [{'name': 'egg', 'quantity': '0.5', 'unit': 'piece'}]})
    with pytest.raises(AppError) as error:
        asyncio.run(ReceiptRecognizer(Settings(_env_file=None), vlm=vlm).parse_mode(b'image', 'image/png', 'vlm_only'))
    assert error.value.code == 'UNIT_AMBIGUOUS'


def test_name_only_row_is_kept_and_triggers_assistance_instead_of_silent_omission():
    parsed, _, issues = extract_fields(lines('大米500g 小计3.00', '未知商品'), .85)
    assert len(parsed['items']) == 2
    assert parsed['items'][1]['name'] == '未知商品'
    assert parsed['items'][1]['quantity'] is None and parsed['items'][1]['amount'] is None
    assert {'quantity_missing', 'amount_missing'} <= set(issues)
