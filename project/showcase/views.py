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

    # В статусе учитываются вообще все карточки из базы:
    # активные и отключенные.
    last_product_created_at = Product.objects.aggregate(
        last_created_at=Max("created_at")
    )["last_created_at"]

    context = {
        "products": products,
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
