# core/utils/filters.py
from django.db.models import Count, Min, Max
from core.models import AttributeOption

def compute_filters(base_qs):
    agg = base_qs.aggregate(
        price_min=Min("price"),  price_max=Max("price"),
        width_min=Min("width"),  width_max=Max("width"),
        height_min=Min("height"),height_max=Max("height"),
        depth_min=Min("depth"),  depth_max=Max("depth"),
    )
    ranges = {
        "price":  {"min": agg["price_min"],  "max": agg["price_max"]},
        "width":  {"min": agg["width_min"],  "max": agg["width_max"]},
        "height": {"min": agg["height_min"], "max": agg["height_max"]},
        "depth":  {"min": agg["depth_min"],  "max": agg["depth_max"]},
    }

    color_rows = (
        base_qs.exclude(color__isnull=True)
               .values("color", "color__name", "color__hex_code")
               .annotate(count=Count("id"))
               .order_by("color__name")
    )
    colors = [
        {"id": r["color"], "name": r["color__name"], "hex_code": r["color__hex_code"], "count": r["count"]}
        for r in color_rows
    ]

    tag_rows = (
        base_qs.values("tags__id", "tags__name", "tags__slug")
               .exclude(tags__id__isnull=True)
               .annotate(count=Count("id"))
               .order_by("tags__name")
    )
    tags = [
        {"id": r["tags__id"], "name": r["tags__name"], "slug": r["tags__slug"], "count": r["count"]}
        for r in tag_rows
    ]

    opt_rows = (
        AttributeOption.objects.filter(
            attribute__show_in_filter=True,
            productattributevalue__product__in=base_qs,
        )
        .values(
            "attribute_id",
            "attribute__name",
            "attribute__slug",
            "attribute__filter_widget",
            "attribute__is_multiselect",
            "attribute__filter_order",
            "id",
            "value",
        )
        .annotate(count=Count("productattributevalue__id", distinct=True))
        .order_by("attribute__filter_order", "attribute__name", "value")
    )
    attr_map = {}
    for r in opt_rows:
        aid = r["attribute_id"]
        if aid not in attr_map:
            attr_map[aid] = {
                "id": aid,
                "name": r["attribute__name"],
                "slug": r["attribute__slug"],
                "filter_widget": r["attribute__filter_widget"],
                "is_multiselect": r["attribute__is_multiselect"],
                "filter_order": r["attribute__filter_order"],
                "options": [],
            }
        attr_map[aid]["options"].append({
            "id": r["id"], "value": r["value"], "count": r["count"]
        })
    attributes = sorted(attr_map.values(), key=lambda x: (x["filter_order"], x["name"]))

    return {
        "ranges": ranges,
        "colors": colors,
        "tags": tags,
        "attributes": attributes,
    }
