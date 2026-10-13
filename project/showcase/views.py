from django.db.models import Max
from django.shortcuts import render
from django.utils import timezone

from .models import Product


def product_showcase(request):
    # На витрину выводятся только активные предложения.
    products = Product.objects.filter(is_active=True)

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
