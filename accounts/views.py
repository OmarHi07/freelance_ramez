from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from accounts.forms import AddressForm, EmailAuthenticationForm, ProfileForm, RegistrationForm
from accounts.models import Address
from core.constants import BUSINESS_NAME
from core.security import safe_next_url
from orders.models import Order


@require_http_methods(["GET", "POST"])
def register(request):
    next_url = safe_next_url(request, reverse("core:home"))
    if request.user.is_authenticated:
        return redirect(next_url)
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        # Logging in fires user_logged_in, which merges the anonymous cart.
        login(request, user, backend="accounts.backends.EmailBackend")
        messages.success(
            request,
            _("Welcome to %(store)s, %(name)s!") % {"store": BUSINESS_NAME, "name": user.get_short_name()},
        )
        return redirect(next_url)
    return render(request, "accounts/register.html", {"form": form, "next": next_url})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    """POST-only logout (Django's default); GET shows a confirmation page."""

    template_name = "accounts/logged_out.html"
    http_method_names = ["get", "post", "options"]

    def get(self, request, *args, **kwargs):
        return render(request, "accounts/logout_confirm.html")


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/emails/password_reset_email.txt"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        messages.success(self.request, _("Your password was changed."))
        return super().form_valid(form)


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Your profile was updated."))
        return redirect("accounts:profile")
    recent_orders = Order.objects.filter(customer=request.user).order_by("-created_at")[:3]
    return render(request, "accounts/profile.html", {"form": form, "recent_orders": recent_orders})


@login_required
def address_list(request):
    addresses = Address.objects.filter(user=request.user)
    return render(request, "accounts/address_list.html", {"addresses": addresses})


@login_required
@require_http_methods(["GET", "POST"])
def address_create(request):
    form = AddressForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        address.save()
        messages.success(request, _("Address saved."))
        return redirect(safe_next_url(request, reverse("accounts:address_list")))
    return render(request, "accounts/address_form.html", {"form": form, "is_new": True})


@login_required
@require_http_methods(["GET", "POST"])
def address_update(request, pk: int):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    form = AddressForm(request.POST or None, instance=address)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Address updated."))
        return redirect("accounts:address_list")
    return render(request, "accounts/address_form.html", {"form": form, "is_new": False, "address": address})


@login_required
@require_http_methods(["GET", "POST"])
def address_delete(request, pk: int):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        was_default = address.is_default
        address.delete()
        if was_default:
            replacement = Address.objects.filter(user=request.user).first()
            if replacement:
                replacement.is_default = True
                replacement.save(update_fields=["is_default", "updated_at"])
        messages.success(request, _("Address deleted."))
        return redirect("accounts:address_list")
    return render(request, "accounts/address_confirm_delete.html", {"address": address})
