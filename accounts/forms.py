from __future__ import annotations

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from accounts.models import Address, User
from core.validators import normalize_phone


class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("At least 10 characters. Avoid common or all-numeric passwords."),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ("full_name", "email", "phone")
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "inputmode": "tel"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = True
        self.fields["full_name"].required = True

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."), code="duplicate_email")
        return email

    def clean_phone(self) -> str:
        return normalize_phone(self.cleaned_data["phone"])

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get("password1"), cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _("The two passwords do not match."))
        if password1:
            candidate = User(
                email=cleaned.get("email", ""),
                full_name=cleaned.get("full_name", ""),
                phone=cleaned.get("phone", ""),
            )
            try:
                password_validation.validate_password(password1, candidate)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    error_messages = {
        "invalid_login": _("The email or password is incorrect."),
        "inactive": _("This account is inactive."),
    }

    def clean_username(self) -> str:
        return self.cleaned_data["username"].strip().lower()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "phone")
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "inputmode": "tel"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = True

    def clean_phone(self) -> str:
        return normalize_phone(self.cleaned_data["phone"])


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ("label", "city", "street", "building_number", "apartment", "postal_code", "landmark", "is_default")
        widgets = {
            "city": forms.TextInput(attrs={"autocomplete": "address-level2"}),
            "street": forms.TextInput(attrs={"autocomplete": "address-line1"}),
            "building_number": forms.TextInput(attrs={"autocomplete": "address-line2"}),
            "postal_code": forms.TextInput(attrs={"autocomplete": "postal-code", "inputmode": "numeric"}),
        }
