from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel
from core.validators import customer_phone_validator


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        return self.get(email__iexact=(username or "").strip())

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).strip().lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user identified by email. Created from day one to avoid a later swap."""

    email = models.EmailField(_("email address"), max_length=254, unique=True)
    full_name = models.CharField(_("full name"), max_length=150)
    phone = models.CharField(_("phone number"), max_length=20, blank=True, validators=[customer_phone_validator])
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Staff members can access the owner dashboard."),
    )
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)

    objects = UserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def __str__(self) -> str:
        return self.email

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email).strip().lower()

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.email


class Address(TimeStampedModel):
    """A saved delivery address. Coordinates are never stored here, only on orders."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses", verbose_name=_("customer"))
    label = models.CharField(_("label"), max_length=60, blank=True, help_text=_("For example: Home, Work"))
    city = models.CharField(_("city / town"), max_length=100)
    street = models.CharField(_("street"), max_length=150)
    building_number = models.CharField(_("building / house number"), max_length=20)
    apartment = models.CharField(_("apartment"), max_length=20, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=12, blank=True)
    landmark = models.CharField(_("landmark or delivery notes"), max_length=255, blank=True)
    is_default = models.BooleanField(_("default address"), default=False)

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ["-is_default", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=Q(is_default=True), name="accounts_one_default_address_per_user"
            ),
        ]
        indexes = [models.Index(fields=["user", "-updated_at"], name="accounts_address_user_idx")]

    def __str__(self) -> str:
        return self.one_line()

    def one_line(self) -> str:
        parts = [f"{self.street} {self.building_number}".strip()]
        if self.apartment:
            parts.append(str(_("Apt. %(apartment)s") % {"apartment": self.apartment}))
        parts.append(self.city)
        if self.postal_code:
            parts.append(self.postal_code)
        return ", ".join(part for part in parts if part)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
            elif not Address.objects.filter(user=self.user).exclude(pk=self.pk).exists():
                self.is_default = True
            super().save(*args, **kwargs)
