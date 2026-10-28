from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from showcase.models import Product
from showcase.views import MAX_SHOWCASE_OFFERS


class ProductShowcaseTests(TestCase):
    def create_product(
        self,
        index,
        *,
        is_active=True,
        is_priority_offer=False,
        other_epc=Decimal("0.00"),
        sort_order=0,
    ):
        return Product.objects.create(
            provider_name=f"MFO {index}",
            title=f"Product {index}",
            category=Product.Category.SHORT_TERM,
            amount_text="до 30 000 ₽",
            term_text="до 30 дней",
            rate_text="0,8%",
            product_url=f"https://example.com/product/{index}",
            is_active=is_active,
            is_priority_offer=is_priority_offer,
            other_epc=other_epc,
            sort_order=sort_order,
        )

    def test_showcase_is_public(self):
        self.create_product(1)

        response = self.client.get(
            reverse("showcase:product_showcase"),
        )

        self.assertEqual(response.status_code, 200)

    def test_inactive_products_are_not_displayed(self):
        active = self.create_product(
            1,
            is_active=True,
        )
        hidden = self.create_product(
            2,
            is_active=False,
        )

        response = self.client.get(
            reverse("showcase:product_showcase"),
        )

        products = list(response.context["products"])

        self.assertIn(active, products)
        self.assertNotIn(hidden, products)

    def test_showcase_contains_at_most_ten_products(self):
        for index in range(MAX_SHOWCASE_OFFERS + 5):
            self.create_product(index)

        response = self.client.get(
            reverse("showcase:product_showcase"),
        )

        products = response.context["products"]

        self.assertEqual(
            len(products),
            MAX_SHOWCASE_OFFERS,
        )

    def test_priority_products_are_shown_first(self):
        regular = self.create_product(
            1,
            is_priority_offer=False,
            other_epc=Decimal("100.00"),
        )

        priority = self.create_product(
            2,
            is_priority_offer=True,
            other_epc=Decimal("1.00"),
        )

        response = self.client.get(
            reverse("showcase:product_showcase"),
        )

        products = list(response.context["products"])

        self.assertEqual(products[0], priority)
        self.assertEqual(products[1], regular)

    def test_higher_epc_is_shown_first_with_same_priority(self):
        low_epc = self.create_product(
            1,
            other_epc=Decimal("10.00"),
        )

        high_epc = self.create_product(
            2,
            other_epc=Decimal("20.00"),
        )

        response = self.client.get(
            reverse("showcase:product_showcase"),
        )

        products = list(response.context["products"])

        self.assertEqual(products[0], high_epc)
        self.assertEqual(products[1], low_epc)


class PrivacyPolicyTests(TestCase):
    def test_privacy_policy_is_public(self):
        response = self.client.get(
            reverse("showcase:privacy_policy"),
        )

        self.assertEqual(response.status_code, 200)

    def test_privacy_policy_uses_expected_template(self):
        response = self.client.get(
            reverse("showcase:privacy_policy"),
        )

        self.assertTemplateUsed(
            response,
            "showcase/privacy.html",
        )

    def test_privacy_policy_contains_title(self):
        response = self.client.get(
            reverse("showcase:privacy_policy"),
        )

        self.assertContains(
            response,
            "Политика в отношении обработки персональных данных",
        )

    def test_showcase_contains_privacy_policy_link(self):
        response = self.client.get(
            reverse("showcase:product_showcase"),
        )

        self.assertContains(
            response,
            reverse("showcase:privacy_policy"),
        )
