import pytest
from django.core import mail
from django.urls import reverse
from django.utils import translation

from accounts.models import Address, User
from conftest import PASSWORD, make_user

pytestmark = pytest.mark.django_db


def url(name, **kwargs):
    with translation.override("en"):
        return reverse(name, kwargs=kwargs or None)


REGISTRATION = {
    "full_name": "Lina Haddad",
    "email": "Lina@Example.TEST",
    "phone": "050 123 4567",
    "password1": "pearl-and-rose-2026",
    "password2": "pearl-and-rose-2026",
}


def test_registration_creates_customer_and_logs_in(client, site_settings):
    response = client.post(url("accounts:register") + "?next=/en/orders/checkout/", REGISTRATION)
    assert response.status_code == 302 and response["Location"] == "/en/orders/checkout/"
    user = User.objects.get()
    assert user.email == "lina@example.test" and user.phone == "0501234567"
    assert not user.is_staff and user.check_password(REGISTRATION["password1"])
    assert client.get(url("accounts:profile")).status_code == 200


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phone", ""),
        ("full_name", ""),
        ("password2", "different-pass-2026"),
        ("password1", "1234567890"),
        ("email", "not-an-email"),
    ],
)
def test_registration_validation(client, site_settings, field, value):
    data = {**REGISTRATION, field: value}
    if field == "password1":
        data["password2"] = value
    response = client.post(url("accounts:register"), data)
    assert response.status_code == 200
    assert not User.objects.exists()


def test_duplicate_email_is_case_insensitive(client, site_settings):
    make_user(email="lina@example.test")
    response = client.post(url("accounts:register"), REGISTRATION)
    assert "email" in response.context["form"].errors


def test_email_login_is_case_insensitive_and_safe_redirect(client, customer, site_settings):
    response = client.post(
        url("accounts:login"),
        {"username": customer.email.upper(), "password": PASSWORD, "next": "https://evil.example.com/steal"},
    )
    assert response.status_code == 302
    assert response["Location"].startswith("/") and "evil" not in response["Location"]


def test_register_ignores_external_next(client, site_settings):
    response = client.post(url("accounts:register") + "?next=//evil.example.com", REGISTRATION)
    assert "evil" not in response["Location"]


def test_login_throttling_locks_out_after_repeated_failures(client, customer, site_settings, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT):
        client.post(url("accounts:login"), {"username": customer.email, "password": "wrong-password"})
    response = client.post(url("accounts:login"), {"username": customer.email.upper(), "password": PASSWORD})
    assert response.status_code == 429
    assert "_auth_user_id" not in client.session


def test_logout_requires_post(customer_client, site_settings):
    assert customer_client.get(url("accounts:logout")).status_code == 200  # confirmation page only
    assert "_auth_user_id" in customer_client.session
    customer_client.post(url("accounts:logout"))
    assert "_auth_user_id" not in customer_client.session


def test_password_reset_sends_email(client, customer, site_settings):
    assert client.get(url("accounts:password_reset")).status_code == 200
    response = client.post(url("accounts:password_reset"), {"email": customer.email})
    assert response.status_code == 302
    assert len(mail.outbox) == 1 and "/account/password/reset/" in mail.outbox[0].body


def test_profile_update(customer_client, customer, site_settings):
    customer_client.post(url("accounts:profile"), {"full_name": "New Name", "phone": "052-000-1111"})
    customer.refresh_from_db()
    assert customer.full_name == "New Name" and customer.phone == "0520001111"


def test_addresses_are_private(customer_client, customer, other_customer, site_settings):
    mine = Address.objects.create(user=customer, city="Haifa", street="A", building_number="1")
    theirs = Address.objects.create(user=other_customer, city="Akko", street="Secret", building_number="9")
    html = customer_client.get(url("accounts:address_list")).content.decode()
    assert "Haifa" in html and "Secret" not in html
    assert customer_client.get(url("accounts:address_update", pk=theirs.pk)).status_code == 404
    assert customer_client.post(url("accounts:address_delete", pk=theirs.pk)).status_code == 404
    assert Address.objects.filter(pk=theirs.pk).exists()
    customer_client.post(url("accounts:address_delete", pk=mine.pk))
    assert not Address.objects.filter(pk=mine.pk).exists()


def test_one_default_address_per_user(customer, site_settings):
    first = Address.objects.create(user=customer, city="A", street="A", building_number="1")
    second = Address.objects.create(user=customer, city="B", street="B", building_number="2", is_default=True)
    first.refresh_from_db()
    assert first.is_default is False and second.is_default is True


def test_account_pages_require_login(client, site_settings):
    for name in ("accounts:profile", "accounts:address_list", "orders:list"):
        response = client.get(url(name))
        assert response.status_code == 302 and "/account/login/" in response["Location"]


def test_createsuperuser_manager_sets_flags(db):
    admin = User.objects.create_superuser(email="Owner@Example.test", password=PASSWORD, full_name="Owner")
    assert admin.is_staff and admin.is_superuser and admin.email == "owner@example.test"
