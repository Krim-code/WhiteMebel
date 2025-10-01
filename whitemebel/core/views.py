# core/views.py
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from django.db.models import Case, When, IntegerField, Count, Min, Max, Q, Value ,Prefetch
from rest_framework.response import Response
from django_filters import rest_framework as dj_filters
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from collections import OrderedDict
from django.views.generic import TemplateView
from core.models import Category, ProductAttribute, Tag
from core.serializers import CategoryBriefSerializer, CategoryCrumbSerializer, CategoryNodeSerializer, ProductDetailSerializer, ProductListSerializer,ProductsByIdsResponseSerializer, ServiceListSerializer, TagSerializer
from core.serializers import FiltersResponseSerializer
from rest_framework.views import APIView
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from core.models import Product, AttributeOption
from core.pagination import LimitPageNumberPagination
from core.utils.filters import compute_filters
from rest_framework import permissions
from core.models import MainSlider
from core.serializers import MainSliderSerializer

from decimal import Decimal
from core.models import DeliveryRegion, DeliveryDiscount
from core.serializers import DeliveryRegionCostSerializer
from rest_framework.generics import CreateAPIView
from drf_spectacular.utils import OpenApiExample
from core.models import ContactRequest
from core.serializers import ContactRequestCreateSerializer
from core.serializers import OrderCreateSerializer
from core.models import Order
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from django.db import transaction
from .models import Payment, Service
from .utils.cloudpayments import verify_cp_signature
import base64, hashlib, hmac, json

from django.urls import reverse
from core.serializers import (
    CloudPaymentsInitResponseSerializer,
    OrderStatusResponseSerializer,
)

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/categories/                — плоский список (фильтры: parent, level, is_featured)
    GET /api/categories/tree/?depth=3   — дерево с корня (depth уровней вниз)
    GET /api/categories/{slug}/children/?depth=2 — дети выбранной категории на N уровней
    GET /api/categories/{slug}/         — детали категории (плоско)
    """
    serializer_class = CategoryBriefSerializer
    lookup_field = "slug"
    filter_backends = [dj_filters.DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_featured"]  # parent и level — руками, см. get_queryset
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "lft", "level"]
    ordering = ["tree_id", "lft"]

    def get_queryset(self):
        qs = Category.objects.all().select_related("parent")
        # опционально — счётчик товаров
        if self.request.query_params.get("with_counts") == "1":
            qs = qs.annotate(products_count=Count("products"))
        # фильтр по родителю: ?parent=root | ?parent=<slug>
        parent = self.request.query_params.get("parent")
        if parent:
            if parent == "root":
                qs = qs.filter(parent__isnull=True)
            else:
                qs = qs.filter(parent__slug=parent)
        # фильтр по уровню: ?level=0..N
        level = self.request.query_params.get("level")
        if level is not None:
            try:
                qs = qs.filter(level=int(level))
            except ValueError:
                pass
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("depth", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Глубина дерева, по умолчанию 3"),
            OpenApiParameter("with_counts", OpenApiTypes.INT, OpenApiParameter.QUERY, description="1 — добавить products_count"),
        ],
        responses=CategoryNodeSerializer(many=True),
        summary="Дерево категорий от корня",
    )
    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        depth = int(request.query_params.get("depth", 3))
        qs = Category.objects.filter(parent__isnull=True)
        if request.query_params.get("with_counts") == "1":
            qs = qs.annotate(products_count=Count("products"))
        ser = CategoryNodeSerializer(qs, many=True, context={"request": request, "depth": depth})
        return Response(ser.data)

    @extend_schema(
        parameters=[
            OpenApiParameter("depth", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Глубина детей, по умолчанию 1"),
            OpenApiParameter("with_counts", OpenApiTypes.INT, OpenApiParameter.QUERY, description="1 — добавить products_count"),
        ],
        responses=CategoryNodeSerializer(many=True),
        summary="Дочерние категории выбранной категории",
    )
    @action(detail=True, methods=["get"], url_path="children")
    def children(self, request, slug=None):
        depth = int(request.query_params.get("depth", 1))
        category = self.get_object()
        qs = category.children.all()
        if request.query_params.get("with_counts") == "1":
            qs = qs.annotate(products_count=Count("products"))
        # depth применяется к потомкам; для детей передаём depth-1
        ser = CategoryNodeSerializer(qs, many=True, context={"request": request, "depth": max(0, depth - 1)})
        return Response(ser.data)



def _to_float(x):
    return float(x) if x is not None else None



def _parse_bool(v, default=None):
    if v is None:
        return default
    return str(v).lower() in {"1","true","yes","y","on"}
class FiltersView(APIView):
    """
    Возвращает фильтры для каталога:
    - только значения, которые реально есть в товарах выборки
    - диапазоны: price/width/height/depth
    - список цветов/тегов с count
    - атрибуты (метаданные + опции с count)
    Параметры:
      ?category=<slug> — категория (включая вложенные по умолчанию)
      ?deep=0|1 — учитывать вложенные (default 1)
      ?in_stock=0|1 — только в наличии (default None = не фильтровать)
      ?active=0|1 — только активные (default 1)
    """

    @extend_schema(
        parameters=[
            OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Слаг категории"),
            OpenApiParameter("deep", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Включать вложенные (1/0), по умолчанию 1"),
            OpenApiParameter("in_stock", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Только в наличии (1/0)"),
            OpenApiParameter("active", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Только активные (1/0, по умолчанию 1)"),
        ],
        responses=FiltersResponseSerializer,
        summary="Получить доступные фильтры для выборки товаров",
    )
    def get(self, request):
        category_slug = request.query_params.get("category")
        include_desc = _parse_bool(request.query_params.get("deep"), True)
        only_active = _parse_bool(request.query_params.get("active"), True)
        only_in_stock = _parse_bool(request.query_params.get("in_stock"), None)

        products = Product.objects.all()

        # активность
        if only_active is True:
            products = products.filter(is_active=True)
        elif only_active is False:
            products = products.filter(is_active=False)

        # в наличии
        if only_in_stock is True:
            products = products.filter(stock__gt=0)
        elif only_in_stock is False:
            products = products.filter(stock=0)

        # категория
        cat = None
        if category_slug:
            try:
                cat = Category.objects.get(slug=category_slug)
            except Category.DoesNotExist:
                raise NotFound("Категория не найдена")
            if include_desc:
                products = products.filter(category__in=cat.get_descendants(include_self=True))
            else:
                products = products.filter(category=cat)

        # основная выборка для агрегаций
        base_qs = products.select_related("color", "category")

        total_products = base_qs.count()

        # диапазоны
        agg = base_qs.aggregate(
            price_min=Min("price"),  price_max=Max("price"),
            width_min=Min("width"),  width_max=Max("width"),
            height_min=Min("height"),height_max=Max("height"),
            depth_min=Min("depth"),  depth_max=Max("depth"),
        )

        ranges = {
            "price":  {"title": "Цена",    "min": _to_float(agg["price_min"]),  "max": _to_float(agg["price_max"])},
            "width":  {"title": "Ширина",  "min": _to_float(agg["width_min"]),  "max": _to_float(agg["width_max"])},
            "height": {"title": "Высота",  "min": _to_float(agg["height_min"]), "max": _to_float(agg["height_max"])},
            "depth":  {"title": "Глубина", "min": _to_float(agg["depth_min"]),  "max": _to_float(agg["depth_max"])},
        }

        color_rows = (
            base_qs.exclude(color__isnull=True)
                   .values("color", "color__name", "color__hex_code")
                   .annotate(count=Count("id"))
                   .order_by("color__name")
        )
        colors = [
            {
                "id": r["color"],
                "name": r["color__name"],
                "title": r["color__name"],            # <- добавили
                "hex_code": r["color__hex_code"],
                "count": r["count"],
            }
            for r in color_rows
        ]

        tag_rows = (
            base_qs.values("tags__id", "tags__name", "tags__slug")
                   .exclude(tags__id__isnull=True)
                   .annotate(count=Count("id"))
                   .order_by("tags__name")
        )
        tags = [
            {
                "id": r["tags__id"],
                "name": r["tags__name"],
                "title": r["tags__name"],             # <- добавили
                "slug": r["tags__slug"],
                "count": r["count"],
            }
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

        # ключ — slug
        attr_by_slug = {}
        for r in opt_rows:
            slug = r["attribute__slug"]
            if slug not in attr_by_slug:
                attr_by_slug[slug] = {
                    "id": r["attribute_id"],
                    "name": r["attribute__name"],
                    "title": r["attribute__name"],
                    "slug": slug,
                    "filter_widget": r["attribute__filter_widget"],
                    "is_multiselect": r["attribute__is_multiselect"],
                    "filter_order": r["attribute__filter_order"],
                    "options": [],
                }
            attr_by_slug[slug]["options"].append({
                "id": r["id"],
                "value": r["value"],
                "title": r["value"],
                "count": r["count"],
            })

        # чтобы фронт получал предсказуемый порядок — отсортируем слуги по порядку фильтра, но вернём dict
        ordered_slugs = sorted(
            attr_by_slug.keys(),
            key=lambda s: (attr_by_slug[s]["filter_order"], attr_by_slug[s]["name"])
        )
        attributes_obj = OrderedDict((s, attr_by_slug[s]) for s in ordered_slugs)

        payload = {
            "category": cat.slug if cat else None,
            "include_descendants": bool(include_desc),
            "total_products": total_products,
            "ranges": {
                "price":  {"title": "Цена",         "min": _to_float(agg["price_min"]),  "max": _to_float(agg["price_max"])},
                "width":  {"title": "Ширина (см)",  "min": _to_float(agg["width_min"]),  "max": _to_float(agg["width_max"])},
                "height": {"title": "Высота (см)",  "min": _to_float(agg["height_min"]), "max": _to_float(agg["height_max"])},
                "depth":  {"title": "Глубина (см)", "min": _to_float(agg["depth_min"]),  "max": _to_float(agg["depth_max"])},
            },
            "colors": colors,
            "tags": tags,
            "attributes": attributes_obj,   # <-- теперь объект
            "titles": {
                "colors": "Цвет",
                "tags": "Теги",
                "attributes": "Характеристики",
            },
        }

        return Response(FiltersResponseSerializer(payload).data)



def _csv_ints(v):
    if not v: return []
    out = []
    for p in str(v).replace(" ", "").split(","):
        if not p: continue
        try: out.append(int(p))
        except ValueError: pass
    return out

def _csv_strs(v):
    if not v: return []
    return [s for s in str(v).replace(" ", "").split(",") if s]

class ProductListView(APIView):
    """
    GET /api/products/
      Параметры:
        category: slug категории
        deep: 1/0 — включать вложенные (по умолчанию 1)
        q: строка поиска (title, description, sku)
        price_min/price_max, width_min/width_max, height_min/height_max, depth_min/depth_max
        color: CSV id цветов (напр. color=1,3,5)
        tag: CSV slug’ов тегов (напр. tag=novinka,hit)
        attr_<slug>: CSV id опций по атрибуту (напр. attr_material=1,3)
        in_stock: 1/0, active: 1/0 (по умолчанию active=1)
        ordering: -created_at|price|-price|title
        page, limit: пагинация (limit макс 200)
    Ответ:
      { count, page, limit, results: [...], filters: {...} }
    """
    serializer_class = ProductListSerializer
    pagination_class = LimitPageNumberPagination

    @extend_schema(
        parameters=[
            OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("deep", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("price_min", OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter("price_max", OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter("width_min", OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter("width_max", OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter("height_min", OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter("height_max", OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter("depth_min", OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter("depth_max", OpenApiTypes.NUMBER, OpenApiParameter.QUERY),
            OpenApiParameter("color", OpenApiTypes.STR, OpenApiParameter.QUERY, description="CSV id цветов"),
            OpenApiParameter("tag", OpenApiTypes.STR, OpenApiParameter.QUERY, description="CSV slug тегов"),
            OpenApiParameter("in_stock", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("active", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("ordering", OpenApiTypes.STR, OpenApiParameter.QUERY),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        summary="Листинг товаров с фильтрами, пагинацией и пересчитанными фасетами",
    )
    def get(self, request):
        qs = Product.objects.all().select_related("color", "category").prefetch_related("tags")

        # базовые флаги
        only_active = _b(request.query_params.get("active"), True)
        only_in_stock = _b(request.query_params.get("in_stock"), None)
        if only_active is True:
            qs = qs.filter(is_active=True)
        elif only_active is False:
            qs = qs.filter(is_active=False)
        if only_in_stock is True:
            qs = qs.filter(stock__gt=0)
        elif only_in_stock is False:
            qs = qs.filter(stock=0)

        # категория
        category_slug = request.query_params.get("category")
        deep = _b(request.query_params.get("deep"), True)
        cat = None                                   # <-- добавили
        if category_slug:
            try:
                cat = Category.objects.get(slug=category_slug)
            except Category.DoesNotExist:
                return Response({"detail": "Category not found"}, status=404)
            qs = qs.filter(category__in=cat.get_descendants(include_self=True) if deep else [cat])

        # поиск
        q = request.query_params.get("q")
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(sku__icontains=q))

        # числовые диапазоны
        rng_map = {
            "price": ("price_min", "price_max"),
            "width": ("width_min", "width_max"),
            "height": ("height_min", "height_max"),
            "depth": ("depth_min", "depth_max"),
        }
        for field, (param_min, param_max) in rng_map.items():
            vmin = request.query_params.get(param_min)
            vmax = request.query_params.get(param_max)
            if vmin not in (None, ""):
                try: qs = qs.filter(**{f"{field}__gte": float(vmin)})
                except ValueError: pass
            if vmax not in (None, ""):
                try: qs = qs.filter(**{f"{field}__lte": float(vmax)})
                except ValueError: pass

        # цвета
        color_ids = _csv_ints(request.query_params.get("color"))
        if color_ids:
            qs = qs.filter(color_id__in=color_ids)

        # теги
        tag_slugs = _csv_strs(request.query_params.get("tag"))
        if tag_slugs:
            qs = qs.filter(tags__slug__in=tag_slugs).distinct()

        # атрибуты
        attr_params = {k: v for k, v in request.query_params.items() if k.startswith("attr_")}
        if attr_params:
            slug_to_id = dict(ProductAttribute.objects.values_list("slug", "id"))
            for key, value in attr_params.items():
                slug = key[5:]
                option_ids = _csv_ints(value)
                if not option_ids:
                    continue
                attr_id = slug_to_id.get(slug)
                if not attr_id:
                    continue
                qs = qs.filter(
                    attributes__attribute_id=attr_id,
                    attributes__option_id__in=option_ids
                )

        # сортировка
        ordering = request.query_params.get("ordering") or "-created_at"
        allowed = {"created_at", "-created_at", "price", "-price", "title", "-title"}
        if ordering not in allowed:
            ordering = "-created_at"
        qs = qs.order_by(ordering, "id")

        # фасеты (после фильтров)
        facets = compute_filters(qs)

        # хлебные крошки по выбранной категории
        breadcrumbs = []
        if cat:
            nodes = cat.get_ancestors(include_self=True)
            breadcrumbs = CategoryCrumbSerializer(nodes, many=True).data

        # пагинация
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        data = ProductListSerializer(page, many=True, context={"request": request}).data

        # добавили breadcrumbs в payload
        return paginator.get_paginated_response({
            "results": data,
            "filters": facets,
            "breadcrumbs": breadcrumbs,
        })
        
        
# core/views.py
class ProductDetailView(APIView):
    """
    GET /api/products/<slug>/?include_related=1&related_limit=8&related_by_color_limit=8
    """
    @extend_schema(
        parameters=[
            OpenApiParameter("include_related", OpenApiTypes.INT, OpenApiParameter.QUERY, description="1/0 — включить блоки related_* (по умолчанию 1)"),
            OpenApiParameter("related_limit", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Сколько связанных вернуть (default 8)"),
            OpenApiParameter("related_by_color_limit", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Сколько связанных по цвету вернуть (default 8)"),
        ],
        responses=ProductDetailSerializer,
        summary="Детальная карточка товара",
    )
    def get(self, request, slug):
        include_related = str(request.query_params.get("include_related", "1")).lower() in {"1","true","yes","on"}
        related_limit = int(request.query_params.get("related_limit", 8))
        related_by_color_limit = int(request.query_params.get("related_by_color_limit", 8))

        # queryset для карточек, как в листинге
        rel_card_qs = (
            Product.objects.filter(is_active=True)
            .select_related("color", "category")
            .prefetch_related("tags")
        )

        qs = (
            Product.objects.filter(is_active=True, slug=slug)
            .select_related("color", "category")
            .prefetch_related(
                "tags",
                "images",
                "attributes__attribute",
                "attributes__option",
                # related блоки — сразу карточными данными
                *( [
                    Prefetch("related_products", queryset=rel_card_qs),
                    Prefetch("related_by_color", queryset=rel_card_qs),
                ] if include_related else [] )
            )
        )

        obj = get_object_or_404(qs)

        ctx = {
            "request": request,
            "related_limit": related_limit if include_related else 0,
            "related_by_color_limit": related_by_color_limit if include_related else 0,
        }
        data = ProductDetailSerializer(obj, context=ctx).data
        return Response(data)


# core/views.py

def _b(v, default=None):
    if v is None: return default
    return str(v).lower() in {"1","true","yes","y","on"}

class SliderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/slider/?limit=5&active=1
    POST /api/slider/reorder/  (только админы)
    """
    serializer_class = MainSliderSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["order", "created_at", "updated_at"]
    ordering = ["order", "id"]

    def get_queryset(self):
        qs = MainSlider.objects.all().order_by(*self.ordering)
        active = _b(self.request.query_params.get("active"), True)  # по умолчанию только активные
        if active is True:
            qs = qs.filter(is_active=True)
        elif active is False:
            qs = qs.filter(is_active=False)
        # лимит
        try:
            limit = int(self.request.query_params.get("limit", 0))
            if limit > 0:
                qs = qs[:min(limit, 50)]  # не офигеваем, верхний кап
        except ValueError:
            pass
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY, description="Максимум слайдов (<=50)"),
            OpenApiParameter("active", OpenApiTypes.INT, OpenApiParameter.QUERY, description="1 — только активные, 0 — только неактивные, пусто — все"),
            OpenApiParameter("ordering", OpenApiTypes.STR, OpenApiParameter.QUERY, description="order|created_at|updated_at с '-'"),
        ],
        responses=MainSliderSerializer(many=True),
        summary="Получить слайды (по умолчанию только активные)",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"id": {"type":"integer"}, "order": {"type":"integer"}},
                            "required": ["id", "order"]
                        }
                    }
                },
                "required": ["items"]
            }
        },
        responses={"200": {"type": "object", "properties": {"updated": {"type": "integer"}}}},
        summary="Переставить порядок слайдов (только админы)",
    )
    @action(detail=False, methods=["post"], url_path="reorder", permission_classes=[permissions.IsAdminUser])
    def reorder(self, request):
        data = request.data or {}
        items = data.get("items") or []
        if not isinstance(items, list):
            return Response({"detail": "items must be a list"}, status=400)

        id_to_order = {}
        for it in items:
            try:
                iid = int(it.get("id"))
                ordv = int(it.get("order"))
            except Exception:
                return Response({"detail": "id/order must be integers"}, status=400)
            id_to_order[iid] = ordv

        slides = list(MainSlider.objects.filter(id__in=id_to_order.keys()))
        for s in slides:
            new_order = id_to_order.get(s.id)
            if new_order is not None and s.order != new_order:
                s.order = new_order
        # bulk update
        MainSlider.objects.bulk_update(slides, ["order"])
        return Response({"updated": len(slides)})




class DeliveryRegionListView(APIView):
    """
    GET /api/shipping/regions/?order_total=45000&active=1&detailed=1
    Возвращает список регионов доставки с финальной ценой.
    """
    @extend_schema(
        parameters=[
            OpenApiParameter("order_total", OpenApiTypes.NUMBER, OpenApiParameter.QUERY,
                             description="Сумма товара в корзине (для порога бесплатной и скидок)"),
            OpenApiParameter("active", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="1 — только активные (по умолчанию), 0 — только неактивные, пусто — все"),
            OpenApiParameter("detailed", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="1 — вернуть информацию о применённой скидке"),
            OpenApiParameter("ordering", OpenApiTypes.STR, OpenApiParameter.QUERY,
                             description="Сортировка: order|name|final_cost c '-'"),
        ],
        responses=DeliveryRegionCostSerializer(many=True),
        summary="Регионы доставки с расчётом стоимости",
    )
    def get(self, request):
        # базовый qs
        qs = DeliveryRegion.objects.all()
        active = _b(request.query_params.get("active"), True)
        if active is True:
            qs = qs.filter(is_active=True)
        elif active is False:
            qs = qs.filter(is_active=False)

        # сортировка (по умолчанию по order, затем name)
        ordering = request.query_params.get("ordering") or "order,name"
        allowed = {"order", "-order", "name", "-name", "final_cost", "-final_cost"}
        # Если хотят сортировать по final_cost — посчитаем на уровне Python, оставим как есть
        sort_by_final = ordering in {"final_cost", "-final_cost"}

        # входные параметры
        order_total_raw = request.query_params.get("order_total") or "0"
        try:
            order_total = Decimal(str(order_total_raw))
        except Exception:
            order_total = Decimal("0")
        detailed = _b(request.query_params.get("detailed"), True)

        # подготовим скидки (активные «по времени» проверяются в методе модели)
        discounts_qs = DeliveryDiscount.objects.filter(is_active=True).select_related("region")

        # сериализация
        ser = DeliveryRegionCostSerializer(
            qs, many=True,
            context={
                "request": request,
                "order_total": order_total,
                "discounts_qs": list(discounts_qs),  # один раз вытащим
                "detailed": detailed,
            }
        )
        data = ser.data

        # сортировка по final_cost, если просили
        if sort_by_final:
            rev = ordering.startswith("-")
            data.sort(key=lambda r: (r["final_cost"] if r["final_cost"] is not None else Decimal("0")), reverse=rev)
        elif ordering and ordering in {"order", "-order"}:
            rev = ordering.startswith("-")
            data.sort(key=lambda r: (r["order"], r["name"]), reverse=rev)
        elif ordering and ordering in {"name", "-name"}:
            rev = ordering.startswith("-")
            data.sort(key=lambda r: r["name"], reverse=rev)

        return Response(data)
    
    
    
class DeliveryRegionQuoteView(APIView):
    """
    GET /api/shipping/regions/<slug>/quote/?order_total=45000&detailed=1
    """
    @extend_schema(
        parameters=[
            OpenApiParameter("order_total", OpenApiTypes.NUMBER, OpenApiParameter.QUERY,
                             description="Сумма корзины для расчёта порога/скидок"),
            OpenApiParameter("detailed", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="1 — вернуть инфу о применённой скидке (по умолчанию 1)"),
            OpenApiParameter("active", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="1 — искать только активные (по умолчанию 1)"),
        ],
        responses=DeliveryRegionCostSerializer,
        summary="Расчёт доставки по конкретному региону",
    )
    def get(self, request, slug: str):
        # входные
        try:
            order_total = Decimal(str(request.query_params.get("order_total") or "0"))
        except Exception:
            order_total = Decimal("0")
        detailed = _b(request.query_params.get("detailed"), True)
        active = _b(request.query_params.get("active"), True)

        # регион
        qs = DeliveryRegion.objects.all()
        if active is True:
            qs = qs.filter(is_active=True)
        elif active is False:
            qs = qs.filter(is_active=False)
        region = get_object_or_404(qs, slug=slug)

        # скидки (общие + по региону)
        discounts_qs = DeliveryDiscount.objects.filter(is_active=True).select_related("region")

        data = DeliveryRegionCostSerializer(
            region,
            context={
                "request": request,
                "order_total": order_total,
                "discounts_qs": list(discounts_qs),
                "detailed": detailed,
            },
        ).data
        return Response(data)
    
    




def _parse_ids_from_query(qs_param):
    if not qs_param:
        return []
    parts = str(qs_param).replace(" ", "").split(",")
    out = []
    for p in parts:
        if not p: 
            continue
        try:
            out.append(int(p))
        except ValueError:
            continue
    return out

def _normalize_ids(payload):
    # payload может быть строкой "1,2,3" или list/tuple
    if payload is None:
        return []
    if isinstance(payload, (list, tuple)):
        out = []
        for x in payload:
            try: out.append(int(x))
            except (TypeError, ValueError): pass
        return out
    return _parse_ids_from_query(payload)

class ProductsByIdsView(APIView):
    """
    GET  /api/products/by-ids/?ids=1,2,3&active=1
    POST /api/products/by-ids/  {"ids":[1,2,3], "active":1}
    Возвращает товары в том же порядке, что пришли id.
    """
    @extend_schema(
        parameters=[
            OpenApiParameter("ids", OpenApiTypes.STR, OpenApiParameter.QUERY,
                             description="CSV id, пример: 12,5,9 (для GET)"),
            OpenApiParameter("active", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="1 — только активные (по умолчанию), 0 — только неактивные, пусто — все"),
        ],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "ids": {"type": "array", "items": {"type": "integer"}},
                    "active": {"type": "integer", "enum": [0,1]},
                },
                "required": ["ids"]
            }
        },
        responses=ProductsByIdsResponseSerializer,
        summary="Получить товары по массиву id (с сохранением порядка)",
    )
    def get(self, request):
        ids = _parse_ids_from_query(request.query_params.get("ids"))
        active = _b(request.query_params.get("active"), True)
        return self._respond(request, ids, active)

    def post(self, request):
        data = request.data or {}
        ids = _normalize_ids(data.get("ids"))
        active = _b(data.get("active"), True)
        return self._respond(request, ids, active)

    def _respond(self, request, ids, active):
        if not ids:
            return Response({"detail": "ids пустой."}, status=status.HTTP_400_BAD_REQUEST)

        # ограничим чтобы не убить БД
        if len(ids) > 500:
            return Response({"detail": "Слишком много id (макс 500)."}, status=413)

        # убираем точные дубли, но порядок первых вхождений сохраняем
        seen = set()
        ordered_ids = []
        for i in ids:
            if i not in seen:
                seen.add(i)
                ordered_ids.append(i)

        qs = Product.objects.filter(id__in=ordered_ids)\
            .select_related("color", "category")\
            .prefetch_related("tags")

        if active is True:
            qs = qs.filter(is_active=True)
        elif active is False:
            qs = qs.filter(is_active=False)

        # Сохранить порядок как в ordered_ids
        order_case = Case(
            *[When(id=pk, then=pos) for pos, pk in enumerate(ordered_ids)],
            output_field=IntegerField(),
        )
        qs = qs.order_by(order_case, "id")

        found_ids = set(qs.values_list("id", flat=True))
        missing = [pk for pk in ordered_ids if pk not in found_ids]

        ser = ProductListSerializer(qs, many=True, context={"request": request})
        payload = {"results": ser.data, "missing": missing}
        return Response(payload)
    
    

class TagListView(APIView):
    """
    GET /api/tags/?home=1&with_counts=1&q=хит&limit=50
    """
    @extend_schema(
        parameters=[
            OpenApiParameter("home", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="1 — только show_on_home, 0 — только не-home, пусто — все"),
            OpenApiParameter("with_counts", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="1 — добавить product_count"),
            OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY,
                             description="поиск по name/slug"),
            OpenApiParameter("limit", OpenApiTypes.INT, OpenApiParameter.QUERY,
                             description="ограничить кол-во (1..500, по умолчанию 100)"),
        ],
        responses=TagSerializer(many=True),
        summary="Список тегов (с фильтром по show_on_home и опциональным количеством товаров)",
    )
    def get(self, request):
        qs = Tag.objects.all()

        home = _b(request.query_params.get("home"), None)
        if home is True:
            qs = qs.filter(show_on_home=True)
        elif home is False:
            qs = qs.filter(show_on_home=False)

        q = request.query_params.get("q")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q))

        with_counts = _b(request.query_params.get("with_counts"), False)
        if with_counts:
            qs = qs.annotate(product_count=Count("products", distinct=True))
        else:
            qs = qs.annotate(product_count=Value(0, output_field=IntegerField()))

        try:
            limit = int(request.query_params.get("limit", 100))
        except ValueError:
            limit = 100
        limit = max(1, min(limit, 500))

        qs = qs.order_by("name")[:limit]
        return Response(TagSerializer(qs, many=True).data)
    


class ContactRequestCreateView(CreateAPIView):
    """POST /api/contact-requests/ — оставить телефон для звонка."""
    serializer_class = ContactRequestCreateSerializer
    queryset = ContactRequest.objects.all()

    @extend_schema(
        summary="Создать обращение (имя + телефон)",
        request=ContactRequestCreateSerializer,
        responses=ContactRequestCreateSerializer,
        examples=[
            OpenApiExample(
                "Пример",
                value={"name": "Иван", "phone": "+7 (999) 123-45-67"},
                request_only=True,
            ),
            OpenApiExample(
                "Успешный ответ",
                value={
                    "id": 12,
                    "name": "Иван",
                    "phone": "+79991234567",
                    "created_at": "2025-09-29T10:00:00Z"
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class OrderCreateView(CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = OrderCreateSerializer

    @extend_schema(
        summary="Оформление заказа",
        tags=["orders"],
        request=OrderCreateSerializer,
        responses=OrderCreateSerializer,
        examples=[
            OpenApiExample(
                "Пример заказа (доставка)",
                value={
                    "full_name": "Иванов Иван",
                    "phone": "+7 (999) 123-45-67",
                    "email": "ivan@example.com",
                    "city": "Москва",
                    "address": "ул. Пушкина, д. 10",
                    "comment": "Позвонить за час",
                    "payment_method": "cod",
                    "total_price": "35200.00",
                    "delivery_type": "delivery",
                    "region": "moscow-mo",
                    "items": [
                        {"product_id": 123, "quantity": 2},
                        {"product_id": 456, "quantity": 1}
                    ],
                    "services": [
                        {"service_id": 1}
                    ]
                },
                request_only=True,
            ),
            OpenApiExample(
                "Пример ответа",
                value={
                    "id": 1,
                    "full_name": "Иванов Иван",
                    "phone": "+79991234567",
                    "email": "ivan@example.com",
                    "city": "Москва",
                    "address": "ул. Пушкина, д. 10",
                    "comment": "Позвонить за час",
                    "payment_method": "cod",
                    "delivery_type": "delivery",
                    "status": "new",
                    "created_at": "2025-09-29T12:34:56Z",
                    "items_brief": [
                        {
                            "product_id": 123,
                            "product_title": "Шкаф-купе Alpha 200",
                            "product_slug": "shkaf-kupe-alpha-200",
                            "product_image": "/media/products/alpha.webp",
                            "quantity": 2,
                            "price_at_moment": "12000.00",
                            "final_price": "24000.00"
                        }
                    ],
                    "services_brief": [
                        {"service_id": 1, "service_name": "Сборка", "price_at_moment": "2500.00"}
                    ],
                    "subtotal": "24000.00",
                    "services_total": "2500.00",
                    "delivery_base": "1500.00",
                    "delivery_discount": "0.00",
                    "delivery_cost": "1500.00"
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
    
    




# ---------- HTML виджет (только для теста/демо) ----------
class CloudPaymentsPayView(TemplateView):
    template_name = "payments/pay_widget.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        order = get_object_or_404(Order, pk=kwargs["order_id"])
        request = self.request

        success_url = request.build_absolute_uri(f"/api/payments/success/?order_id={order.id}")
        fail_url    = request.build_absolute_uri(f"/api/payments/fail/?order_id={order.id}")
        status_api  = request.build_absolute_uri(f"/api/orders/{order.id}/status/")

        ctx.update({
            "order": order,
            "public_id": settings.CLOUDPAYMENTS_PUBLIC_ID,
            "amount": float(order.total_price),
            "currency": "RUB",
            "account_id": order.email or order.phone or f"user-{order.id}",
            "description": f"Оплата заказа #{order.id} на WhiteMebel",
            "success_url": success_url,
            "fail_url": fail_url,
            "status_api": status_api,
        })
        return ctx


# ---------- API: вернуть конфиг для виджета (Swagger-видимый) ----------
class CloudPaymentsInitView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        parameters=[OpenApiParameter("order_id", OpenApiTypes.INT, OpenApiParameter.PATH)],
        responses=CloudPaymentsInitResponseSerializer,
        summary="CloudPayments: получить конфиг для оплаты заказа",
    )
    def get(self, request, order_id: int):
        order = get_object_or_404(Order, pk=order_id)

        success_url = request.build_absolute_uri(f"/api/payments/success/?order_id={order.id}")
        fail_url    = request.build_absolute_uri(f"/api/payments/fail/?order_id={order.id}")
        status_api  = request.build_absolute_uri(f"/api/orders/{order.id}/status/")
        pay_url     = request.build_absolute_uri(reverse("cp-pay", args=[order.id]))

        payload = {
            "order_id": order.id,
            "public_id": settings.CLOUDPAYMENTS_PUBLIC_ID,
            "amount": float(order.total_price),
            "currency": "RUB",
            "account_id": order.email or order.phone or f"user-{order.id}",
            "description": f"Оплата заказа #{order.id} на WhiteMebel",
            "status_api": status_api,
            "success_url": success_url,
            "fail_url": fail_url,
            "pay_url": pay_url,
        }
        return Response(CloudPaymentsInitResponseSerializer(payload).data)


# ---------- API: статус заказа (поллинг фронта) ----------
class OrderStatusView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        parameters=[OpenApiParameter("order_id", OpenApiTypes.INT, OpenApiParameter.PATH)],
        responses=OrderStatusResponseSerializer,
        summary="Статус заказа (для поллинга оплаты)",
    )
    def get(self, request, order_id: int):
        order = get_object_or_404(Order, pk=order_id)
        return Response({"order_id": order.id, "status": order.status, "paid": order.status == "paid"})


# ---------- success/fail (можно редиректить на фронт) ----------
class PaymentSuccessView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok", "order_id": int(request.query_params.get("order_id", 0))})


class PaymentFailView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "fail", "order_id": int(request.query_params.get("order_id", 0))})


# ---------- Webhook от CloudPayments (Check/Pay/Fail/Refund/Confirm) ----------
def _verify_cp_hmac(raw_body: bytes, header_value: str, secret: str) -> bool:
    """Проверяем Content-HMAC = base64( HMAC_SHA256(secret, raw_body) )"""
    if not header_value:
        return False
    digest = hmac.new(secret.encode("utf-8"), msg=raw_body, digestmod=hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, header_value)


class CloudPaymentsWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    # CloudPayments требует HTTP 200 с JSON {'code':0} для успеха
    def _ok(self, message="OK"):
        return Response({"code": 0, "message": message})

    def _err(self, message="Error", code=13):
        # 13 — generic decline
        return Response({"code": code, "message": message})

    @extend_schema(
        summary="CloudPayments webhook",
        description="Обрабатывает уведомления: Check, Pay, Fail, Refund, Confirm. Подписано через Content-HMAC.",
        responses=None,
    )
    def post(self, request):
        raw = request.body or b""
        h = request.META.get("HTTP_CONTENT_HMAC", "")
        if not _verify_cp_hmac(raw, h, settings.CLOUDPAYMENTS_SECRET):
            return self._err("Bad signature", code=12)

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._err("Bad JSON", code=12)

        ntype = (payload.get("NotificationType") or payload.get("notificationType") or "").lower()
        invoice_id = payload.get("InvoiceId") or payload.get("InvoiceID")
        data = payload.get("Data") or {}
        order_id = data.get("order_id") or invoice_id
        amount = Decimal(str(payload.get("Amount", "0")))
        transaction_id = payload.get("TransactionId") or payload.get("TransactionID")

        if not order_id:
            return self._err("No order_id")

        order = Order.objects.filter(pk=int(order_id)).first()
        if not order:
            return self._err("Order not found", code=12)

        # Check — провалидацию делаем тут: сумма, состояние, и т.д.
        if ntype == "check":
            # проверим сумму (на рубли не ругаемся на копейки)
            if amount.quantize(Decimal("0.01")) != order.total_price.quantize(Decimal("0.01")):
                return self._err("Amount mismatch", code=2)
            if order.status in ("paid", "canceled"):
                return self._err("Order already closed", code=13)
            return self._ok("Check OK")

        # Pay — деньги списаны. Фиксируем заказ.
        if ntype == "pay":
            order.status = "paid"
            # если хочешь — сохрани transaction_id, paid_at
            # order.transaction_id = transaction_id
            order.save(update_fields=["status"])
            return self._ok("Pay OK")

        # Fail — оплата не прошла
        if ntype == "fail":
            # Не обязательно отменять заказ сразу, но логично
            order.status = "canceled"
            order.save(update_fields=["status"])
            return self._ok("Fail OK")

        # Refund — возврат средств
        if ntype == "refund":
            order.status = "canceled"
            order.save(update_fields=["status"])
            return self._ok("Refund OK")

        # Confirm — для двухстадийных (hold->capture). Если используешь charge — обычно не придёт.
        if ntype == "confirm":
            order.status = "paid"
            order.save(update_fields=["status"])
            return self._ok("Confirm OK")

        # если что-то экзотическое
        return self._ok("Ignored")


class ServiceListView(ListAPIView):
    """
    GET /api/services/?active=1
    """
    serializer_class = ServiceListSerializer

    def get_queryset(self):
        qs = Service.objects.all().only("id", "name", "price", "is_active").order_by("name")
        active = self.request.query_params.get("active", "1")
        if str(active).lower() in {"1", "true", "yes"}:
            qs = qs.filter(is_active=True)
        elif str(active).lower() in {"0", "false", "no"}:
            qs = qs.filter(is_active=False)
        # любое иное значение — отдать все
        return qs

    @extend_schema(
        summary="Список услуг",
        parameters=[
            OpenApiParameter(
                name="active",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="1 — только активные (по умолчанию), 0 — только неактивные, пусто — все",
            ),
        ],
        responses=ServiceListSerializer(many=True),
        tags=["Services"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)