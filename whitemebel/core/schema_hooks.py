# core/schema_hooks.py
from typing import Any, Dict
from django.db.utils import OperationalError, ProgrammingError

def add_attribute_params(result: Dict[str, Any], generator, request, public):
    """
    Подмешивает в GET /api/products/ параметры attr_<slug> (CSV id опций).
    Работает и на пустой БД — просто молча скипнет.
    """
    try:
        from core.models import ProductAttribute
        attrs = list(
            ProductAttribute.objects.filter(show_in_filter=True)
            .values("slug", "name")
            .order_by("filter_order", "name")
        )
    except (OperationalError, ProgrammingError):
        # миграций нет/таблиц нет — не ломаем схему
        attrs = []

    if not attrs:
        return result

    for path, path_item in (result.get("paths") or {}).items():
        # ищем именно листинг, а не /products/{slug}/
        if not (path.endswith("/products/") and "{slug}" not in path):
            continue
        op = (path_item or {}).get("get")
        if not op:
            continue

        params = op.get("parameters", [])
        for a in attrs:
            slug = a["slug"]
            name = a["name"]
            # OpenAPI массив через CSV: style=form + explode=false
            params.append({
                "name": f"attr_{slug}",
                "in": "query",
                "required": False,
                "description": f"Опции атрибута «{name}». CSV id, пример: attr_{slug}=1,2,5",
                "schema": {
                    "type": "array",
                    "items": {"type": "integer"}
                },
                "style": "form",
                "explode": False,
            })
        op["parameters"] = params

    return result
