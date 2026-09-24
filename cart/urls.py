from django.urls import path

from cart import views

app_name = "cart"

urlpatterns = [
    path("", views.cart_detail, name="detail"),
    path("add/", views.cart_add, name="add"),
    path("items/<int:item_id>/update/", views.cart_update, name="update"),
    path("items/<int:item_id>/remove/", views.cart_remove, name="remove"),
]
