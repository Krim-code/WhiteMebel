# core/emails.py
from decimal import Decimal
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def _money(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"))

def send_order_notifications(order):
    """
    Шлём админам и покупателю. HTML + текст.
    Вызывать через transaction.on_commit().
    """
    # подтягиваем всё, что надо в шаблон
    items = list(order.items.select_related("product").all())
    services = list(order.orderservice_set.select_related("service").all())

    ctx = {
        "order": order,
        "items": items,
        "services": services,
        # на случай если сериалайзер положил временные поля:
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
            # не убиваем запрос, логи — в консоль/серверные логи
            import logging
            logging.getLogger(__name__).exception("Order #%s: admin email send failed", order.id)

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
            import logging
            logging.getLogger(__name__).exception("Order #%s: customer email send failed", order.id)
