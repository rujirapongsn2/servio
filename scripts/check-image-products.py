"""Live synthetic catalog regression; run in the configured backend environment."""
import io
import json

from PIL import Image, ImageDraw, ImageFont

from app.knowledge_products import extract_products


image = Image.new('RGB', (1100, 640), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 28)
for left, model, color, background in [
    (20, 'ABC-123', '#d92228', '#eeeeee'),
    (570, 'ABC-124', '#245acb', '#d92228'),
]:
    draw.text((left + 15, 20), 'Name: Canvas Tote', fill='black', font=font)
    draw.text((left + 15, 65), 'Model: ' + model, fill='black', font=font)
    draw.rectangle((left, 130, left + 510, 610), fill=background)
    draw.arc((left + 150, 180, left + 360, 390), 180, 360, fill=color, width=24)
    draw.rectangle((left + 110, 280, left + 400, 540), fill=color, outline='black', width=3)
output = io.BytesIO()
image.save(output, 'PNG')
metadata, warnings = extract_products(output.getvalue())
print(json.dumps({'products': metadata['products'] if metadata else None, 'warnings': warnings}, ensure_ascii=False))
assert metadata is not None, 'Product extraction returned no validated metadata'
by_model = {p['model']: p for p in metadata['products']}
assert 'ABC-123' in by_model and 'ABC-124' in by_model, 'Expected both visible model identifiers'
assert {c['family'] for c in by_model['ABC-123']['colors']} == {'red'}, 'Incorrect first product color'
assert {c['family'] for c in by_model['ABC-124']['colors']} == {'blue'}, 'Background color leaked into second product'
assert all(c['evidence'] == 'visual' for p in metadata['products'] for c in p['colors']), 'Invented printed color words'
print('LIVE_SYNTHETIC_PRODUCT_EXTRACTION_PASSED')
