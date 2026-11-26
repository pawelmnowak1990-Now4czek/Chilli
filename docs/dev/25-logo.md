# 25. Logo and social preview

A logo for the README and the repository card, before the first public release.

## What was built

- `docs/assets/logo.svg`: a smiling chili pepper with a green stem on a cream rounded square, in the
  colours of the demo animation (red `#e8492b`, green `#3d8b5a`, cream `#fff1e3`). Plain SVG paths, no
  fonts or filters, so it renders the same everywhere and stays readable at 32 px.
- `docs/assets/logo.png`: the same logo at 512x512 with a transparent background, for places that do
  not take SVG.
- `docs/assets/social-preview.png`: a 1280x640 card with the logo, the name, the tagline and the
  repository address. GitHub uses it when the repository link is shared, once it is uploaded in
  Settings, General, Social preview (the setting appears when the repository is public).
- `docs/assets/brand/social-preview.html`: the source of that card.
- README: the logo above the title.

The logo was drawn for this project. A web search found no product using the same mark; smiling chili
peppers are a common stock motif, so it is not meant as a registered trademark.

## How to rebuild the card

Open `docs/assets/brand/social-preview.html` in a browser window of 1280x640 (or with Playwright,
viewport 1280x640) and save a screenshot as `docs/assets/social-preview.png`.

## Not changed

The browser extension icons (`extension/icons/`) still show the older plain pepper; they can move to
the new logo in a later change.
