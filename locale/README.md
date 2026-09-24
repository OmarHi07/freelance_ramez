# Translations

* Interface text is written in English in templates and Python code and translated to Arabic in
  `ar/LC_MESSAGES/django.po`. The English catalogue is intentionally empty (English is the source language).
* Store content (brands, categories, products, variants, promotions, site settings) is **not** translated here:
  it uses explicit `_ar` / `_en` database fields edited in the owner dashboard.
* The compiled `.mo` files are committed so the site works without GNU gettext installed.

Update workflow:

```bash
python manage.py makemessages -l ar -l en --ignore=.venv --ignore=staticfiles --ignore=media
# translate new/changed entries in locale/ar/LC_MESSAGES/django.po (remove any "fuzzy" flags)
python manage.py compilemessages --ignore=.venv
```

Arabic has six plural forms (zero, one, two, few, many, other); keep all six `msgstr[n]` lines for plural entries.
