import os
import secrets
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

ENV_EMAIL = os.getenv("SUPERUSER_EMAIL") or os.getenv("DJANGO_SUPERUSER_EMAIL")
ENV_PASSWORD = os.getenv("SUPERUSER_PASSWORD") or os.getenv("DJANGO_SUPERUSER_PASSWORD")
ENV_FIRST = os.getenv("SUPERUSER_FIRST_NAME") or ""
ENV_LAST = os.getenv("SUPERUSER_LAST_NAME") or ""
ENV_PHONE = os.getenv("SUPERUSER_PHONE") or ""

class Command(BaseCommand):
    help = "Создать или обновить суперпользователя без интерактива."

    def add_arguments(self, parser):
        parser.add_argument("--email", type=str, help="Email суперпользователя")
        parser.add_argument("--password", type=str, help="Пароль (если не указан — сгенерируется)")
        parser.add_argument("--first-name", type=str, default=None, help="Имя")
        parser.add_argument("--last-name", type=str, default=None, help="Фамилия")
        parser.add_argument("--phone", type=str, default=None, help="Телефон")
        parser.add_argument("--update", action="store_true",
                            help="Если пользователь уже есть — обновить флаги/данные. "
                                 "Пароль меняется только если передан --password.")
        parser.add_argument("--print-password", action="store_true",
                            help="Печатать сгенерированный пароль в stdout (удобно для dev).")

    def handle(self, *args, **opts):
        User = get_user_model()

        email = (opts.get("email") or ENV_EMAIL or "").strip().lower()
        if not email:
            # дефолт для локалки
            email = "admin@witemebel.local"
            self.stdout.write(self.style.WARNING(f"[!] email не задан, беру дефолт: {email}"))

        password = opts.get("password") or ENV_PASSWORD
        generated = False
        if not password:
            password = secrets.token_urlsafe(16)
            generated = True

        first_name = opts.get("first_name")
        last_name = opts.get("last_name")
        phone = opts.get("phone")

        # ENV как фоллбек, если опции не заданы
        if first_name is None:
            first_name = ENV_FIRST
        if last_name is None:
            last_name = ENV_LAST
        if phone is None:
            phone = ENV_PHONE

        user = User.objects.filter(email=email).first()

        if user:
            if not opts.get("update"):
                self.stdout.write(self.style.WARNING(f"Пользователь {email} уже существует. "
                                                     f"Ничего не делаю (добавь --update, если нужно обновить)."))
                return

            # апгрейдим
            updates = []
            if not user.is_staff:
                user.is_staff = True; updates.append("is_staff")
            if not user.is_superuser:
                user.is_superuser = True; updates.append("is_superuser")

            # профильные поля
            if first_name and user.first_name != first_name:
                user.first_name = first_name; updates.append("first_name")
            if last_name and user.last_name != last_name:
                user.last_name = last_name; updates.append("last_name")
            if phone and user.phone != phone:
                user.phone = phone; updates.append("phone")

            if opts.get("password"):  # пароль меняем только когда явно просят
                user.set_password(password); updates.append("password")

            if updates:
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f"Обновлён {email}: {', '.join(updates)}"
                ))
            else:
                self.stdout.write(f"Без изменений для {email}.")
        else:
            # создаём нового
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name or "",
                last_name=last_name or "",
                phone=phone or "",
                is_staff=True,
                is_superuser=True,
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Создан суперпользователь: {email}"))

        if generated and opts.get("print_password"):
            self.stdout.write(self.style.WARNING(f"[dev only] Сгенерированный пароль: {password}"))
