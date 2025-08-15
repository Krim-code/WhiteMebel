# core/management/commands/reslug_ascii.py
from django.core.management.base import BaseCommand
from core.utils.slug import ascii_slug
from core.models import Category, Tag, ProductAttribute, Product

def reslug(model, field="name"):
    seen = set()
    for obj in model.objects.all():
        base = getattr(obj, "slug") or getattr(obj, field)
        s = ascii_slug(base)
        if not s: s = "item"
        orig = s; i = 2
        while s in seen or model.objects.exclude(pk=obj.pk).filter(slug=s).exists():
            s = f"{orig}-{i}"; i += 1
        if obj.slug != s:
            obj.slug = s
            obj.save(update_fields=["slug"])
        seen.add(s)

class Command(BaseCommand):
    help = "Перегенерить слаги в ASCII"

    def handle(self, *args, **kwargs):
        reslug(Category)
        reslug(Tag)
        reslug(ProductAttribute)
        reslug(Product, field="title")
        self.stdout.write(self.style.SUCCESS("Готово"))
