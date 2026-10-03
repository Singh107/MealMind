"""Reproduce MealMind's original geometric bowl mark using existing Pillow.

Run with the backend Python environment from any directory. No source artwork,
fonts, downloads or image-generation service is used.
"""
from pathlib import Path

from PIL import Image, ImageDraw

PUBLIC = Path(__file__).resolve().parents[1] / 'frontend' / 'public'


def main():
    # Shared geometry in a 64-unit square, used for both SVG and raster assets.
    bowl = [(13, 31), (51, 31), (46, 43), (39, 48), (25, 48), (18, 43)]
    leaf = [(32, 27), (32, 18), (38, 12), (46, 12), (46, 20), (40, 26)]
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">',
           '<rect width="64" height="64" rx="16" fill="#C45500"/>']
    scale = 16
    image = Image.new('RGBA', (64 * scale, 64 * scale))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 64 * scale - 1, 64 * scale - 1),
                           radius=16 * scale, fill='#C45500')
    for points, fill in [(bowl, '#FFFFFF'), (leaf, '#FFFFFF')]:
        coordinates = ' '.join(f'{x},{y}' for x, y in points)
        svg.append(f'<polygon points="{coordinates}" fill="{fill}"/>')
        draw.polygon([(x * scale, y * scale) for x, y in points], fill=fill)
    svg.append('<rect x="24" y="51" width="16" height="3" rx="1.5" fill="#0F172A"/>')
    draw.rounded_rectangle((24 * scale, 51 * scale, 40 * scale, 54 * scale),
                           radius=1.5 * scale, fill='#0F172A')
    svg.append('</svg>')
    (PUBLIC / 'mealmind-mark.svg').write_text('\n'.join(svg) + '\n', encoding='utf-8')
    for size in (192, 512):
        image.resize((size, size), Image.Resampling.LANCZOS).save(PUBLIC / f'logo{size}.png')
    image.save(PUBLIC / 'favicon.ico', sizes=[(16, 16), (24, 24), (32, 32), (64, 64)])


if __name__ == '__main__':
    main()
