import random
from io import BytesIO
from pathlib import Path
from core.utils.slug import ascii_slug

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from faker import Faker
from PIL import Image, ImageDraw
import uuid
from django.db import IntegrityError, transaction
from django.core.management.base import CommandError

from core.models import (
    Category, Color, Tag, Product, ProductImage,
    ProductAttribute, AttributeOption, ProductAttributeValue,
    Collection, Service, MainSlider,
    DeliveryRegion, DeliveryDiscount
)

fake = Faker("ru_RU")

ROOT_CATS = [
    ("Шкафы-купе", ["Двухдверные", "Трёхдверные", "Угловые"]),
    ("Распашные шкафы", ["Двухдверные", "Четырёхдверные"]),
    ("Гардеробные", ["П-образные", "Угловые"]),
    ("Прихожие", ["Секции", "Комплекты"]),
    ("Аксессуары", ["Полки", "Корзины"]),
]

# имя: (опции, виджет, мульти?)
ATTRS = {
    "Материал": (["ЛДСП", "МДФ", "Дерево", "Металл", "Пластик"], "checkbox", True),
    "Тип дверей": (["Распашные", "Купе"], "radio", False),
    "Зеркало": (["Нет", "На одной двери", "На всех дверях"], "radio", False),
    "Стиль": (["Современный", "Классика", "Лофт", "Минимализм"], "chips", True),
    "Фурнитура": (["Blum", "Hettich", "Boyard"], "select", True),
}

COLORS = [
    ("Белый", "#FFFFFF"), ("Венге", "#4A2C2A"), ("Дуб Сонома", "#C0A078"),
    ("Чёрный", "#000000"), ("Серый", "#B0B0B0"), ("Графит", "#2F3136"),
]

TAGS = ["новинка", "хит", "распродажа", "эксклюзив", "индивидуальный-заказ"]

COLLECTIONS = ["Basic", "Premium", "Eco"]

SERVICES = [
    ("Доставка", 1500.00),
    ("Сборка", 2500.00),
]

REGIONS = [
    ("Москва и МО", "moscow-mo", 1500.00, 50000.00, (1, 3)),
    ("Санкт-Петербург", "spb", 1500.00, 50000.00, (2, 4)),
    ("ЦФО", "cfo", 2000.00, 60000.00, (3, 6)),
    ("Поволжье", "povolzhe", 2500.00, 70000.00, (4, 8)),
    ("Сибирь", "sibir", 4000.00, 90000.00, (6, 12)),
]

DISCOUNTS = [
    ("-10% на доставку всем", None, "percent", 10, 30000),
    ("-500₽ на доставку в МО", "moscow-mo", "fixed", 500, 0),
]


def make_placeholder_bytes(text="WhiteMebel"):
    img = Image.new("RGB", (1200, 800), (242, 242, 242))
    d = ImageDraw.Draw(img)
    d.rectangle([(10, 10), (1190, 790)], outline=(40, 40, 40), width=3)
    d.text((40, 40), text, fill=(30, 30, 30))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


IMG_BYTES = make_placeholder_bytes()


def cf(name="placeholder.jpg"):
    # каждый раз новый ContentFile, чтобы Django не ругался
    return ContentFile(IMG_BYTES, name=name)


def unique_slug(base, existing_qs, field="slug"):
    s = ascii_slug(base)
    if not s:
        s = "item"
    original = s
    i = 2
    while existing_qs.filter(**{field: s}).exists():
        s = f"{original}-{i}"
        i += 1
    return s



def make_sku(prefix="WM"):
    # Чисто цифры? Тогда оставляем паттерн
    return f"{prefix}-{random.randint(100000, 999999)}"

def generate_unique_sku(used, prefix="WM", max_tries=20):
    # 1) быстрые попытки в памяти + БД
    for _ in range(max_tries):
        sku = make_sku(prefix)
        if sku in used:
            continue
        if not Product.objects.filter(sku=sku).exists():
            used.add(sku)
            return sku
    # 2) fallback — вообще уникальный
    alt = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
    used.add(alt)
    return alt


class Command(BaseCommand):
    help = "Генерит тестовые данные для WhiteMebel (категории, товары, атрибуты, слайдеры и т.д.)"

    def add_arguments(self, parser):
        parser.add_argument("--products", type=int, default=150, help="Сколько товаров создать (100-200 ок)")
        parser.add_argument("--fresh", action="store_true", help="Очистить ключевые таблицы перед генерацией")

    def handle(self, *args, **opts):
        products_count = max(1, int(opts["products"]))
        fresh = opts["fresh"]

        if fresh:
            self.stdout.write("💣 Чищу данные…")
            ProductImage.objects.all().delete()
            ProductAttributeValue.objects.all().delete()
            Product.objects.all().delete()
            Tag.objects.all().delete()
            Color.objects.all().delete()
            AttributeOption.objects.all().delete()
            ProductAttribute.objects.all().delete()
            Collection.objects.all().delete()
            Service.objects.all().delete()
            MainSlider.objects.all().delete()
            DeliveryDiscount.objects.all().delete()
            DeliveryRegion.objects.all().delete()
            # категории трогаем последними
            Category.objects.all().delete()

        self.stdout.write("🌲 Категории…")
        for root_name, children in ROOT_CATS:
            root = Category.objects.create(
                name=root_name,
                slug=unique_slug(root_name, Category.objects),
                is_featured=random.choice([True, False, False]),
            )
            for child in children:
                Category.objects.create(
                    name=child,
                    slug=unique_slug(f"{root_name}-{child}", Category.objects),
                    parent=root,
                )
        # подправим MPTT индексы
        try:
            Category.objects.rebuild()
        except AttributeError:
            # старые/капризные версии
            Category._tree_manager.rebuild()

        self.stdout.write("🎨 Цвета…")
        for name, hx in COLORS:
            Color.objects.get_or_create(name=name, defaults={"hex_code": hx})

        self.stdout.write("🏷 Теги…")
        HOME_TAGS = {"новинка", "хит"}
        for t in TAGS:
            # первичный slug-кандидат (ASCII + уникальность против всей таблицы)
            slug_candidate = unique_slug(t, Tag.objects)

            tag, created = Tag.objects.get_or_create(
                name=t,
                defaults={
                    "slug": slug_candidate,
                    "show_on_home": (t in HOME_TAGS),
                },
            )
            if not created:
                # лечим пустые/кириллические/левые слаги у уже существующих тегов
                # важное: исключаем сам объект из выборки, чтобы не словить конфликт уникальности
                fixed_slug = unique_slug(tag.name, Tag.objects.exclude(pk=tag.pk))
                updates = []

                if not tag.slug or tag.slug != fixed_slug:
                    tag.slug = fixed_slug
                    updates.append("slug")

                # если флаг ещё не трогали — можно расставить дефолты (или пропусти, если не надо)
                if tag.show_on_home is None:  # на случай если в БД NULL
                    tag.show_on_home = (tag.name in HOME_TAGS)
                    updates.append("show_on_home")

                if updates:
                    tag.save(update_fields=updates)

        self.stdout.write("⚙️  Характеристики и опции…")
        attr_map = {}
        for idx, (attr_name, (options, widget, mult)) in enumerate(ATTRS.items()):
            attr, created = ProductAttribute.objects.get_or_create(
                name=attr_name,
                defaults={
                    "filter_widget": widget,
                    "is_multiselect": mult,
                    "show_in_filter": True,
                    "filter_order": idx,
                    "slug":unique_slug(attr_name, ProductAttribute.objects),
                },
            )
            # если уже существовала — аккуратно обновим стиль
            changed = False
            if hasattr(attr, "filter_widget") and attr.filter_widget != widget:
                attr.filter_widget = widget
                changed = True
            if hasattr(attr, "is_multiselect") and attr.is_multiselect != mult:
                attr.is_multiselect = mult
                changed = True
            if changed:
                attr.save(update_fields=["filter_widget", "is_multiselect"])
            attr_map[attr_name] = attr

            for opt in options:
                AttributeOption.objects.get_or_create(attribute=attr, value=opt)

        self.stdout.write("🧺 Коллекции…")
        collections = [
            Collection.objects.get_or_create(title=c, defaults={"slug": unique_slug(c, Collection.objects)})[0]
            for c in COLLECTIONS
        ]

        self.stdout.write("🧰 Сервисы…")
        for title, price in SERVICES:
            Service.objects.get_or_create(name=title, defaults={"price": price, "description": ""})

        self.stdout.write("🚚 Регионы доставки…")
        slug2region = {}
        for title, slug, base_cost, free_thr, (dmin, dmax) in REGIONS:
            r = DeliveryRegion.objects.create(
                name=title,
                slug=slug,
                base_cost=base_cost,
                free_threshold=free_thr,
                delivery_days_min=dmin,
                delivery_days_max=dmax,
            )
            slug2region[slug] = r

        self.stdout.write("🏷 Скидки на доставку…")
        for title, reg_slug, tp, val, min_total in DISCOUNTS:
            DeliveryDiscount.objects.create(
                title=title,
                region=slug2region.get(reg_slug) if reg_slug else None,
                discount_type=tp,
                value=val,
                min_order_total=min_total,
            )

        self.stdout.write("🖼 Слайдер…")
        for i in range(3):
            MainSlider.objects.create(
                title=f"Слайд {i+1}",
                image=cf(f"slide_{i+1}.jpg"),
                link="",
                order=i,
                is_active=True,
            )

        self.stdout.write(f"📦 Генерю товары: {products_count} шт…")
        all_colors = list(Color.objects.all())
        all_tags = list(Tag.objects.all())
        leaf_categories = list(Category.objects.filter(children__isnull=True)) or list(Category.objects.all())
        used_skus = set(Product.objects.values_list("sku", flat=True))
        created_products = []
        for _ in range(products_count):
            cat = random.choice(leaf_categories)
            base_title = f"{cat.name} {fake.word().capitalize()} {random.randint(100, 999)}"
            p_slug = unique_slug(base_title, Product.objects)
            price = random.randint(12000, 120000)
            has_disc = random.random() < 0.35
            disc = round(price * random.uniform(0.85, 0.97), 2) if has_disc else None
            color = random.choice(all_colors)
            sku = generate_unique_sku(used_skus, prefix="WM")

            p = Product(
                title=base_title,
                slug=p_slug,
                description=fake.paragraph(nb_sentences=3),
                price=price,
                discount_price=disc,
                sku=sku,
                is_active=True,
                stock=random.randint(0, 50),
                width=random.choice([60, 80, 100, 120, 150, 180]),
                height=random.choice([200, 210, 220, 240]),
                depth=random.choice([40, 45, 50, 60]),
                color=color,
                category=cat,
            )
            p.image = cf(f"{p_slug}.jpg")
            p.save()
            created_products.append(p)
            
            for attempt in range(3):
                try:
                    with transaction.atomic():
                        p.save()
                    break
                except IntegrityError as e:
                    if "core_product_sku_key" in str(e) and attempt < 2:
                        # пересоздаём SKU и пробуем ещё раз
                        sku = generate_unique_sku(used_skus, prefix="WM")
                        p.sku = sku
                        continue
                    raise
                        
            # теги
            if all_tags:
                k = random.randint(0, min(3, len(all_tags)))
                if k:
                    p.tags.add(*random.sample(all_tags, k=k))

            # доп. картинка
            ProductImage.objects.create(product=p, image=cf(f"{p_slug}_1.jpg"), alt_text=p.title)

            # атрибуты (устойчиво к рассинхрону)
            for attr_name in ATTRS.keys():
                attr = attr_map.get(attr_name) or ProductAttribute.objects.filter(name=attr_name).first()
                if not attr:
                    continue
                opt = AttributeOption.objects.filter(attribute=attr).order_by("?").first()
                if not opt:
                    continue
                ProductAttributeValue.objects.get_or_create(product=p, attribute=attr, option=opt)

        # немножко связок по цвету/related
        self.stdout.write("🔗 Линкую товары между собой…")
        id_to_product = {p.id: p for p in created_products}
        by_color = {}
        for p in created_products:
            by_color.setdefault(p.color_id, []).append(p.id)

        for ids in by_color.values():
            if len(ids) < 2:
                continue
            sample_ids = random.sample(ids, k=min(4, len(ids)))
            for pid in sample_ids:
                prod = id_to_product[pid]
                others_ids = [oid for oid in sample_ids if oid != pid]
                others_objs = [id_to_product[oid] for oid in others_ids]
                prod.related_products.add(*others_objs)
                prod.related_by_color.add(*others_objs)

        # раскидаем по коллекциям
        for p in created_products:
            p.collections.add(random.choice(collections))

        self.stdout.write(self.style.SUCCESS(f"Готово. Создано товаров: {len(created_products)}"))
