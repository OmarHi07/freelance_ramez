from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from cart.services import attach_session_cart_to_user


@receiver(user_logged_in, dispatch_uid="cart_merge_on_login")
def merge_cart_on_login(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        attach_session_cart_to_user(request, user)
