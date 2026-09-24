from django import forms
from django.conf import settings


class AddToCartForm(forms.Form):
    variant = forms.IntegerField(min_value=1)
    quantity = forms.IntegerField(min_value=1, max_value=settings.MAX_CART_LINE_QUANTITY, initial=1)


class UpdateCartItemForm(forms.Form):
    quantity = forms.IntegerField(min_value=0, max_value=settings.MAX_CART_LINE_QUANTITY)
