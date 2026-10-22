from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from showcase.models import Product


def create_product(**overrides):
    data = {
        "provider_name": "Тест МФО",
        "title": "Тестовый займ",
        "category": Product.Category.SHORT_TERM,
        "amount_text": "до 30 000 ₽",
        "term_text": "до 30 дней",
        "rate_text": "0,8%",
        "psk_text": "0,00 – 292,00%",
        "product_url": "https://example.com/product",
    }

    data.update(overrides)

    return Product.objects.create(**data)


class ProductModelTests(TestCase):
    def test_default_values(self):
        product = create_product()

        self.assertEqual(product.source, "manual")
        self.assertIsNone(product.external_id)
        self.assertIsNone(product.external_modified_at)
        self.assertEqual(product.logo_url, "")
        self.assertFalse(product.is_for_new_clients)
        self.assertFalse(product.is_priority_offer)
        self.assertTrue(product.is_active)
        self.assertEqual(
            product.other_epc,
            Decimal("0.00"),
        )
        self.assertEqual(product.sort_order, 0)

    def test_string_representation(self):
        product = create_product(
            provider_name="МФО Пример",
            title="До зарплаты",
        )

        self.assertEqual(
            str(product),
            "МФО Пример — До зарплаты",
        )

    def test_category_choices(self):
        self.assertEqual(
            Product.Category.SHORT_TERM,
            "short_term",
        )
        self.assertEqual(
            Product.Category.LONG_TERM,
            "long_term",
        )

    def test_invalid_category_fails_full_clean(self):
        product = create_product(
            category="invalid-category",
        )

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_negative_sort_order_fails_validation(self):
        product = create_product()

        product.sort_order = -1

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_invalid_product_url_fails_validation(self):
        product = create_product()

        product.product_url = "not-a-url"

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_invalid_logo_url_fails_validation(self):
        product = create_product()

        product.logo_url = "not-a-url"

        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_blank_logo_url_is_valid(self):
        product = create_product(
            logo_url="",
        )

        product.full_clean()

    def test_created_at_and_updated_at_are_set(self):
        product = create_product()

        self.assertIsNotNone(product.created_at)
        self.assertIsNotNone(product.updated_at)

    def test_multiple_manual_products_can_have_null_external_id(self):
        create_product(
            provider_name="Manual 1",
        )
        create_product(
            provider_name="Manual 2",
        )

        self.assertEqual(
            Product.objects.filter(
                source="manual",
                external_id__isnull=True,
            ).count(),
            2,
        )


class ProductDatabaseConstraintTests(TestCase):
    def test_same_source_and_external_id_must_be_unique(self):
        create_product(
            source="leads_su",
            external_id="1001",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_product(
                    source="leads_su",
                    external_id="1001",
                )

    def test_same_external_id_is_allowed_for_different_sources(self):
        create_product(
            source="leads_su",
            external_id="1001",
        )

        create_product(
            source="another_source",
            external_id="1001",
        )

        self.assertEqual(
            Product.objects.filter(
                external_id="1001",
            ).count(),
            2,
        )

    def test_null_external_id_is_not_unique(self):
        create_product(
            source="manual",
            external_id=None,
        )

        create_product(
            source="manual",
            external_id=None,
        )

        self.assertEqual(
            Product.objects.filter(
                source="manual",
                external_id__isnull=True,
            ).count(),
            2,
        )

    def test_unique_constraint_is_declared(self):
        constraint_names = {
            constraint.name
            for constraint in Product._meta.constraints
        }

        self.assertIn(
            "unique_product_source_external_id",
            constraint_names,
        )


class ProductMetaTests(TestCase):
    def test_default_model_ordering(self):
        self.assertEqual(
            Product._meta.ordering,
            (
                "sort_order",
                "-created_at",
                "id",
            ),
        )

    def test_verbose_name(self):
        self.assertEqual(
            Product._meta.verbose_name,
            "Финансовое предложение",
        )

    def test_verbose_name_plural(self):
        self.assertEqual(
            Product._meta.verbose_name_plural,
            "Финансовые предложения",
        )
