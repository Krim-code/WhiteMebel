from django import forms
from django.contrib import admin
from .models import (
    AttributeOption,
    DeliveryDiscount,
    DeliveryRegion,
    MainSlider,
    Order,
    OrderItem,
    OrderService,
    Product,
    ProductImage,
    ProductAttribute,
    ProductAttributeValue,
    Service,
    Tag,
    Color,
    Category,
    Collection,
    User,
    ContactRequest
    
)
from django.utils.html import format_html
from mptt.admin import DraggableMPTTAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("name", "hex_code")
    search_fields = ("name",)

    # Виджет с color picker — хак через formfield
    def formfield_for_dbfield(self, db_field, **kwargs):
        field = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == 'hex_code':
            field.widget.input_type = 'color'
        return field


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 50px;" />', obj.image.url)
        return "-"
    image_preview.short_description = "Превью изображения"

class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "price", "discount_price", "stock", "is_active", "color")
    list_filter = ("is_active", "tags", "color")
    search_fields = ("title", "description", "sku")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ProductImageInline, ProductAttributeValueInline]
    filter_horizontal = ("tags", "related_by_color")
    readonly_fields = ("created_at", "updated_at")
    
    save_on_top = True
    list_per_page = 25

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "show_on_home")
    list_editable = ("show_on_home",)
    search_fields = ("name", "slug")
    list_filter = ("show_on_home",)


class AttributeOptionInline(admin.TabularInline):
    model = AttributeOption
    extra = 1

@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "filter_widget", "is_multiselect", "show_in_filter", "filter_order")
    list_editable = ("filter_widget", "is_multiselect", "show_in_filter", "filter_order")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class ProductAttributeValueForm(forms.ModelForm):
    class Meta:
        model = ProductAttributeValue
        fields = ("attribute", "option")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        attr_id = (self.data.get(self.add_prefix("attribute"))
                   or self.initial.get("attribute")
                   or (self.instance.attribute_id if self.instance.pk else None))
        qs = AttributeOption.objects.none()
        if attr_id:
            qs = AttributeOption.objects.filter(attribute_id=attr_id)
        self.fields["option"].queryset = qs

class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    form = ProductAttributeValueForm
    extra = 1
    autocomplete_fields = ("attribute", "option")
@admin.register(Category)
class CategoryAdmin(DraggableMPTTAdmin):
    prepopulated_fields = {'slug': ('name',)}
    
@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug')
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('title',)
    filter_horizontal = ('products',)
    
    
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'phone', 'is_staff', 'created_at')
    list_filter = ('is_staff', 'is_active')
    ordering = ('-created_at',)
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Личная информация', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Права', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Дополнительно', {'fields': ('last_login',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_active', 'is_staff', 'is_superuser')}
        ),
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderServiceInline(admin.TabularInline):
    model = OrderService
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'phone', 'status', 'total_price', 'created_at')
    list_filter = ('status', 'payment_method', 'delivery_type')
    search_fields = ('full_name', 'phone', 'email')
    date_hierarchy = 'created_at'
    inlines = [OrderItemInline, OrderServiceInline]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'is_active')
    search_fields = ('name',)
    
    
@admin.register(MainSlider)
class MainSliderAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'preview', 'is_active', 'order')
    list_editable = ('is_active', 'order')
    readonly_fields = ('preview',)

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 60px; border-radius:4px;" />', obj.image.url)
        return "-"
    preview.short_description = "Превью"
    
# core/admin.py


@admin.register(DeliveryRegion)
class DeliveryRegionAdmin(admin.ModelAdmin):
    list_display = ("name", "base_cost", "free_threshold",
                    "delivery_days_min", "delivery_days_max", "is_active", "order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")

@admin.register(DeliveryDiscount)
class DeliveryDiscountAdmin(admin.ModelAdmin):
    list_display = ("title", "region", "discount_type", "value",
                    "min_order_total", "active_from", "active_to", "is_active")
    list_filter = ("discount_type", "is_active", "region")
    search_fields = ("title",)


@admin.register(ContactRequest)
class ContactRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "created_at", "processed")
    list_filter = ("processed", "created_at")
    search_fields = ("name", "phone")
    list_editable = ("processed",)
