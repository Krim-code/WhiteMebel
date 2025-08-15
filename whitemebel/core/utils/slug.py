# core/utils/slug.py
from django.utils.text import slugify
from unidecode import unidecode

def ascii_slug(value: str) -> str:
    return slugify(unidecode(value or ""), allow_unicode=False)
