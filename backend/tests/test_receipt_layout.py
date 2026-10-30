"""Receipt layout and merge regressions, using synthetic rows without private text."""
import asyncio
from decimal import Decimal

import pytest
from app.core.config import Settings
from app.services.receipt_recognition import ReceiptRecognizer
from app.services.receipt_rules import extract_fields


def rows(*values):
    result = []
    for y, cells in enumerate(values):
        for x, text in cells:
            result.append({'text': text, 'confidence': .99, 'order': len(result),
                           'box': [[x, y*50], [x+120, y*50], [x+120, y*50+25], [x, y*50+25]]})
    return result


def sku_table(*products):
    body = [((0, '销售单'),), ((0, '2026-10-15'),),
            ((0, '货号/品名/数量'), (600, '金额/折扣'))]
    for i, (name, purchase, amount) in enumerate(products):
        body += [((0, str(10000000+i)),), ((0, name),),
                 ((0, purchase), (650, amount)), ((650, '-1.23'),)]
    body += [((0, '商品合计'), (650, '99.99')), ((0, '支付明细'),), ((0, '其他无关文字'),)]
    return rows(*body)


def test_numbered_names_weight_and_glued_price_columns_form_one_product():
    data = rows(((0, '随机门店'),), ((0, '购买日期2026-10-15'),),
                ((0, '品名'), (220, '数量'), (500, '单价'), (700, '小计')),
                ((0, '1.西兰花'),), ((220, '0.625kg'), (500, '12.408.00')),
                ((0, '2.红薯'),), ((220, '0.750kg'), (500, '4.00'), (700, '3.00')),
                ((0, '原价：11.00'),), ((0, '会员姓名：不应成为商品'),))
    parsed, fields, issues = extract_fields(data, .85)
    assert parsed['purchased_on'] == '2026-10-15'
    assert [x['name'] for x in parsed['items']] == ['西兰花', '红薯']
    assert [Decimal(x['quantity']) for x in parsed['items']] == [625, 750]
    assert [Decimal(x['amount']) for x in parsed['items']] == [8, 3]
    assert all(len(x['line_orders']) >= 3 for x in fields) and not issues


@pytest.mark.parametrize('purchase', ['×3（4.00元/盒）', 'x3(4.00元/盒)', '3（4.00元/盒）'])
def test_sku_specification_and_purchase_count_are_assembled_without_using_discount(purchase):
    parsed, fields, issues = extract_fields(sku_table(('饮料250ml/盒', purchase, '12.00')), .85)
    assert len(parsed['items']) == 1
    item = parsed['items'][0]
    assert item['name'] == '饮料' and Decimal(item['quantity']) == 750 and item['unit'] == 'ml'
    assert Decimal(item['amount']) == 12 and fields[0]['purchase_count'] == '3'
    assert not issues


def test_long_approximate_specification_overlapping_price_column_is_retained():
    data = rows(((0, '货号/品名/数量'), (500, '金额/折扣')),
                ((0, 'A12345678'),), ((0, '[不定重]有机蔬菜'), (550, '约350g')),
                ((0, '×2(3.00元/包)'), (650, '6.00')),
                ((650, '0.80'),), ((0, '订单总额'), (650, '5.20')))
    parsed, _, issues = extract_fields(data, .85)
    assert len(parsed['items']) == 1
    assert parsed['items'][0]['name'] == '[不定重]有机蔬菜 约350g'
    assert parsed['items'][0]['quantity'] is None and parsed['items'][0]['unit'] is None
    assert parsed['items'][0]['amount'] == '6.00' and 'approximate_or_range' in issues


def test_explicit_amount_in_single_ocr_box_is_not_added_to_product_name():
    parsed, _, _ = extract_fields(rows(((0, '商品名称 金额'),),
        ((0, '燕麦500g 小计9.00'),), ((0, '合计9.00'),)), .85)
    assert parsed['items'] == [{'name': '燕麦', 'quantity': '500', 'unit': 'g',
                                'amount': '9.00', 'uncertain': True, 'excluded': False}]


def test_table_missing_purchase_count_cannot_treat_package_size_as_total():
    data = rows(((0, '货号/品名/数量'), (600, '金额/折扣')),
                ((0, '123456789'),), ((0, '饮料250ml/盒'), (650, '4.00')),
                ((0, '商品合计'), (650, '4.00')))
    parsed, _, issues = extract_fields(data, .85)
    assert parsed['items'][0]['quantity'] is None and 'package_count_unknown' in issues


class OCR:
    def __init__(self, value):
        self.value = value

    def extract(self, _):
        return self.value


class VLM:
    is_mock = True

    def __init__(self, items):
        self.items = items

    async def parse(self, *_):
        return {'items': self.items}


def hybrid(text, proposals):
    return asyncio.run(ReceiptRecognizer(Settings(_env_file=None),
        ocr=OCR(rows(*[((0, x),) for x in text])), vlm=VLM(proposals)).parse_mode(b'image', 'image/png', 'hybrid'))


def item(name, quantity='500', unit='g', amount='3.00'):
    return {'name': name, 'quantity': quantity, 'unit': unit, 'amount': amount}


@pytest.mark.parametrize('position', [0, 1, 2])
def test_additional_vlm_product_does_not_shift_existing_product_quantities(position):
    proposal = [item('大米'), item('牛奶', '250', 'ml', '2.00')]
    proposal.insert(position, item('鸡蛋', '2', 'piece', '4.00'))
    result = hybrid(['大米500g', '牛奶250ml'], proposal)
    assert [x['name'] for x in result.parsed['items']] == [x['name'] for x in proposal]
    by_name = {x['name']: x for x in result.parsed['items']}
    assert by_name['大米']['quantity'] == '500' and by_name['牛奶']['quantity'] == '250'
    assert by_name['鸡蛋']['unit'] == 'piece' and all(x['uncertain'] for x in result.parsed['items'])
    assert result.metadata['conflicts'][0]['field'] == 'item_count'
    assert len(result.metadata['fields']) == 3
    assert [x['item_index'] for x in result.metadata['fields']] == [0, 1, 2]


def test_product_missing_from_vlm_is_retained_without_cross_assigning_neighbor_fields():
    result = hybrid(['大米500g', '玉米200g', '牛奶250ml'],
                    [item('大米'), item('牛奶', '250', 'ml', '2.00')])
    assert [x['name'] for x in result.parsed['items']] == ['大米', '玉米', '牛奶']
    assert result.parsed['items'][1]['quantity'] == '200'
    assert result.parsed['items'][1]['amount'] is None
    assert result.parsed['items'][2]['amount'] == '2.00'
    assert result.metadata['fields'][1]['source'] == 'ocr_unmatched'


def test_count_conflict_does_not_bypass_approximate_quantity_protection():
    result = hybrid(['[不定重]土豆约2kg/袋 ×1 小计3.00', '牛奶250ml'],
                    [item('鸡蛋', '2', 'piece'), item('土豆', '2000'), item('牛奶', '250', 'ml')])
    potatoes = next(x for x in result.parsed['items'] if '土豆' in x['name'])
    assert potatoes['quantity'] is None and potatoes['unit'] is None
    assert any(x.get('reason') == 'unresolved_quantity' for x in result.metadata['conflicts'])


def test_unmatched_ambiguous_ocr_row_cannot_be_silently_replaced_by_numeric_alias():
    result = hybrid(['[不定重]土豆约2kg 小计3.00'], [item('洋芋', '2000')])
    assert len(result.parsed['items']) == 2
    assert all(x['quantity'] is None for x in result.parsed['items'])


def test_name_correction_keeps_numeric_conflicts_unknown_and_preserves_proposal():
    result = hybrid(['三色彩版600g', '牛奶250ml'],
                    [item('三色彩椒', '600'), item('牛奶', '750', 'ml')])
    assert [x['name'] for x in result.parsed['items']] == ['三色彩椒', '牛奶']
    assert result.parsed['items'][0]['quantity'] == '600'
    assert result.parsed['items'][1]['quantity'] is None
    assert result.metadata['vlm_proposal']['items'][1]['quantity'] == '750'


def test_repeated_product_names_remain_separate_and_keep_numeric_conflicts_visible():
    result = hybrid(['苹果500g', '苹果750g'], [item('苹果', '500'), item('苹果', '700')])
    assert len(result.parsed['items']) == 2
    assert result.parsed['items'][0]['quantity'] == '500'
    assert result.parsed['items'][1]['quantity'] is None


def test_digit_led_brand_is_not_reduced_to_empty_identity_and_duplicated():
    result = hybrid(['7UP250ml'], [item('7UP', '250', 'ml')])
    assert len(result.parsed['items']) == 1 and result.parsed['items'][0]['quantity'] == '250'


def test_distinct_high_confidence_short_names_are_not_fuzzily_joined():
    result = hybrid(['牛奶250ml'], [item('奶粉', '250', 'g')])
    assert len(result.parsed['items']) == 2
    assert not any(x['field'] == 'quantity' for x in result.metadata['conflicts'])
