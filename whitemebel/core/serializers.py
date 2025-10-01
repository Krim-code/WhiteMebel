from django.conf import settings
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from decimal import Decimal
from core.models import DeliveryRegion, DeliveryDiscount
from core.models import ContactRequest
from core.utils.phone import normalize_ru_phone
from core.models import (
    MainSlider, Product, ProductImage, Tag, Color, Category,
    ProductAttributeValue
)
from rest_framework.generics import CreateAPIView
from django.urls import reverse

from decimal import ROUND_HALF_UP
from typing import List, Dict
from django.utils import timezone
from core.models import (
    Order, OrderItem, OrderService, Service
)
from django.db import models
import re
from django.db import transaction
from django.db.models import Q
from core.emails import send_order_notifications
class CategoryBriefSerializer(serializers.ModelSerializer):
    parent_slug = serializers.SlugRelatedField(
        read_only=True, source="parent", slug_field="slug"
    )
    level = serializers.IntegerField(read_only=True)
    products_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent", "parent_slug", "is_featured", "level", "products_count")


class CategoryNodeSerializer(CategoryBriefSerializer):
    children = serializers.SerializerMethodField()

    @extend_schema_field(CategoryBriefSerializer(many=True))
    def get_children(self, obj):
        depth = self.context.get("depth", 0)
        if depth <= 0:
            return []
        qs = obj.children.all()
        # передаём контекст с уменьшенной глубиной
        ser = CategoryNodeSerializer(qs, many=True, context={**self.context, "depth": depth - 1})
        return ser.data

    class Meta(CategoryBriefSerializer.Meta):
        fields = CategoryBriefSerializer.Meta.fields + ("children",)





class RangeSerializer(serializers.Serializer):
    title = serializers.CharField()
    min = serializers.FloatField(allow_null=True)
    max = serializers.FloatField(allow_null=True)

class ColorFacetItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    title = serializers.CharField()
    hex_code = serializers.CharField()
    count = serializers.IntegerField()

class TagFacetItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    title = serializers.CharField()
    slug = serializers.SlugField()
    count = serializers.IntegerField()

class AttributeOptionFacetSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    value = serializers.CharField()
    title = serializers.CharField()
    count = serializers.IntegerField()

class AttributeFacetSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    title = serializers.CharField()
    slug = serializers.SlugField()
    filter_widget = serializers.CharField()
    is_multiselect = serializers.BooleanField()
    filter_order = serializers.IntegerField()
    options = AttributeOptionFacetSerializer(many=True)

class FiltersResponseSerializer(serializers.Serializer):
    category = serializers.CharField(allow_null=True)
    include_descendants = serializers.BooleanField()
    total_products = serializers.IntegerField()
    ranges = serializers.DictField(child=RangeSerializer())
    colors = ColorFacetItemSerializer(many=True)
    tags = TagFacetItemSerializer(many=True)
    # было: attributes = AttributeFacetSerializer(many=True)
    attributes = serializers.DictField(child=AttributeFacetSerializer())
    titles = serializers.DictField(child=serializers.CharField(), required=False)



class ProductListSerializer(serializers.ModelSerializer):
    color_name = serializers.CharField(source="color.name", read_only=True)
    color_hex = serializers.CharField(source="color.hex_code", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "title", "slug", "price", "discount_price", "discount_percent",
            "sku", "image", "is_active", "stock",
            "width", "height", "depth",
            "color", "color_name", "color_hex",
            "category", "category_slug",
            "created_at",
        )


class TagSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Tag
        fields = ("id", "name", "slug", "show_on_home", "product_count")

# core/serializers.py


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "alt_text")

class TagBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ("id", "name", "slug")

class ColorBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Color
        fields = ("id", "name", "hex_code")

class CategoryCrumbSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug")

class AttributeKVSerializer(serializers.ModelSerializer):
    attribute_id = serializers.IntegerField(source="attribute.id", read_only=True)
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)
    attribute_slug = serializers.CharField(source="attribute.slug", read_only=True)
    option_id = serializers.IntegerField(source="option.id", read_only=True)
    option_value = serializers.CharField(source="option.value", read_only=True)

    class Meta:
        model = ProductAttributeValue
        fields = ("attribute_id", "attribute_name", "attribute_slug",
                  "option_id", "option_value")

class RelatedProductSerializer(serializers.ModelSerializer):
    color = ColorBriefSerializer(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = ("id", "title", "slug", "price", "discount_price", "discount_percent",
                  "image", "color")


class ProductDetailSerializer(serializers.ModelSerializer):
    color = ColorBriefSerializer(read_only=True)
    category = CategoryCrumbSerializer(read_only=True)
    breadcrumbs = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)
    tags = TagBriefSerializer(many=True, read_only=True)
    attributes = AttributeKVSerializer(many=True, read_only=True)
    related_products = serializers.SerializerMethodField()
    related_by_color = serializers.SerializerMethodField()
    discount_percent = serializers.IntegerField(read_only=True)
    effective_price = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id", "title", "slug", "description",
            "price", "discount_price", "discount_percent", "effective_price",
            "sku", "is_active", "in_stock", "stock",
            "width", "height", "depth",
            "color", "category", "breadcrumbs",
            "image", "images", "tags", "attributes",
            "created_at", "updated_at",
            "related_products", "related_by_color",
        )

    def get_effective_price(self, obj):
        if obj.discount_price and obj.discount_price < obj.price:
            return obj.discount_price
        return obj.price

    def get_in_stock(self, obj):
        return obj.stock > 0

    def get_breadcrumbs(self, obj):
        if not obj.category_id:
            return []
        # ancestors + self
        nodes = obj.category.get_ancestors(include_self=True)
        return CategoryCrumbSerializer(nodes, many=True).data

    def _limit(self, key, default):
        try:
            return max(0, int(self.context.get(key, default)))
        except Exception:
            return default

    def get_related_products(self, obj):
        limit = self._limit("related_limit", 8)
        qs = obj.related_products.all()
        if limit:
            qs = qs[:limit]
        # карточки ТОЧНО как в /api/products
        return ProductListSerializer(qs, many=True, context=self.context).data

    def get_related_by_color(self, obj):
        limit = self._limit("related_by_color_limit", 8)
        qs = obj.related_by_color.all()
        if limit:
            qs = qs[:limit]
        return ProductListSerializer(qs, many=True, context=self.context).data
    
    # core/serializers.py (добавь в конец рядом с ProductListSerializer)
class ProductListPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = ProductListSerializer(many=True)
    # тот же формат, что отдаёт /api/filters/
    filters = FiltersResponseSerializer()




# core/serializers.py
class MainSliderSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = MainSlider
        fields = ("id", "title", "link", "order", "is_active", "image", "image_url")

    def get_image_url(self, obj):
        req = self.context.get("request")
        if not obj.image:
            return None
        return req.build_absolute_uri(obj.image.url) if req else obj.image.url


class DeliveryDiscountBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    discount_type = serializers.CharField()
    value = serializers.DecimalField(max_digits=10, decimal_places=2)

class DeliveryRegionCostSerializer(serializers.ModelSerializer):
    # динамика
    base_cost_effective = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    final_cost = serializers.SerializerMethodField()
    applied_discount = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryRegion
        fields = (
            "id", "name", "slug",
            "base_cost", "free_threshold",
            "delivery_days_min", "delivery_days_max",
            "is_active", "order",
            "base_cost_effective", "discount_amount", "final_cost",
            "applied_discount",
        )

    # --- helpers ---
    def _get_ctx_decimal(self, key: str, default="0"):
        from decimal import Decimal
        try:
            v = self.context.get(key)
            if v is None: return Decimal(default)
            return Decimal(str(v))
        except Exception:
            return Decimal(default)

    def _best_discount(self, region: DeliveryRegion, base_cost: Decimal, order_total: Decimal):
        """
        Выбираем скидку с максимальной выгодой среди:
        - скидок конкретного региона
        - глобальных скидок (region is null)
        """
        discounts_qs = self.context.get("discounts_qs")
        if discounts_qs is None:
            discounts_qs = DeliveryDiscount.objects.filter(is_active=True).select_related("region")

        best = {"amount": Decimal("0.00"), "obj": None}
        for d in discounts_qs:
            # область действия
            if d.region_id not in (None, region.id):
                continue
            amt = d.calc_discount_amount(base_cost, order_total)
            if amt > best["amount"]:
                best = {"amount": amt, "obj": d}
        return best

    # --- SDFs ---
    def get_base_cost_effective(self, obj: DeliveryRegion):
        order_total = self._get_ctx_decimal("order_total", "0")
        return obj.calc_base_cost(order_total)

    def get_discount_amount(self, obj: DeliveryRegion):
        order_total = self._get_ctx_decimal("order_total", "0")
        base_cost = self.get_base_cost_effective(obj)
        if base_cost <= 0:
            return Decimal("0.00")
        best = self._best_discount(obj, base_cost, order_total)
        return best["amount"]

    def get_final_cost(self, obj: DeliveryRegion):
        base_cost = self.get_base_cost_effective(obj)
        if base_cost <= 0:
            return base_cost
        return (base_cost - self.get_discount_amount(obj)).quantize(Decimal("0.01"))

    def get_applied_discount(self, obj: DeliveryRegion):
        # можно выключить деталь через context["detailed"]=False
        if not self.context.get("detailed", True):
            return None
        order_total = self._get_ctx_decimal("order_total", "0")
        base_cost = self.get_base_cost_effective(obj)
        if base_cost <= 0:
            return None
        best = self._best_discount(obj, base_cost, order_total)
        if best["amount"] <= 0 or not best["obj"]:
            return None
        d: DeliveryDiscount = best["obj"]
        return DeliveryDiscountBriefSerializer({
            "id": d.id, "title": d.title, "discount_type": d.discount_type, "value": d.value
        }).data
        
class ProductsByIdsResponseSerializer(serializers.Serializer):
    results = ProductListSerializer(many=True)
    missing = serializers.ListField(child=serializers.IntegerField(), default=[])
    

class ContactRequestCreateSerializer(serializers.ModelSerializer):
    
    phone = serializers.CharField(write_only=True, trim_whitespace=True)
    class Meta:
        model = ContactRequest
        fields = ("id", "name", "phone", "created_at")
        read_only_fields = ("id", "created_at")

    def validate_name(self, v):
        v = (v or "").strip()
        if len(v) < 2:
            raise serializers.ValidationError("Имя слишком короткое.")
        return v

    def validate_phone(self, v):
        return normalize_ru_phone(v)

    def create(self, validated_data):
        # phone уже нормализован, сохраняем
        return super().create(validated_data)


# ==========================
# helpers
# ==========================

_MONEY_Q = Decimal("0.01")


def money(val) -> Decimal:
    """Округление денег до 2 знаков (банковское)."""
    return (Decimal(val).quantize(_MONEY_Q, rounding=ROUND_HALF_UP)
            if not isinstance(val, Decimal) else val.quantize(_MONEY_Q))


def normalize_ru_phone(raw: str) -> str:
    """
    Нормализация российского номера:
    - вход: '+7 999 123-45-67', '8(999)1234567', '9991234567'
    - выход: '+79991234567'
    """
    if not raw:
        raise serializers.ValidationError("Телефон обязателен.")
    digits = re.sub(r"\D+", "", raw)

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    elif len(digits) == 11 and digits.startswith("7"):
        pass
    else:
        raise serializers.ValidationError("Неверный формат телефона. Ожидаю российский номер.")

    return f"+{digits}"


def product_effective_price(p: Product) -> Decimal:
    if p.discount_price and p.discount_price < p.price:
        return money(p.discount_price)
    return money(p.price)


def calc_delivery(order_total: Decimal, *, region_slug: str | None, delivery_type: str) -> tuple[Decimal, Decimal, Decimal]:
    """
    Возвращает (base, discount, cost).
    - Самовывоз: всё 0.
    - Доставка: base по региону (учитывая free_threshold), discount — лучшая действующая скидка.
    """
    if delivery_type == "pickup":
        return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")

    if not region_slug:
        raise serializers.ValidationError({"region": "Не указан регион доставки."})

    try:
        region = DeliveryRegion.objects.get(slug=region_slug, is_active=True)
    except DeliveryRegion.DoesNotExist:
        raise serializers.ValidationError({"region": "Регион доставки не найден или неактивен."})

    base = money(region.calc_base_cost(order_total))

    # Лучший (максимальный) дисконт
    now = timezone.now()
    discounts = DeliveryDiscount.objects.filter(
        is_active=True
    ).filter(
        Q(region__isnull=True) | Q(region=region)
    ).filter(
        Q(active_from__isnull=True) | Q(active_from__lte=now),
        Q(active_to__isnull=True) | Q(active_to__gte=now),
    )

    best = Decimal("0.00")
    for d in discounts:
        amt = d.calc_discount_amount(delivery_cost=base, order_total=order_total)
        if amt > best:
            best = amt

    cost = base - best
    if cost < 0:
        cost = Decimal("0.00")
    return money(base), money(best), money(cost)


# ==========================
# input serializers
# ==========================

class OrderItemInSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, max_value=999)

    def validate(self, data):
        pid = data["product_id"]
        qty = data["quantity"]

        try:
            p = Product.objects.get(pk=pid, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"product_id": "Товар не найден или неактивен."})

        # Если надо — контролируй склад
        if p.stock is not None and p.stock < qty:
            raise serializers.ValidationError({"quantity": f"Недостаточно на складе (в наличии: {p.stock})."})

        data["_product"] = p  # прокинем внутрь, чтобы не дергать БД ещё раз
        return data


class OrderServiceInSerializer(serializers.Serializer):
    service_id = serializers.IntegerField()

    def validate_service_id(self, pk):
        if not Service.objects.filter(pk=pk, is_active=True).exists():
            raise serializers.ValidationError("Услуга не найдена или неактивна.")
        return pk


# ==========================
# output brief serializers
# ==========================

class OrderItemBriefSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    product_image = serializers.ImageField(source="product.image", read_only=True)

    class Meta:
        model = OrderItem
        fields = ("product_id", "product_title", "product_slug", "product_image",
                  "quantity", "price_at_moment", "final_price")


class OrderServiceBriefSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source="service.name", read_only=True)

    class Meta:
        model = OrderService
        fields = ("service_id", "service_name", "price_at_moment")


# ==========================
# main serializer
# ==========================

class OrderCreateSerializer(serializers.ModelSerializer):
    """
    ВХОД:
    {
      "full_name": "...",
      "phone": "...",
      "email": "...",                // опционально
      "city": "...",
      "address": "...",
      "comment": "...",              // опционально
      "payment_method": "online|cod",
      "delivery_type": "delivery|pickup",
      "region": "moscow-mo",         // обязателен при delivery
      "items": [{"product_id": 1, "quantity": 2}, ...],
      "services": [{"service_id": 1}, ...] // опционально
    }

    ВЫХОД: объект заказа + рассчитанные суммы и брифы позиций/услуг.
    """
    # вход
    items = OrderItemInSerializer(many=True, write_only=True)
    services = OrderServiceInSerializer(many=True, required=False, write_only=True)
    region = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # выход (read-only)
    items_brief = OrderItemBriefSerializer(many=True, read_only=True, source="items")
    services_brief = OrderServiceBriefSerializer(many=True, read_only=True, source="orderservice_set")

    subtotal = serializers.SerializerMethodField()
    services_total = serializers.SerializerMethodField()
    delivery_base = serializers.SerializerMethodField()
    delivery_discount = serializers.SerializerMethodField()
    delivery_cost = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "full_name", "phone", "email",
            "city", "address", "comment",
            "payment_method", "delivery_type",
            "region",          # write-only
            "items", "services",  # write-only
            "total_price", "status", "created_at",

            # read-only детализация
            "items_brief", "services_brief",
            "subtotal", "services_total",
            "delivery_base", "delivery_discount", "delivery_cost",
        )
        read_only_fields = ("id", "status", "created_at",
                            "total_price",
                            "items_brief", "services_brief",
                            "subtotal", "services_total",
                            "delivery_base", "delivery_discount", "delivery_cost")

    # ----- field-level -----
    def validate_phone(self, v: str) -> str:
        return normalize_ru_phone(v)

    def validate_payment_method(self, v: str) -> str:
        allowed = {c[0] for c in Order.PAYMENT_CHOICES}
        if v not in allowed:
            raise serializers.ValidationError("Некорректный способ оплаты.")
        return v

    def validate_delivery_type(self, v: str) -> str:
        allowed = {c[0] for c in Order.DELIVERY_CHOICES}
        if v not in allowed:
            raise serializers.ValidationError("Некорректный тип доставки.")
        return v

    def validate(self, data):
        # При delivery должен прийти region
        if data.get("delivery_type") == "delivery" and not data.get("region"):
            raise serializers.ValidationError({"region": "Укажи регион доставки."})
        # Позиции обязательны
        if not data.get("items"):
            raise serializers.ValidationError({"items": "Корзина пуста."})
        return data

    # ----- create -----
    @transaction.atomic
    def create(self, validated):
        items_in = validated.pop("items")
        services_in = validated.pop("services", [])
        region_slug = validated.pop("region", "").strip() or None

        # создаём с total_price=0.00, чтобы пройти NOT NULL
        order = Order.objects.create(total_price=Decimal("0.00"), **validated)

        # items
        subtotal = Decimal("0.00")
        bulk_items = []
        for it in items_in:
            p = it["_product"]
            qty = it["quantity"]
            price = product_effective_price(p)
            final = money(price * qty)
            subtotal += final
            bulk_items.append(OrderItem(
                order=order, product=p, quantity=qty,
                price_at_moment=price, final_price=final
            ))
        if bulk_items:
            OrderItem.objects.bulk_create(bulk_items)

        # services (через through, без order.services.add)
        services_total = Decimal("0.00")
        bulk_services = []
        if services_in:
            svc_by_id = {s.id: s for s in Service.objects.filter(
                id__in=[x["service_id"] for x in services_in], is_active=True
            )}
            for s in services_in:
                sid = s["service_id"]
                svc = svc_by_id.get(sid)
                if not svc:
                    raise serializers.ValidationError({"services": f"Услуга {sid} не найдена/неактивна."})
                services_total += money(svc.price)
                bulk_services.append(OrderService(order=order, service=svc, price_at_moment=money(svc.price)))
        if bulk_services:
            OrderService.objects.bulk_create(bulk_services)

        # delivery
        delivery_base = delivery_discount = delivery_cost = Decimal("0.00")
        if order.delivery_type == "delivery":
            delivery_base, delivery_discount, delivery_cost = calc_delivery(
                order_total=money(subtotal + services_total),
                region_slug=region_slug,
                delivery_type=order.delivery_type,
            )

        # итог и сохранение
        total = money(subtotal + services_total + delivery_cost)
        order.total_price = total
        order.save(update_fields=["total_price"])

        # для ответа
        order._subtotal = subtotal
        order._services_total = services_total
        order._delivery_base = delivery_base
        order._delivery_discount = delivery_discount
        order._delivery_cost = delivery_cost
        transaction.on_commit(lambda: send_order_notifications(order))
        return order

    # ----- read-only computed -----
    def _sum_items(self, order: Order) -> Decimal:
        if hasattr(order, "_subtotal"):
            return order._subtotal
        return (order.items.aggregate(s=models.Sum("final_price"))["s"] or Decimal("0.00"))

    def _sum_services(self, order: Order) -> Decimal:
        if hasattr(order, "_services_total"):
            return order._services_total
        return (order.orderservice_set.aggregate(s=models.Sum("price_at_moment"))["s"] or Decimal("0.00"))

    def get_subtotal(self, obj: Order) -> Decimal:
        return money(self._sum_items(obj))

    def get_services_total(self, obj: Order) -> Decimal:
        return money(self._sum_services(obj))

    def get_delivery_base(self, obj: Order) -> Decimal:
        return money(getattr(obj, "_delivery_base", Decimal("0.00")))

    def get_delivery_discount(self, obj: Order) -> Decimal:
        return money(getattr(obj, "_delivery_discount", Decimal("0.00")))

    def get_delivery_cost(self, obj: Order) -> Decimal:
        return money(getattr(obj, "_delivery_cost", Decimal("0.00")))
    
class OrderCreateView(CreateAPIView):
    serializer_class = OrderCreateSerializer
    queryset = Order.objects.all()

    def create(self, request, *args, **kwargs):
        resp = super().create(request, *args, **kwargs)
        order_id = resp.data.get("id")
        pay_url = request.build_absolute_uri(reverse("cp-pay", args=[order_id]))
        resp.data["payment_url"] = pay_url
        # По желанию — сразу JSON для открытия виджета на фронте:
        resp.data["payment_init"] = {
            "public_id": settings.CLOUDPAYMENTS_PUBLIC_ID,
            "amount": float(resp.data.get("total_price")),
            "currency": "RUB",
            "invoice_id": str(order_id),
            "description": f"Оплата заказа #{order_id} на WhiteMebel",
        }
        return resp

class OrderStatusResponseSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    status = serializers.CharField()  # new|paid|canceled|...
    paid = serializers.BooleanField()

class CloudPaymentsInitResponseSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    public_id = serializers.CharField()
    amount = serializers.FloatField()
    currency = serializers.CharField()
    account_id = serializers.CharField()
    description = serializers.CharField()
    status_api = serializers.URLField()
    success_url = serializers.URLField()
    fail_url = serializers.URLField()
    pay_url = serializers.URLField()


class OrderCreatedSerializer(serializers.ModelSerializer):
    payment = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ("id", "status", "total_price", "payment")

    def get_payment(self, obj):
        request = self.context.get("request")
        if not request:
            return None
        data = {
            "status_api": request.build_absolute_uri(reverse("order-status", args=[obj.id])),
        }
        # Только если онлайн-оплата
        if obj.payment_method == "online":
            data.update({
                "pay_url": request.build_absolute_uri(reverse("cp-pay",  args=[obj.id])),
                "init_api": request.build_absolute_uri(reverse("cp-init", args=[obj.id])),
            })
        return data
    
class ServiceListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ("id", "name", "price")
        
        
class CloudPaymentsWebhookIn(serializers.Serializer):
    NotificationType = serializers.CharField()
    Amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    Currency = serializers.CharField()
    InvoiceId = serializers.CharField(required=False, allow_blank=True)
    InvoiceID = serializers.CharField(required=False, allow_blank=True)
    TransactionId = serializers.CharField(required=False, allow_blank=True)
    TransactionID = serializers.CharField(required=False, allow_blank=True)
    Data = serializers.DictField(required=False)

class CloudPaymentsWebhookOut(serializers.Serializer):
    code = serializers.IntegerField()
    message = serializers.CharField()
