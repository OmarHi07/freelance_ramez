from django.urls import path

from orders import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="list"),
    path("checkout/", views.checkout, name="checkout"),
    path("<uuid:pk>/", views.order_detail, name="detail"),
    path("<uuid:pk>/confirmation/", views.confirmation, name="confirmation"),
]
