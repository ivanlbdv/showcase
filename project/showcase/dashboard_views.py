import io

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
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
    # Фильтр из адресной строки: all | active | priority | hidden.
    filter_key = request.GET.get("filter", "all")

    if filter_key not in {"all", "active", "priority", "hidden"}:
        filter_key = "all"

    if filter_key == "active":
        # «На витрине» — ровно та же выборка, что на публичной
        # витрине: активные, приоритетные сверху, по EPC и порядку,
        # максимум 10 карточек.
        products = list(
            Product.objects.filter(is_active=True)
            .order_by(
                "-is_priority_offer",
                "-other_epc",
                "sort_order",
                "-created_at",
                "id",
            )[:10]
        )
    elif filter_key == "priority":
        products = Product.objects.filter(
            is_priority_offer=True,
        ).order_by(
            "-is_active",
            "sort_order",
            "-updated_at",
        )
    elif filter_key == "hidden":
        products = Product.objects.filter(
            is_active=False,
        ).order_by(
            "-is_priority_offer",
            "sort_order",
            "-updated_at",
        )
    else:
        # «Все» — реально всё из базы, включая скрытые.
        products = Product.objects.order_by(
            "-is_priority_offer",
            "-is_active",
            "sort_order",
            "-updated_at",
        )

    stats = Product.objects.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        priority=Count("id", filter=Q(is_priority_offer=True)),
        hidden=Count("id", filter=Q(is_active=False)),
    )

    # На витрине физически не больше MAX_SHOWCASE_OFFERS карточек
    # (см. константу в showcase/views.py), поэтому счётчик кабинета
    # не должен показывать больше.
    showcase_count = min(stats["active"], MAX_SHOWCASE_OFFERS)

    context = {
        "products": products,
        "stats": stats,
        "showcase_count": showcase_count,
        "filter": filter_key,
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

    if action == "make_priority":
        updated = queryset.update(is_priority_offer=True)
        messages.success(
            request,
            f"Отмечены приоритетными: {updated}.",
        )
    elif action == "hide":
        updated = queryset.filter(is_active=True).update(is_active=False)
        messages.success(
            request,
            f"Скрыто с витрины: {updated}.",
        )
    elif action == "show":
        updated = queryset.filter(is_active=False).update(is_active=True)
        messages.success(
            request,
            f"Показано на витрине: {updated}.",
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
