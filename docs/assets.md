# Assets and attribution

MealMind's source and original local graphics use the [MIT License](../LICENSE). Third-party dependencies and web fonts retain their respective licenses.

## Original local artwork

| Asset | Provenance and use |
| --- | --- |
| `frontend/public/mealmind-mark.svg` | Original geometric bowl-and-leaf mark created specifically for MealMind. Orange tile, white bowl/leaf and navy base; no borrowed artwork or font outlines |
| `frontend/public/favicon.ico`, `logo192.png`, `logo512.png` | Raster versions of the same original geometry, replacing React starter branding. Existing HTML/manifest filenames remain valid |
| `frontend/public/kitchen-decoration.svg` | Original circles and polygon bowl/leaf illustration, replacing the external decorative photograph. Decorative only, not a generated recipe or food measurement |

The mark and icon files are reproducible with `python tools/generate_brand_assets.py` using the backend's existing Pillow dependency. The decorative SVG is hand-authored geometry. No artwork, personal photos, stock images or image-generation service was used. Existing header/image container dimensions and page layouts are unchanged.

The public frontend has no Google-hosted artwork or other remote image dependency. `designAssets.ts` resolves the local SVGs through the application's public base URL. Unused CRA `src/logo.svg` and `src/App.css`, reference exports and private photographs remain excluded from the public repository.

## Externally hosted fonts and symbols

These remain web-font references in `frontend/public/index.html`; no font binaries are bundled or modified:

- **Bricolage Grotesque**, Copyright 2022 The Bricolage Grotesque Project Authors: [SIL Open Font License 1.1](https://github.com/google/fonts/blob/main/ofl/bricolagegrotesque/OFL.txt).
- **Space Grotesk**, Copyright 2020 The Space Grotesk Project Authors: [SIL Open Font License 1.1](https://github.com/google/fonts/blob/main/ofl/spacegrotesk/OFL.txt).
- **Material Symbols Outlined**, Google: [Apache License 2.0](https://github.com/google/material-design-icons/blob/master/LICENSE). The [official project documents hosted web-font use](https://github.com/google/material-design-icons#using-a-font).

Google Fonts requests contact `fonts.googleapis.com` and `fonts.gstatic.com` and depend on their availability. These fonts/symbols are third-party assets, not MealMind originals. Any future bundling or modification must retain the applicable upstream license notices and conditions.

## Screenshots

Public-safe screenshots are pending; none are included. See the [screenshot checklist](screenshots.md). Internal reference documents, private account captures and personal photos are not publication assets.
