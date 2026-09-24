from django.urls import path

from catalog import views

app_name = "catalog"

urlpatterns = [
    path("brands/", views.brand_list, name="brand_list"),
    path("brands/<slug:slug>/", views.brand_detail, name="brand_detail"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
]
