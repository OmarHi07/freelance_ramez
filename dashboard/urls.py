from django.urls import path

from dashboard import views
from dashboard.permissions import staff_required

app_name = "dashboard"


def staff(view_class):
    """Wrap a class-based view so the URL itself enforces staff access (defence in depth)."""
    return staff_required(view_class.as_view())


urlpatterns = [
    path("", staff(views.OverviewView), name="overview"),
    # Orders
    path("orders/", staff(views.OrderListView), name="order_list"),
    path("orders/<uuid:pk>/", staff(views.OrderDetailView), name="order_detail"),
    path("orders/<uuid:pk>/status/", staff(views.OrderStatusUpdateView), name="order_status"),
    path("orders/<uuid:pk>/notes/", staff(views.OrderNotesUpdateView), name="order_notes"),
    path("orders/<uuid:pk>/resend-email/", staff(views.OrderResendNotificationView), name="order_resend_email"),
    # Products
    path("products/", staff(views.ProductListView), name="product_list"),
    path("products/new/", staff(views.ProductCreateView), name="product_create"),
    path("products/<int:pk>/edit/", staff(views.ProductUpdateView), name="product_update"),
    path("products/<int:pk>/delete/", staff(views.ProductDeleteView), name="product_delete"),
    # Stock
    path("stock/", staff(views.StockListView), name="stock_list"),
    path("stock/<int:pk>/", staff(views.StockUpdateView), name="stock_update"),
    # Brands
    path("brands/", staff(views.BrandListView), name="brand_list"),
    path("brands/new/", staff(views.BrandCreateView), name="brand_create"),
    path("brands/<int:pk>/edit/", staff(views.BrandUpdateView), name="brand_update"),
    path("brands/<int:pk>/delete/", staff(views.BrandDeleteView), name="brand_delete"),
    # Categories
    path("categories/", staff(views.CategoryListView), name="category_list"),
    path("categories/new/", staff(views.CategoryCreateView), name="category_create"),
    path("categories/<int:pk>/edit/", staff(views.CategoryUpdateView), name="category_update"),
    path("categories/<int:pk>/delete/", staff(views.CategoryDeleteView), name="category_delete"),
    # Promotions
    path("promotions/", staff(views.PromotionListView), name="promotion_list"),
    path("promotions/new/", staff(views.PromotionCreateView), name="promotion_create"),
    path("promotions/<int:pk>/edit/", staff(views.PromotionUpdateView), name="promotion_update"),
    path("promotions/<int:pk>/delete/", staff(views.PromotionDeleteView), name="promotion_delete"),
    # Customers
    path("customers/", staff(views.CustomerListView), name="customer_list"),
    path("customers/<int:pk>/", staff(views.CustomerDetailView), name="customer_detail"),
    # Settings
    path("settings/", staff(views.SiteSettingsUpdateView), name="settings"),
]
