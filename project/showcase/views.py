from django.db.models import Max
from django.shortcuts import render
from django.utils import timezone

from .models import Product

# Максимум карточек на витрине независимо от размера базы.
MAX_SHOWCASE_OFFERS = 12


def product_showcase(request):
    # На витрину выводятся только активные предложения,
    # не более MAX_SHOWCASE_OFFERS в порядке сортировки:
    # приоритетные, затем по sort_order, затем по дате.
    products = list(
        Product.objects.filter(is_active=True)
        .order_by(
            "-is_priority_offer",
            "-other_epc",
            "sort_order",
            "-created_at",
            "id",
        )[:MAX_SHOWCASE_OFFERS]
    )

    # Реквизиты для футера: одна МФО — один блок, даже если
    # на витрине несколько её офферов. Первый попавшийся
    # непустой legal_info побеждает (у всех карточек одной
    # МФО он одинаковый — берётся из одной группы «Лицензии»).
    legal_items: dict[str, str] = {}

    for product in products:
        if product.legal_info:
            legal_items.setdefault(
                product.provider_name,
                product.legal_info,
            )

    # В статусе учитываются вообще все карточки из базы:
    # активные и отключенные.
    last_product_created_at = Product.objects.aggregate(
        last_created_at=Max("created_at")
    )["last_created_at"]

    context = {
        "products": products,
        "legal_items": list(legal_items.items()),
        "last_product_date": None,
        "is_updated_today": False,
    }

    if last_product_created_at is not None:
        last_product_date = timezone.localtime(
            last_product_created_at
        ).date()

        context["last_product_date"] = last_product_date
        context["is_updated_today"] = (
            last_product_date == timezone.localdate()
        )

    return render(
        request,
        "showcase/product_showcase.html",
        context,
    )


def privacy_policy(request):
    return render(
        request,
        "showcase/privacy.html",
    )
