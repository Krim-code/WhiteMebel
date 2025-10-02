from django.db import models
from django.forms import ValidationError
from mptt.models import MPTTModel, TreeForeignKey
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
import slugify

from core.utils.slug import ascii_slug
from .utils.image import compress_image
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('У юзера должен быть email')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("Email", unique=True)
    first_name = models.CharField("Имя", max_length=150, blank=True)
    last_name = models.CharField("Фамилия", max_length=150, blank=True)
    phone = models.CharField("Телефон", max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return self.email


class Category(MPTTModel):
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Слаг", max_length=255, unique=True)
    parent = TreeForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name="Родительская категория"
    )
    is_featured = models.BooleanField("Популярная", default=False)
    class MPTTMeta:
        order_insertion_by = ['name']

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name
    
class Color(models.Model):
    name = models.CharField("Название цвета", max_length=50, unique=True)
    hex_code = models.CharField("HEX-код", max_length=7, default="#ffffff")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Цвет"
        verbose_name_plural = "Цвета"
        
class Tag(models.Model):
    name = models.CharField("Название тега", max_length=100, unique=True)
    slug = models.SlugField("Слаг", max_length=100, unique=True)
    show_on_home = models.BooleanField("Показывать на главной", default=False, db_index=True)  # <—

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Тег"
        verbose_name_plural = "Теги"


class Product(models.Model):
    title = models.CharField("Название", max_length=255)
    slug = models.SlugField("Слаг", max_length=255, unique=True)
    description = models.TextField("Описание", blank=True)
    price = models.DecimalField("Цена", max_digits=10, decimal_places=2)
    discount_price = models.DecimalField("Цена со скидкой", max_digits=10, decimal_places=2, null=True, blank=True)
    sku = models.CharField("Артикул", max_length=64, unique=True)
    is_active = models.BooleanField("Активен", default=True)
    stock = models.PositiveIntegerField("Остаток", default=0)
    image = models.ImageField("Главное изображение", upload_to="products/", blank=True, null=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='products')
    width = models.DecimalField("Ширина (см)", max_digits=6, decimal_places=2, null=True, blank=True)
    height = models.DecimalField("Высота (см)", max_digits=6, decimal_places=2, null=True, blank=True)
    depth = models.DecimalField("Глубина (см)", max_digits=6, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Цвет")
    related_by_color = models.ManyToManyField("self", blank=True, verbose_name="Связанные по цвету", symmetrical=False)
    related_products = models.ManyToManyField(
        'self',
        verbose_name="Связанные товары",
        blank=True,
        symmetrical=False,
        related_name='related_to'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Категория",
        related_name="products"
    )

    def __str__(self):
        return self.title

    @property
    def discount_percent(self):
        if self.discount_price and self.discount_price < self.price:
            return round(100 - (self.discount_price / self.price * 100))
        return 0

    def has_discount(self):
        return self.discount_percent > 0

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        
    def save(self, *args, **kwargs):
        if self.image:
            self.image = compress_image(self.image, format="WEBP", quality=80)
        super().save(*args, **kwargs)


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_images/')
    alt_text = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Image for {self.product.title}"
    
    def save(self, *args, **kwargs):
        if self.image:
            self.image = compress_image(self.image, format="WEBP", quality=80)
        super().save(*args, **kwargs)


class ProductAttribute(models.Model):
    class FilterWidget(models.TextChoices):
        SELECT   = "select",   "Выпадающий список"
        CHECKBOX = "checkbox", "Чекбоксы"
        RADIO    = "radio",    "Радио-кнопки"
        CHIPS    = "chips",    "Чипсы/тэги"
        SWATCH   = "swatch",   "Сэмплы цвета"
        SLIDER   = "slider",   "Слайдер (число)"
        RANGE    = "range",    "Диапазон (число)"

    name = models.CharField("Название характеристики", max_length=100, unique=True)
    slug = models.SlugField("Слаг", max_length=120, blank=True, unique=True)
    filter_widget = models.CharField("Стиль фильтра", max_length=16,
                                     choices=FilterWidget.choices, default=FilterWidget.CHECKBOX)
    is_multiselect = models.BooleanField("Мультивыбор", default=True)
    show_in_filter = models.BooleanField("Показывать в фильтре", default=True)
    filter_order = models.PositiveSmallIntegerField("Порядок в фильтре", default=0)

    class Meta:
        verbose_name = "Характеристика"
        verbose_name_plural = "Характеристики"
        ordering = ("filter_order", "name")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = ascii_slug(self.name)
        super().save(*args, **kwargs)

class AttributeOption(models.Model):
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name="options")
    value = models.CharField("Значение", max_length=255)

    class Meta:
        verbose_name = "Опция характеристики"
        verbose_name_plural = "Опции характеристик"
        unique_together = (("attribute", "value"),)
        ordering = ["attribute__name", "value"]

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"


class ProductAttributeValue(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='attributes')
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE)
    option = models.ForeignKey(AttributeOption, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        verbose_name = "Значение характеристики"
        verbose_name_plural = "Характеристики товара"
        unique_together = (("product", "attribute", "option"),)
        indexes = [
            models.Index(fields=["product", "attribute"]),
        ]

    def __str__(self):
        return f"{self.product.title} — {self.attribute.name}: {self.option.value}"

    def clean(self):
        if self.option and self.attribute_id != self.option.attribute_id:
            raise ValidationError("Опция не принадлежит выбранной характеристике.")
        

class Collection(models.Model):
    title = models.CharField("Название коллекции", max_length=255)
    slug = models.SlugField("Слаг", max_length=255, unique=True)
    description = models.TextField("Описание", blank=True)
    products = models.ManyToManyField('Product', related_name='collections', verbose_name="Товары")

    class Meta:
        verbose_name = "Коллекция"
        verbose_name_plural = "Коллекции"

    def __str__(self):
        return self.title

class Service(models.Model):
    name = models.CharField("Название услуги", max_length=255)
    description = models.TextField("Описание", blank=True)
    price = models.DecimalField("Стоимость", max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"



class Order(models.Model):
    STATUS_CHOICES = [
        ('new', 'Новый'),
        ('paid', 'Оплачен'),
        ('shipped', 'Отправлен'),
        ('delivered', 'Доставлен'),
        ('canceled', 'Отменён'),
    ]
    PAYMENT_CHOICES = [
        ('online', 'Онлайн'),
        ('cod', 'При получении'),
    ]
    DELIVERY_CHOICES = [
        ('delivery', 'Доставка'),
        ('pickup', 'Самовывоз'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    full_name = models.CharField("ФИО", max_length=255)
    phone = models.CharField("Телефон", max_length=20)
    email = models.EmailField("Email", blank=True)
    city = models.CharField("Город", max_length=100)
    address = models.TextField("Адрес")
    comment = models.TextField("Комментарий", blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES)
    delivery_type = models.CharField(max_length=20, choices=DELIVERY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    total_price = models.DecimalField("Сумма заказа", max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    services = models.ManyToManyField('Service', through='OrderService', blank=True, related_name='orders')

    def __str__(self):
        return f"Заказ #{self.id} от {self.full_name}"
    
    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"

class OrderService(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    price_at_moment = models.DecimalField("Цена услуги на момент заказа", max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.service.name} для заказа #{self.order.id}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField(default=1)
    price_at_moment = models.DecimalField(max_digits=10, decimal_places=2)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product} x {self.quantity}"
    
class MainSlider(models.Model):
    image = models.ImageField("Картинка", upload_to="main_slider/")
    link = models.URLField("Ссылка", blank=True, help_text="Ссылка при клике на слайд")
    title = models.CharField("Заголовок", max_length=255, blank=True)
    is_active = models.BooleanField("Активен", default=True)
    order = models.PositiveIntegerField("Порядок", default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order']
        verbose_name = "Слайд"
        verbose_name_plural = "Слайдер на главной"

    def __str__(self):
        return self.title or f"Слайд #{self.id}"
    
    def save(self, *args, **kwargs):
        if self.image:
            self.image = compress_image(self.image, format="WEBP", quality=80)
        super().save(*args, **kwargs)
    



class DeliveryRegion(models.Model):
    name = models.CharField("Регион", max_length=255, unique=True)
    slug = models.SlugField("Слаг", max_length=255, unique=True)
    base_cost = models.DecimalField("Базовая стоимость доставки",
                                    max_digits=10, decimal_places=2,
                                    validators=[MinValueValidator(Decimal("0"))])
    free_threshold = models.DecimalField("Порог бесплатной доставки",
                                         max_digits=10, decimal_places=2,
                                         null=True, blank=True,
                                         validators=[MinValueValidator(Decimal("0"))])
    delivery_days_min = models.PositiveSmallIntegerField("Срок (мин, дней)", default=1)
    delivery_days_max = models.PositiveSmallIntegerField("Срок (макс, дней)", default=3)
    is_active = models.BooleanField("Активен", default=True)
    order = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Регион доставки"
        verbose_name_plural = "Регионы доставки"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name

    def calc_base_cost(self, order_total: Decimal | float | int) -> Decimal:
        """Базовая стоимость с учётом порога бесплатной доставки."""
        total = Decimal(str(order_total))
        if self.free_threshold is not None and total >= self.free_threshold:
            return Decimal("0.00")
        return self.base_cost


class DeliveryDiscount(models.Model):
    TYPE_PERCENT = "percent"
    TYPE_FIXED = "fixed"
    TYPE_CHOICES = [
        (TYPE_PERCENT, "Процент"),
        (TYPE_FIXED, "Фикс"),
    ]

    title = models.CharField("Название", max_length=255)
    region = models.ForeignKey(
        DeliveryRegion,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="discounts",
        verbose_name="Регион (пусто = глобальная)"
    )
    discount_type = models.CharField("Тип скидки", max_length=10, choices=TYPE_CHOICES, default=TYPE_PERCENT)
    value = models.DecimalField("Величина скидки",
                                max_digits=7, decimal_places=2,
                                validators=[MinValueValidator(Decimal("0"))])
    min_order_total = models.DecimalField("Мин. сумма заказа",
                                          max_digits=10, decimal_places=2,
                                          null=True, blank=True,
                                          validators=[MinValueValidator(Decimal("0"))])
    active_from = models.DateTimeField("Активна с", null=True, blank=True)
    active_to = models.DateTimeField("Активна по", null=True, blank=True)
    is_active = models.BooleanField("Активна", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Скидка на доставку"
        verbose_name_plural = "Скидки на доставку"
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["active_from", "active_to"]),
        ]

    def __str__(self):
        scope = self.region.name if self.region else "Глобальная"
        return f"{self.title} ({scope})"

    def is_now_active(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.active_from and now < self.active_from:
            return False
        if self.active_to and now > self.active_to:
            return False
        return True

    def eligible(self, order_total: Decimal | float | int) -> bool:
        if self.min_order_total is None:
            return True
        return Decimal(str(order_total)) >= self.min_order_total

    def calc_discount_amount(self, delivery_cost: Decimal | float | int,
                             order_total: Decimal | float | int) -> Decimal:
        """
        Возвращает сумму скидки (не меньше 0 и не больше delivery_cost).
        Процент — от стоимости доставки.
        """
        if not self.is_now_active() or not self.eligible(order_total):
            return Decimal("0.00")

        cost = Decimal(str(delivery_cost))
        if cost <= 0:
            return Decimal("0.00")

        if self.discount_type == self.TYPE_PERCENT:
            # value в процентах: 0..100
            percent = max(Decimal("0"), min(Decimal("100"), self.value))
            amount = (cost * percent / Decimal("100")).quantize(Decimal("0.01"))
        else:
            amount = Decimal(str(self.value)).quantize(Decimal("0.01"))

        # Не уходим в минус
        return min(cost, max(Decimal("0.00"), amount))

class ContactRequest(models.Model):
    name = models.CharField("Имя", max_length=150)
    phone = models.CharField("Телефон (+7XXXXXXXXXX)", max_length=16, db_index=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    processed = models.BooleanField("Обработано", default=False)

    class Meta:
        verbose_name = "Обращение"
        verbose_name_plural = "Обращения"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} — {self.phone}"
    
    
class Payment(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        PAID = "paid", "Оплачен"        # для charge
        AUTHORIZED = "authorized", "Заблокирован"  # для auth, если пойдём в 2-стадийку
        FAILED = "failed", "Ошибка"
        REFUNDED = "refunded", "Возврат"
        CANCELED = "canceled", "Отменён"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="RUB")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)

    # CloudPayments поля
    transaction_id = models.CharField(max_length=64, blank=True)  # TransactionId
    invoice_id = models.CharField(max_length=64, blank=True)      # InvoiceId (обычно str(order.id))
    account_id = models.CharField(max_length=190, blank=True)     # email/phone/id пользователя

    card_first_six = models.CharField(max_length=6, blank=True)
    card_last_four = models.CharField(max_length=4, blank=True)
    card_type = models.CharField(max_length=32, blank=True)

    raw_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["invoice_id"]),
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"

    def __str__(self):
        return f"Payment #{self.id} for order #{self.order_id} [{self.status}]"
    
    
    
class OneClickRequest(models.Model):
    class Status(models.TextChoices):
        NEW        = "new",        "Новая"
        CONTACTED  = "contacted",  "Связались"
        ORDERED    = "ordered",    "Оформлен заказ"
        REJECTED   = "rejected",   "Отклонена"

    name         = models.CharField("Имя", max_length=150)
    phone        = models.CharField("Телефон", max_length=16, db_index=True)  # формат +7XXXXXXXXXX
    product_url  = models.URLField("Ссылка на товар", max_length=500)
    # опционально: если сможем распарсить slug — сохраним связь
    product      = models.ForeignKey("core.Product", null=True, blank=True,
                                     on_delete=models.SET_NULL, verbose_name="Товар")
    comment      = models.CharField("Комментарий", max_length=500, blank=True)
    status       = models.CharField("Статус", max_length=20, choices=Status.choices, default=Status.NEW)
    created_at   = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Заявка «в один клик»"
        verbose_name_plural = "Заявки «в один клик»"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} {self.phone} → {self.product or self.product_url}"