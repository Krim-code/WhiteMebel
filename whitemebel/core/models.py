from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from .utils.image import compress_image

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
    name = models.CharField("Название характеристики", max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Характеристика"
        verbose_name_plural = "Характеристики"


class ProductAttributeValue(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='attributes')
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE)
    value = models.CharField("Значение", max_length=255)

    def __str__(self):
        return f"{self.product.title} — {self.attribute.name}: {self.value}"

    class Meta:
        verbose_name = "Значение характеристики"
        verbose_name_plural = "Характеристики товара"
        

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
    

