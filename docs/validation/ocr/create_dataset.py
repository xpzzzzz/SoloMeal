"""Freeze synthetic receipt images and ground truth before running any recognizer."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CASES = [
    ('clear', ['牛奶250ml/盒 ×2 小计6.50', '苹果750g(单果100g+) 小计9.00'],
     [{'name': '牛奶', 'quantity': '500', 'unit': 'ml', 'amount': '6.50'},
      {'name': '苹果', 'quantity': '750', 'unit': 'g', 'amount': '9.00'}], 0),
    ('blurred', ['牛奶250ml/盒 ×2 小计6.50', '苹果750g 小计9.00'],
     [{'name': '牛奶', 'quantity': '500', 'unit': 'ml', 'amount': '6.50'},
      {'name': '苹果', 'quantity': '750', 'unit': 'g', 'amount': '9.00'}], 2.5),
    ('multipack', ['鸡蛋(3颗装) ×2盒 小计8.00', '大米500g/袋 ×3 小计12.00'],
     [{'name': '鸡蛋(3颗装)', 'quantity': '6', 'unit': 'piece', 'amount': '8.00'},
      {'name': '大米', 'quantity': '1500', 'unit': 'g', 'amount': '12.00'}], 0),
    ('approximate', ['[不定重]土豆约2kg/袋 ×2 小计7.00'],
     [{'name': '[不定重]土豆约2kg', 'quantity': None, 'unit': None, 'amount': '7.00'}], 0),
    ('missing_amount', ['大米500g/袋 ×1'],
     [{'name': '大米', 'quantity': '500', 'unit': 'g', 'amount': None}], 0),
    ('unknown_package', ['牛奶250ml/盒 小计6.50'],
     [{'name': '牛奶', 'quantity': None, 'unit': None, 'amount': '6.50'}], 0),
]


def create(directory, font_path):
    if directory.exists():
        raise RuntimeError('Dataset already exists; refusing to change ground truth')
    directory.mkdir(parents=True)
    font = ImageFont.truetype(str(font_path), 42)
    cases = []
    for name, text, expected, blur in CASES:
        picture = Image.new('RGB', (1200, 300 + 100 * len(text)), 'white')
        draw = ImageDraw.Draw(picture)
        for index, value in enumerate(['购买日期2026-10-15'] + text):
            draw.text((35, 40 + index * 100), value, fill='black', font=font)
        if blur:
            picture = picture.filter(ImageFilter.GaussianBlur(blur))
        file = directory / (name + '.png')
        picture.save(file)
        cases.append({'id': name, 'file': file.name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                      'expected': {'purchased_on': '2026-10-15', 'items': expected}, 'blur_radius': blur})
    manifest = {'dataset_kind': 'synthetic', 'ground_truth_frozen_before_ocr': True,
                'font_sha256': hashlib.sha256(font_path.read_bytes()).hexdigest(), 'cases': cases,
                'limitations': 'Synthetic typography and a Mock VLM oracle cannot establish real receipt/VLM accuracy or paid cost savings.'}
    (directory / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'cases': len(cases), 'dataset_kind': 'synthetic', 'real_model_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/msyh.ttc'))
    args = parser.parse_args()
    create(args.directory, args.font)
