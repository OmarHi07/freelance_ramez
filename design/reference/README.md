# Logo reference

This folder keeps the **original, unmodified** Rawnaq Accessories logo supplied by the owner.

> **Action needed:** the original logo file was not included when this version was generated.
> Save it here as `rawnaq-logo-original.png` (or `.jpg`) and commit it. Do not edit the original.

## Making the header mark

The header uses only the illustrated face mark, with "Rawnaq Accessories" rendered as real,
accessible HTML text beside it. Until the logo is added, the site shows a neutral placeholder
mark (`static/img/brand/logo-mark.png`) that is **not** the logo.

```bash
# 1. See the logo with a 50px grid to choose the crop box around the face only
python manage.py prepare_logo_mark design/reference/rawnaq-logo-original.png --preview

# 2. Crop (left,top,right,bottom in pixels) — the original is only read, never changed
python manage.py prepare_logo_mark design/reference/rawnaq-logo-original.png --box 40,20,520,500
```

This writes `static/img/brand/logo-mark.png`, `favicon.png` and `apple-touch-icon.png`.
The mark is cropped and padded only — it is not redrawn or recoloured.

## Spelling issue to confirm with the owner

The text inside the supplied logo appears to read **`Rawnaq_accessoris1`**, while the confirmed
Instagram handle is **`rawnaq_accessories1`**. Because the website shows the store name as HTML
text, the site itself is spelled correctly, but printed/online uses of the full logo image would
show the misspelling. See the README launch checklist.
