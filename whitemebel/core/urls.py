# api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import CategoryViewSet, DeliveryRegionListView, DeliveryRegionQuoteView, FiltersView, ProductDetailView, ProductListView, SliderViewSet,ProductsByIdsView, TagListView

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
    ]