import io

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import DashboardProductForm
from .models import Product
from .views import MAX_SHOWCASE_OFFERS


def staff_required(view):
    return user_passes_test(
        lambda user: user.is_authenticated and user.is_staff,
        login_url="showcase:dashboard_login",
    )(view)


def login_view(request):
    if request.user.is_staff:
        return redirect("showcase:dashboard")

    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.get_user()

        if not user.is_staff:
            form.add_error(None, "Доступ в кабинет только для сотрудников.")
        else:
            login(request, user)
            return redirect("showcase:dashboard")

    return render(
        request,
        "dashboard/login.html",
        {"form": form},
    )


@require_POST
def logout_view(request):
    logout(request)

    return redirect("showcase:dashboard_login")


@staff_required
def dashboard(request):
    # Кабинет всегда загружает полный список офферов один раз.
    # Переключение фильтров после загрузки выполняется в браузере
    # через dashboard.js без дополнительных запросов к Django.
    products = list(
        Product.objects.order_by(
            "-is_priority_offer",
            "-is_active",
            "sort_order",
            "-updated_at",
        )
    )

    stats = Product.objects.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        priority=Count("id", filter=Q(is_priority_offer=True)),
        hidden=Count("id", filter=Q(is_active=False)),
    )

    # Определяем те же офферы, которые реально попадают
    # на публичную витрину. Это нужно для JS-фильтра
    # «На витрине».
    showcase_product_ids = set(
        Product.objects.filter(is_active=True)
        .order_by(
            "-is_priority_offer",
            "-other_epc",
            "sort_order",
            "-created_at",
            "id",
        )
        .values_list("id", flat=True)[:MAX_SHOWCASE_OFFERS]
    )

    showcase_count = len(showcase_product_ids)

    context = {
        "products": products,
        "stats": stats,
        "showcase_count": showcase_count,
        "showcase_product_ids": showcase_product_ids,
    }

    return render(
        request,
        "dashboard/dashboard.html",
        context,
    )


@staff_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        form = DashboardProductForm(request.POST, instance=product)

        if form.is_valid():
            form.save()
            messages.success(request, "Изменения сохранены.")

            return redirect("showcase:dashboard")
    else:
        form = DashboardProductForm(instance=product)

    return render(
        request,
        "dashboard/product_edit.html",
        {
            "form": form,
            "product": product,
        },
    )


@staff_required
@require_POST
def toggle_active(request, pk):
    product = get_object_or_404(Product, pk=pk)

    product.is_active = not product.is_active
    product.save(update_fields=["is_active", "updated_at"])

    state = "включено на витрине" if product.is_active else "скрыто с витрины"
    messages.success(request, f"«{product.provider_name}» — {state}.")

    return redirect("showcase:dashboard")


@staff_required
@require_POST
def toggle_priority(request, pk):
    product = get_object_or_404(Product, pk=pk)

    product.is_priority_offer = not product.is_priority_offer
    product.save(update_fields=["is_priority_offer", "updated_at"])

    state = "назначен приоритет" if product.is_priority_offer else "приоритет снят"
    messages.success(request, f"«{product.provider_name}» — {state}.")

    return redirect("showcase:dashboard")


@staff_required
@require_POST
def sync_offers(request):
    output = io.StringIO()

    try:
        call_command(
            "sync_leads_offers",
            stdout=output,
            no_color=True,
        )
    except CommandError as exc:
        messages.error(request, f"Синхронизация не выполнена: {exc}")
    else:
        messages.success(
            request,
            output.getvalue().strip() or "Синхронизация завершена.",
        )

    return redirect("showcase:dashboard")


@staff_required
@require_POST
def product_delete(request, pk):
    """Удаление одного оффера. Только POST + подтверждение на клиенте."""
    product = get_object_or_404(Product, pk=pk)

    name = product.provider_name
    product.delete()

    messages.success(request, f"«{name}» удалён с витрины.")

    return redirect("showcase:dashboard")


@staff_required
@require_POST
def bulk_actions(request):
    """Групповые действия над выбранными чекбоксами офферами."""
    action = request.POST.get("action", "")
    ids = []

    for raw_pk in request.POST.getlist("pks"):
        try:
            ids.append(int(raw_pk))
        except (TypeError, ValueError):
            continue

    if not ids:
        messages.warning(request, "Не выбрано ни одного оффера.")

        return redirect("showcase:dashboard")

    queryset = Product.objects.filter(pk__in=ids)

    if action == "toggle_visible":
        updated = 0

        for product in queryset:
            product.is_active = not product.is_active
            product.save(update_fields=["is_active"])
            updated += 1

        messages.success(
            request,
            f"Переключена видимость у {updated} офферов.",
        )
    elif action == "toggle_priority":
        updated = 0

        for product in queryset:
            product.is_priority_offer = not product.is_priority_offer
            product.save(update_fields=["is_priority_offer"])
            updated += 1

        messages.success(
            request,
            f"Переключен приоритет у {updated} офферов.",
        )
    elif action == "delete":
        deleted, _ = queryset.delete()
        messages.success(
            request,
            f"Удалено предложений: {deleted}.",
        )
    else:
        messages.warning(request, "Неизвестное действие.")

    return redirect("showcase:dashboard")
