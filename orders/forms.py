from __future__ import annotations

from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from accounts.models import Address
from core.validators import customer_phone_validator, normalize_phone

ADDRESS_FIELDS = ("city", "street", "building_number", "apartment", "postal_code", "landmark")
REQUIRED_ADDRESS_FIELDS = ("city", "street", "building_number")


class SavedAddressChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj: Address) -> str:
        return f"{obj.label} — {obj.one_line()}" if obj.label else obj.one_line()


class CheckoutForm(forms.Form):
    saved_address = SavedAddressChoiceField(
        queryset=Address.objects.none(),
        required=False,
        empty_label=_("Enter a new address"),
        widget=forms.RadioSelect,
        label=_("Delivery address"),
    )
    city = forms.CharField(label=_("City / town"), max_length=100, required=False)
    street = forms.CharField(label=_("Street"), max_length=150, required=False)
    building_number = forms.CharField(label=_("Building / house number"), max_length=20, required=False)
    apartment = forms.CharField(label=_("Apartment (optional)"), max_length=20, required=False)
    postal_code = forms.CharField(label=_("Postal code (optional)"), max_length=12, required=False)
    landmark = forms.CharField(
        label=_("Landmark or delivery notes (optional)"),
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": _("Near the pharmacy, second floor…")}),
    )
    save_address = forms.BooleanField(label=_("Save this address to my account"), required=False, initial=True)
    phone = forms.CharField(
        label=_("Phone number"),
        max_length=20,
        validators=[customer_phone_validator],
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "inputmode": "tel"}),
    )
    customer_notes = forms.CharField(
        label=_("Order notes (optional)"),
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    # Optional location: only filled after the customer presses the button and the browser grants permission.
    location_consent = forms.BooleanField(required=False, widget=forms.HiddenInput)
    latitude = forms.DecimalField(required=False, max_digits=12, decimal_places=8, widget=forms.HiddenInput)
    longitude = forms.DecimalField(required=False, max_digits=12, decimal_places=8, widget=forms.HiddenInput)
    location_accuracy = forms.DecimalField(
        required=False, max_digits=12, decimal_places=3, min_value=0, widget=forms.HiddenInput
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None and user.is_authenticated:
            self.fields["saved_address"].queryset = Address.objects.filter(user=user)
        autocomplete = {
            "city": "address-level2",
            "street": "address-line1",
            "building_number": "address-line2",
            "postal_code": "postal-code",
        }
        for name, value in autocomplete.items():
            self.fields[name].widget.attrs["autocomplete"] = value

    @property
    def has_saved_addresses(self) -> bool:
        return self.fields["saved_address"].queryset.exists()

    def clean_phone(self) -> str:
        return normalize_phone(self.cleaned_data["phone"])

    def clean(self):
        cleaned = super().clean()
        address = cleaned.get("saved_address")
        if address is not None:
            for name in ADDRESS_FIELDS:
                cleaned[name] = getattr(address, name)
            cleaned["save_address"] = False
        else:
            for name in REQUIRED_ADDRESS_FIELDS:
                if not (cleaned.get(name) or "").strip():
                    self.add_error(name, _("This field is required."))
        cleaned["location"] = self._clean_location(cleaned)
        return cleaned

    def _clean_location(self, cleaned) -> dict | None:
        """Keep coordinates only with explicit consent and valid ranges; otherwise ignore them."""
        if not cleaned.get("location_consent"):
            return None
        lat, lng = cleaned.get("latitude"), cleaned.get("longitude")
        if lat is None or lng is None:
            return None
        if not (Decimal(-90) <= lat <= Decimal(90) and Decimal(-180) <= lng <= Decimal(180)):
            return None
        return {"latitude": lat, "longitude": lng, "accuracy": cleaned.get("location_accuracy")}
