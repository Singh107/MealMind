"""Refresh the bundled offline frontend discovery catalog after curated edits."""
from pathlib import Path

root = Path(__file__).resolve().parent
source = root / 'app/services/ingredient_discovery.json'
target = root.parent / 'frontend/src/ingredientCatalog.json'

if __name__ == '__main__':
    target.write_bytes(source.read_bytes())
    print('Updated offline ingredient discovery catalog.')
