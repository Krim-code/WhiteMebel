# core/serializers.py
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from decimal import Decimal
from core.models import DeliveryRegion, DeliveryDiscount

from core.models import (
    MainSlider, Product, ProductImage, Tag, Color, Category,
    ProductAttributeValue
)

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
    min = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    max = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)

class FilterColorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    hex_code = serializers.CharField()
    count = serializers.IntegerField()

class FilterTagSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    count = serializers.IntegerField()

class FilterOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    value = serializers.CharField()
    count = serializers.IntegerField()

class AttributeFilterSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.CharField()
    filter_widget = serializers.CharField()
    is_multiselect = serializers.BooleanField()
    filter_order = serializers.IntegerField()
    options = FilterOptionSerializer(many=True)

class FiltersResponseSerializer(serializers.Serializer):
    category = serializers.CharField(allow_null=True)
    include_descendants = serializers.BooleanField()
    total_products = serializers.IntegerField()
    ranges = serializers.DictField(child=RangeSerializer())
    colors = FilterColorSerializer(many=True)
    tags = FilterTagSerializer(many=True)
    attributes = AttributeFilterSerializer(many=True)




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
        qs = obj.related_products.filter(is_active=True).select_related("color").only(
            "id", "title", "slug", "price", "discount_price", "image", "color_id"
        )
        if limit:
            qs = qs[:limit]
        return RelatedProductSerializer(qs, many=True, context=self.context).data

    def get_related_by_color(self, obj):
        limit = self._limit("related_by_color_limit", 8)
        qs = obj.related_by_color.filter(is_active=True).select_related("color").only(
            "id", "title", "slug", "price", "discount_price", "image", "color_id"
        )
        if limit:
            qs = qs[:limit]
        return RelatedProductSerializer(qs, many=True, context=self.context).data
    
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