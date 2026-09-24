"""Owner dashboard (/owner/). Every view requires an active staff account."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, DecimalField, Max, ProtectedError, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from accounts.models import User
from catalog.models import Brand, Category, Product, ProductImage, ProductVariant, Promotion
from core.models import SiteSettings
from dashboard.forms import (
    BrandForm,
    CategoryForm,
    CustomerFilterForm,
    ImageFormSet,
    OrderFilterForm,
    OrderNotesForm,
    OrderStatusForm,
    ProductFilterForm,
    ProductForm,
    PromotionForm,
    SiteSettingsForm,
    StockUpdateForm,
    VariantFormSet,
)
from dashboard.permissions import StaffRequiredMixin
from orders.models import Order, OrderStatus
from orders.services.status import InsufficientStock, InvalidTransition, transition_order
from orders.services.whatsapp import customer_whatsapp_url

PAGE_SIZE = 20
SALES_STATUSES = [OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]
MONEY_ZERO = Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
class OverviewView(StaffRequiredMixin, TemplateView):
    template_name = "dashboard/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        sales = Order.objects.filter(status__in=SALES_STATUSES)
        context.update(
            {
                "new_orders": Order.objects.filter(status__in=[OrderStatus.PENDING, OrderStatus.RECEIVED]).count(),
                "active_products": Product.objects.filter(is_active=True).count(),
                "low_stock": ProductVariant.objects.filter(
                    is_active=True, product__is_active=True, stock_quantity__lte=settings.LOW_STOCK_THRESHOLD
                ).count(),
                "customers": User.objects.filter(is_staff=False).count(),
                "sales_7_days": sales.filter(created_at__gte=now - timedelta(days=7)).aggregate(
                    total=Coalesce(Sum("total"), MONEY_ZERO)
                )["total"],
                "sales_30_days": sales.filter(created_at__gte=now - timedelta(days=30)).aggregate(
                    total=Coalesce(Sum("total"), MONEY_ZERO)
                )["total"],
                "recent_orders": Order.objects.order_by("-created_at")[:8],
                "low_stock_threshold": settings.LOW_STOCK_THRESHOLD,
            }
        )
        return context


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
class OrderListView(StaffRequiredMixin, ListView):
    template_name = "dashboard/orders/list.html"
    context_object_name = "orders"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        self.filter_form = OrderFilterForm(self.request.GET or None)
        queryset = Order.objects.annotate(item_count=Sum("items__quantity")).order_by("-created_at")
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("q"):
                term = data["q"].strip()
                queryset = queryset.filter(
                    Q(number__icontains=term)
                    | Q(customer_name__icontains=term)
                    | Q(customer_phone__icontains=term)
                    | Q(customer_email__icontains=term)
                )
            if data.get("status"):
                queryset = queryset.filter(status=data["status"])
            tz = timezone.get_current_timezone()
            if data.get("date_from"):
                queryset = queryset.filter(created_at__gte=datetime.combine(data["date_from"], time.min, tzinfo=tz))
            if data.get("date_to"):
                queryset = queryset.filter(created_at__lte=datetime.combine(data["date_to"], time.max, tzinfo=tz))
        return queryset

    def get_template_names(self):
        if _is_htmx(self.request) and self.request.headers.get("HX-Target") == "order-results":
            return ["dashboard/orders/_results.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["status_choices"] = OrderStatus.choices
        return context


class OrderDetailView(StaffRequiredMixin, DetailView):
    template_name = "dashboard/orders/detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("customer").prefetch_related("items", "status_history__changed_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        context["status_form"] = kwargs.get("status_form") or OrderStatusForm(order=order)
        context["notes_form"] = kwargs.get("notes_form") or OrderNotesForm(instance=order)
        context["customer_whatsapp_url"] = customer_whatsapp_url(order.customer_phone)
        return context


class OrderStatusUpdateView(StaffRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = OrderStatusForm(request.POST, order=order)
        if not form.is_valid():
            messages.error(request, _("That status change is not allowed for this order."))
            return redirect("dashboard:order_detail", pk=order.pk)
        try:
            order = transition_order(
                order, form.cleaned_data["status"], actor=request.user, note=form.cleaned_data.get("note", "")
            )
        except InvalidTransition:
            messages.error(request, _("That status change is not allowed for this order."))
        except InsufficientStock as error:
            messages.error(
                request,
                _("Not enough stock to confirm this order. Check these SKUs: %(skus)s")
                % {"skus": ", ".join(error.skus)},
            )
        else:
            messages.success(
                request, _("Order status updated to “%(status)s”.") % {"status": order.get_status_display()}
            )
        return redirect("dashboard:order_detail", pk=order.pk)


class OrderNotesUpdateView(StaffRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = OrderNotesForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, _("Internal notes saved."))
        else:
            messages.error(request, _("The notes could not be saved."))
        return redirect("dashboard:order_detail", pk=order.pk)


# ---------------------------------------------------------------------------
# Generic CRUD helpers
# ---------------------------------------------------------------------------
class SuccessMessageMixin:
    success_text = gettext_lazy("Saved.")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, str(self.success_text))
        return response


class ProtectedDeleteView(StaffRequiredMixin, DeleteView):
    template_name = "dashboard/confirm_delete.html"
    protected_text = gettext_lazy("This item is still in use and cannot be deleted. Hide it instead.")
    deleted_text = gettext_lazy("Deleted.")
    cancel_url_name = ""

    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, str(self.protected_text))
            return HttpResponseRedirect(self.get_success_url())
        messages.success(self.request, str(self.deleted_text))
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = self.get_success_url()
        context["consequences"] = self.get_consequences()
        return context

    def get_consequences(self) -> list[str]:
        return []


# ---------------------------------------------------------------------------
# Brands
# ---------------------------------------------------------------------------
class BrandListView(StaffRequiredMixin, ListView):
    template_name = "dashboard/brands/list.html"
    context_object_name = "brands"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        return Brand.objects.annotate(product_count=Count("products")).order_by("display_order", "name_en")


class BrandCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Brand
    form_class = BrandForm
    template_name = "dashboard/generic_form.html"
    success_url = reverse_lazy("dashboard:brand_list")
    success_text = gettext_lazy("Brand saved.")
    extra_context = {"title": gettext_lazy("New brand"), "back_url_name": "dashboard:brand_list"}


class BrandUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Brand
    form_class = BrandForm
    template_name = "dashboard/generic_form.html"
    success_url = reverse_lazy("dashboard:brand_list")
    success_text = gettext_lazy("Brand saved.")
    extra_context = {"title": gettext_lazy("Edit brand"), "back_url_name": "dashboard:brand_list"}


class BrandDeleteView(ProtectedDeleteView):
    model = Brand
    success_url = reverse_lazy("dashboard:brand_list")
    protected_text = gettext_lazy("This brand still has products. Move or delete them first, or hide the brand.")
    deleted_text = gettext_lazy("Brand deleted.")

    def get_consequences(self):
        count = self.object.products.count()
        if count:
            return [_("This brand has %(count)s products, so it cannot be deleted.") % {"count": count}]
        return [_("Promotions that target this brand will also be deleted.")]


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
class CategoryListView(StaffRequiredMixin, ListView):
    template_name = "dashboard/categories/list.html"
    context_object_name = "categories"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        return Category.objects.annotate(product_count=Count("products")).order_by("display_order", "name_en")


class CategoryCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "dashboard/generic_form.html"
    success_url = reverse_lazy("dashboard:category_list")
    success_text = gettext_lazy("Category saved.")
    extra_context = {"title": gettext_lazy("New category"), "back_url_name": "dashboard:category_list"}


class CategoryUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "dashboard/generic_form.html"
    success_url = reverse_lazy("dashboard:category_list")
    success_text = gettext_lazy("Category saved.")
    extra_context = {"title": gettext_lazy("Edit category"), "back_url_name": "dashboard:category_list"}


class CategoryDeleteView(ProtectedDeleteView):
    model = Category
    success_url = reverse_lazy("dashboard:category_list")
    deleted_text = gettext_lazy("Category deleted.")

    def get_consequences(self):
        return [
            _("Products stay in the store but will no longer be listed in this category."),
            _("Promotions that target this category will also be deleted."),
        ]


# ---------------------------------------------------------------------------
# Products (with variants, stock and images)
# ---------------------------------------------------------------------------
class ProductListView(StaffRequiredMixin, ListView):
    template_name = "dashboard/products/list.html"
    context_object_name = "products"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        self.filter_form = ProductFilterForm(self.request.GET or None)
        queryset = (
            Product.objects.select_related("brand")
            .prefetch_related("images")
            .annotate(
                stock=Coalesce(Sum("variants__stock_quantity", filter=Q(variants__is_active=True)), 0),
                variant_count=Count("variants", distinct=True),
            )
            .order_by("-created_at")
        )
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("q"):
                term = data["q"].strip()
                queryset = queryset.filter(
                    Q(name_en__icontains=term)
                    | Q(name_ar__icontains=term)
                    | Q(sku__icontains=term)
                    | Q(variants__sku__icontains=term)
                ).distinct()
            if data.get("brand"):
                queryset = queryset.filter(brand=data["brand"])
            state = data.get("state")
            if state == "active":
                queryset = queryset.filter(is_active=True)
            elif state == "inactive":
                queryset = queryset.filter(is_active=False)
            elif state == "low":
                queryset = queryset.filter(stock__lte=settings.LOW_STOCK_THRESHOLD)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        context["low_stock_threshold"] = settings.LOW_STOCK_THRESHOLD
        return context


class ProductEditMixin(StaffRequiredMixin):
    model = Product
    form_class = ProductForm
    template_name = "dashboard/products/form.html"

    def get_formsets(self, instance):
        data = self.request.POST if self.request.method == "POST" else None
        files = self.request.FILES if self.request.method == "POST" else None
        return (
            VariantFormSet(data, files, instance=instance, prefix="variants"),
            ImageFormSet(
                data,
                files,
                instance=instance,
                prefix="images",
                queryset=ProductImage.objects.filter(product=instance) if instance.pk else ProductImage.objects.none(),
            ),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "variant_formset" not in kwargs:
            variant_formset, image_formset = self.get_formsets(self.object or Product())
            context["variant_formset"] = variant_formset
            context["image_formset"] = image_formset
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object() if kwargs.get("pk") else None
        form = self.get_form()
        instance = form.instance
        variant_formset, image_formset = self.get_formsets(instance)
        if form.is_valid() and variant_formset.is_valid() and image_formset.is_valid():
            with transaction.atomic():
                product = form.save()
                variant_formset.instance = product
                variant_formset.save()
                image_formset.instance = product
                image_formset.save()
                self._save_new_images(product, form.cleaned_data.get("new_images") or [])
            messages.success(request, _("Product saved."))
            if "save_continue" in request.POST:
                return redirect("dashboard:product_update", pk=product.pk)
            return redirect("dashboard:product_list")
        messages.error(request, _("Please correct the errors below."))
        return self.render_to_response(
            self.get_context_data(form=form, variant_formset=variant_formset, image_formset=image_formset)
        )

    @staticmethod
    def _save_new_images(product, files):
        if not files:
            return
        last_order = product.images.aggregate(last=Max("display_order"))["last"] or 0
        has_primary = product.images.filter(is_primary=True).exists()
        for offset, uploaded in enumerate(files, start=1):
            ProductImage.objects.create(
                product=product,
                image=uploaded,
                display_order=last_order + offset,
                is_primary=not has_primary and offset == 1,
            )


class ProductCreateView(ProductEditMixin, CreateView):
    extra_context = {"title": gettext_lazy("New product")}


class ProductUpdateView(ProductEditMixin, UpdateView):
    extra_context = {"title": gettext_lazy("Edit product")}

    def get_queryset(self):
        return Product.objects.select_related("brand").prefetch_related("images", "variants", "categories")


class ProductDeleteView(ProtectedDeleteView):
    model = Product
    success_url = reverse_lazy("dashboard:product_list")
    deleted_text = gettext_lazy("Product deleted.")

    def get_consequences(self):
        return [
            _("Its variants, images and product-specific promotions will be deleted."),
            _("Past orders keep their saved names and prices."),
            _("Tip: untick “Active” to hide a product without deleting it."),
        ]


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------
class StockListView(StaffRequiredMixin, ListView):
    template_name = "dashboard/stock/list.html"
    context_object_name = "variants"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        queryset = ProductVariant.objects.select_related("product__brand").order_by(
            "stock_quantity", "product__name_en"
        )
        view = self.request.GET.get("view", "low")
        self.stock_view = view if view in {"low", "out", "all"} else "low"
        if self.stock_view == "low":
            queryset = queryset.filter(stock_quantity__lte=settings.LOW_STOCK_THRESHOLD)
        elif self.stock_view == "out":
            queryset = queryset.filter(stock_quantity=0)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stock_view"] = self.stock_view
        context["low_stock_threshold"] = settings.LOW_STOCK_THRESHOLD
        return context


class StockUpdateView(StaffRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        variant = get_object_or_404(ProductVariant.objects.select_related("product"), pk=pk)
        form = StockUpdateForm(request.POST, instance=variant)
        if form.is_valid():
            form.save()
            saved = True
        else:
            saved = False
        if _is_htmx(request):
            return render(request, "dashboard/stock/_row.html", {"variant": variant, "saved": saved, "form": form})
        if saved:
            messages.success(request, _("Stock updated."))
        else:
            messages.error(request, _("Enter a stock quantity of 0 or more."))
        return redirect(
            request.POST.get("return_to")
            if _safe_local(request.POST.get("return_to"))
            else reverse("dashboard:stock_list")
        )


def _safe_local(url: str | None) -> bool:
    return bool(url) and url.startswith("/") and not url.startswith("//") and "\\" not in url


# ---------------------------------------------------------------------------
# Promotions
# ---------------------------------------------------------------------------
class PromotionListView(StaffRequiredMixin, ListView):
    template_name = "dashboard/promotions/list.html"
    context_object_name = "promotions"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        return Promotion.objects.select_related("brand", "category", "product").order_by(
            "-is_enabled", "-priority", "-starts_at"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["now"] = timezone.now()
        return context


class PromotionCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = Promotion
    form_class = PromotionForm
    template_name = "dashboard/promotions/form.html"
    success_url = reverse_lazy("dashboard:promotion_list")
    success_text = gettext_lazy("Promotion saved.")
    extra_context = {"title": gettext_lazy("New promotion")}


class PromotionUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Promotion
    form_class = PromotionForm
    template_name = "dashboard/promotions/form.html"
    success_url = reverse_lazy("dashboard:promotion_list")
    success_text = gettext_lazy("Promotion saved.")
    extra_context = {"title": gettext_lazy("Edit promotion")}


class PromotionDeleteView(ProtectedDeleteView):
    model = Promotion
    success_url = reverse_lazy("dashboard:promotion_list")
    deleted_text = gettext_lazy("Promotion deleted.")

    def get_consequences(self):
        return [_("Prices return to normal immediately. Existing orders are not affected.")]


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
class CustomerListView(StaffRequiredMixin, ListView):
    template_name = "dashboard/customers/list.html"
    context_object_name = "customers"
    paginate_by = PAGE_SIZE

    def get_queryset(self):
        self.filter_form = CustomerFilterForm(self.request.GET or None)
        queryset = (
            User.objects.filter(is_staff=False)
            .annotate(
                order_count=Count("orders", distinct=True),
                total_spent=Coalesce(Sum("orders__total", filter=Q(orders__status__in=SALES_STATUSES)), MONEY_ZERO),
                last_order_at=Max("orders__created_at"),
            )
            .order_by("-date_joined")
        )
        if self.filter_form.is_valid() and self.filter_form.cleaned_data.get("q"):
            term = self.filter_form.cleaned_data["q"].strip()
            queryset = queryset.filter(
                Q(full_name__icontains=term) | Q(email__icontains=term) | Q(phone__icontains=term)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        return context


class CustomerDetailView(StaffRequiredMixin, DetailView):
    template_name = "dashboard/customers/detail.html"
    context_object_name = "customer"

    def get_queryset(self):
        return User.objects.filter(is_staff=False).prefetch_related("addresses")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["orders"] = Order.objects.filter(customer=self.object).order_by("-created_at")[:50]
        context["customer_whatsapp_url"] = customer_whatsapp_url(self.object.phone)
        return context


# ---------------------------------------------------------------------------
# Site settings
# ---------------------------------------------------------------------------
class SiteSettingsUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    form_class = SiteSettingsForm
    template_name = "dashboard/generic_form.html"
    success_url = reverse_lazy("dashboard:settings")
    success_text = gettext_lazy("Store settings saved.")
    extra_context = {"title": gettext_lazy("Store settings")}

    def get_object(self, queryset=None):
        return SiteSettings.load()
