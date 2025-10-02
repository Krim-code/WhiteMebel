# api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import (CategoryViewSet, DeliveryRegionListView, 
                        DeliveryRegionQuoteView, FiltersView,
                        OrderCreateView, ProductDetailView,
                        ProductListView, ServiceListView, SliderViewSet,
                        ProductsByIdsView, TagListView,
                        ContactRequestCreateView,CloudPaymentsWebhookView, 
                        CloudPaymentsPayView, OrderStatusView)

from core.views import (         # HTML-виджет (только для теста)
    CloudPaymentsInitView,         # API: конфиг для виджета              # API: статус заказа (поллинг)
    PaymentSuccessView,            # success (можно редиректить на фронт)
    PaymentFailView,               # fail      # вебхук от CloudPayments
)
from .views import OrderAcceptedView

# from core.views import ProductViewSet, CategoryViewSet, TagViewSet, ColorViewSet

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r"slider", SliderViewSet, basename="slider")

# router.register(r'products', ProductViewSet, basename='product')
# router.register(r'categories', CategoryViewSet, basename='category')
# router.register(r'tags', TagViewSet, basename='tag')
# router.register(r'colors', ColorViewSet, basename='color')

urlpatterns = [
    path("", include(router.urls)),
    path('filters/', FiltersView.as_view(), name='filters'),
    path('products/', ProductListView.as_view(), name='products-list'),
    path("products/by-ids/", ProductsByIdsView.as_view(), name="products-by-ids"),
    path('products/<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),
    path("tags/", TagListView.as_view(), name="tag-list"),
    path("shipping/regions/", DeliveryRegionListView.as_view(), name="shipping-regions"),
    path("shipping/regions/<slug:slug>/quote/", DeliveryRegionQuoteView.as_view(), name="shipping-region-quote"),
    path("contact-requests/", ContactRequestCreateView.as_view(), name="contact-request-create"),
    path("orders/", OrderCreateView.as_view(), name="order-create"),
    # HTML (тестовый шаблон виджета)
    path("payments/pay/<int:order_id>/", CloudPaymentsPayView.as_view(), name="cp-pay"),

    # API для фронта
    path("payments/init/<int:order_id>/", CloudPaymentsInitView.as_view(), name="cp-init"),
    path("orders/<int:order_id>/status/", OrderStatusView.as_view(), name="order-status"),
    path("payments/success/", PaymentSuccessView.as_view(), name="payment-success"),
    path("payments/fail/", PaymentFailView.as_view(), name="payment-fail"),

    # Важно: URL вебхука CloudPayments (передашь в ЛК CloudPayments)
    path("payments/cloudpayments/webhook/", CloudPaymentsWebhookView.as_view(), name="cp-webhook"),
    path("services/", ServiceListView.as_view(), name="service-list"),
    ]

urlpatterns += [
    path("orders/<int:order_id>/accepted/", OrderAcceptedView.as_view(), name="order-accepted"),
]