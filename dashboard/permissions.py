"""Staff-only access control for every owner-dashboard route.

Two independent layers are used: every view class inherits
``StaffRequiredMixin`` *and* every URL pattern is wrapped with
``staff_required``. Anonymous visitors are sent to the login page; logged-in
customers get HTTP 403. Knowing a dashboard URL is never enough.
"""

from __future__ import annotations

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def is_staff_user(user) -> bool:
    return bool(user and user.is_authenticated and user.is_active and user.is_staff)


def staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_staff_user(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    _wrapped.staff_required = True
    return _wrapped


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self) -> bool:
        return is_staff_user(self.request.user)
