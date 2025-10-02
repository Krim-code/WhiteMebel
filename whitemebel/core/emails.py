# core/emails.py
from decimal import Decimal
import threading
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.db import connection

from core.models import Order  # чтобы рефетчить заказ в воркере


log = logging.getLogger(__name__)


def _money(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"))


def send_order_notifications(order: Order) -> None:
    """
    Шлём админам и покупателю. HTML + текст.
    ВАЖНО: это синхронная функция — вызывай её только из фонового воркера
    или из transaction.on_commit (но лучше фоном).
    """
    items = list(order.items.select_related("product").all())
    services = list(order.orderservice_set.select_related("service").all())

    ctx = {
        "order": order,
        "items": items,
        "services": services,
        "subtotal": getattr(order, "_subtotal", None),
        "services_total": getattr(order, "_services_total", None),
        "delivery_base": getattr(order, "_delivery_base", None),
        "delivery_discount": getattr(order, "_delivery_discount", None),
        "delivery_cost": getattr(order, "_delivery_cost", None),
        "total": _money(order.total_price),
    }

    # === Админам ===
    admin_to = getattr(settings, "ORDER_NOTIFY_EMAILS", [])
    if admin_to:
        subject_admin = f"Новый заказ #{order.id} — {order.full_name}"
        html_admin = render_to_string("email/order_admin.html", ctx)
        text_admin = strip_tags(html_admin)
        msg = EmailMultiAlternatives(
            subject=subject_admin,
            body=text_admin,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=admin_to,
        )
        msg.attach_alternative(html_admin, "text/html")
        try:
            msg.send(fail_silently=False)
        except Exception:
            log.exception("Order #%s: admin email send failed", order.id)

    # === Покупателю ===
    if order.email:
        subject_user = f"Ваш заказ #{order.id} принят"
        html_user = render_to_string("email/order_user.html", ctx)
        text_user = strip_tags(html_user)
        msg2 = EmailMultiAlternatives(
            subject=subject_user,
            body=text_user,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.email],
        )
        msg2.attach_alternative(html_user, "text/html")
        try:
            msg2.send(fail_silently=False)
        except Exception:
            log.exception("Order #%s: customer email send failed", order.id)


# ---------- Асинхронная обёртка ----------

def _email_worker(order_id: int) -> None:
    """
    Фоновый воркер: рефетчит заказ и безопасно шлёт письма,
    чтобы SMTP/шаблоны не блокировали веб-процесс.
    """
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        log.warning("email worker: order %s not found", order_id)
        return

    try:
        # Опционально: прогреть SMTP и использовать EMAIL_TIMEOUT из settings
        get_connection()
        send_order_notifications(order)
    except Exception as e:
        log.exception("email worker failed for order %s: %s", order_id, e)
    finally:
        # Закрыть подключение к БД в треде
        try:
            connection.close()
        except Exception:
            pass


def send_order_notifications_async(order_id: int) -> None:
    """
    Запустить отправку писем в отдельном daemon-треде. Возврат мгновенный.
    """
    t = threading.Thread(
        target=_email_worker,
        args=(order_id,),
        daemon=True,
        name=f"order-mail-{order_id}",
    )
    t.start()
