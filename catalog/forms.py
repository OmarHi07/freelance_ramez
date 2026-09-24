from django import forms
from django.utils.translation import gettext_lazy as _

from catalog import selectors
from catalog.models import VerificationStatus


class BrandProductFilterForm(forms.Form):
    AVAILABILITY_CHOICES = [
        ("", _("All items")),
        (selectors.AVAILABILITY_IN_STOCK, _("In stock")),
        (selectors.AVAILABILITY_OUT_OF_STOCK, _("Out of stock")),
    ]
    VERIFICATION_CHOICES = [("", _("Any status")), *VerificationStatus.choices]
    SORT_CHOICES = [
        (selectors.SORT_NEWEST, _("Newest")),
        (selectors.SORT_PRICE_ASC, _("Price: low to high")),
        (selectors.SORT_PRICE_DESC, _("Price: high to low")),
    ]

    category = forms.ModelChoiceField(
        queryset=None, required=False, label=_("Category"), empty_label=_("All categories")
    )
    availability = forms.ChoiceField(choices=AVAILABILITY_CHOICES, required=False, label=_("Availability"))
    verification = forms.ChoiceField(choices=VERIFICATION_CHOICES, required=False, label=_("Brand confirmation"))
    min_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        label=_("Min price (₪)"),
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "1", "min": "0"}),
    )
    max_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        label=_("Max price (₪)"),
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "1", "min": "0"}),
    )
    sort = forms.ChoiceField(choices=SORT_CHOICES, required=False, label=_("Sort by"))

    def __init__(self, *args, brand=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = selectors.brand_categories(brand) if brand else selectors.active_categories()
        self.fields["category"].to_field_name = "slug"

    def clean(self):
        cleaned = super().clean()
        low, high = cleaned.get("min_price"), cleaned.get("max_price")
        if low is not None and high is not None and low > high:
            cleaned["min_price"], cleaned["max_price"] = high, low
        return cleaned

    @property
    def active_filter_count(self) -> int:
        if not self.is_valid():
            return 0
        keys = ("category", "availability", "verification", "min_price", "max_price")
        return sum(1 for key in keys if self.cleaned_data.get(key) not in (None, ""))
