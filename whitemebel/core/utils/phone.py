# core/utils/phone.py
import re
from rest_framework import serializers  # если хочешь бросать DRF-ошибки; можно ValidationError из Django

RU_PHONE_RE = re.compile(r'^\+7\d{10}$')

def normalize_ru_phone(raw: str) -> str:
    """Приводим к виду +7XXXXXXXXXX. Разрешаем мусорные символы, 8/7/10-значные ввода."""
    if not raw:
        raise serializers.ValidationError("Телефон обязателен.")
    digits = re.sub(r'\D+', '', raw)
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    elif len(digits) == 10:
        digits = '7' + digits
    if len(digits) == 11 and digits.startswith('7'):
        phone = f"+{digits}"
    else:
        raise serializers.ValidationError("Телефон РФ в формате +7XXXXXXXXXX.")
    if not RU_PHONE_RE.match(phone):
        raise serializers.ValidationError("Телефон РФ в формате +7XXXXXXXXXX.")
    return phone
