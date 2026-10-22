from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from showcase.models import Product
from showcase.views import MAX_SHOWCASE_OFFERS


def make_leads_offer(
    external_id,
    *,
    provider_name="Тест МФО",
    max_amount="30000",
    max_term="30",
    rate="0.8",
    other_epc="10.00",
    tracking_url=None,
):
    if tracking_url is None:
        tracking_url = (
            f"https://example.com/offers/"
            f"{external_id}"
        )

    return {
        "id": str(external_id),
        "status": "active",
        "site_name": provider_name,
        "description": (
            "<p>Безопасное описание оффера</p>"
        ),
        "site_condition": "",
        "extendedFields": {
            "Условия кредитования": {
                "Сумма кредита от": "1000",
                "Сумма кредита до": max_amount,
                "Срок кредитования от": "5",
                "Срок кредитования до": max_term,
                "Проценты по кредиту": rate,
                "Первый займ под 0%": "да",
            }
        },
        "tracking_urls": [
            {
                "platform_id": "123",
                "urls": [
                    tracking_url,
                ],
            }
        ],
        "logo": (
            "https://example.com/logo.png"
        ),
        "modified": "2026-01-01 12:00:00",
        "detail_stats": {
            "system": {
                "other_epc": other_epc,
            }
        },
    }


@override_settings(
    LEADS_API_TOKEN="test-token",
    LEADS_PLATFORM_ID="123",
)
class ImportToShowcaseEndToEndTests(TestCase):
    def run_sync(self, offers):
        with patch(
            "showcase.management.commands."
            "sync_leads_offers."
            "LeadsSuClient.fetch_all_active_offers",
            return_value=offers,
        ):
            call_command(
                "sync_leads_offers",
                stdout=StringIO(),
            )

    def get_showcase(self):
        return self.client.get(
            reverse(
                "showcase:product_showcase"
            )
        )

    def test_imported_offer_appears_on_public_showcase(self):
        self.run_sync(
            [
                make_leads_offer(
                    "1001",
                    provider_name="E2E МФО",
                )
            ]
        )

        product = Product.objects.get(
            source="leads_su",
            external_id="1001",
        )

        self.assertTrue(product.is_active)

        response = self.get_showcase()

        self.assertEqual(
            response.status_code,
            200,
        )

        products = list(
            response.context["products"]
        )

        self.assertIn(product, products)
        self.assertContains(
            response,
            "E2E МФО",
        )
        self.assertContains(
            response,
            "от 1 000 до 30 000 ₽",
        )
        self.assertContains(
            response,
            "от 5 до 30 дней",
        )
        self.assertContains(
            response,
            "0,8%",
        )

    def test_imported_tracking_url_reaches_public_html(self):
        tracking_url = (
            "https://example.com/"
            "tracking/abc123"
        )

        self.run_sync(
            [
                make_leads_offer(
                    "1001",
                    tracking_url=tracking_url,
                )
            ]
        )

        response = self.get_showcase()

        self.assertContains(
            response,
            f'href="{tracking_url}"',
            html=False,
        )

        self.assertContains(
            response,
            'rel="nofollow sponsored noopener"',
            html=False,
        )

    def test_long_term_offer_gets_correct_category(self):
        self.run_sync(
            [
                make_leads_offer(
                    "1001",
                    max_term="60",
                )
            ]
        )

        product = Product.objects.get(
            source="leads_su",
            external_id="1001",
        )

        self.assertEqual(
            product.category,
            Product.Category.LONG_TERM,
        )

        response = self.get_showcase()

        self.assertContains(
            response,
            'data-categories="long_term new"',
            html=False,
        )

    def test_short_term_offer_gets_correct_category(self):
        self.run_sync(
            [
                make_leads_offer(
                    "1001",
                    max_term="30",
                )
            ]
        )

        product = Product.objects.get(
            source="leads_su",
            external_id="1001",
        )

        self.assertEqual(
            product.category,
            Product.Category.SHORT_TERM,
        )

        response = self.get_showcase()

        self.assertContains(
            response,
            'data-categories="short_term new"',
            html=False,
        )

    def test_second_sync_updates_existing_card_on_showcase(self):
        self.run_sync(
            [
                make_leads_offer(
                    "1001",
                    provider_name="Старое название",
                    max_amount="10000",
                )
            ]
        )

        self.run_sync(
            [
                make_leads_offer(
                    "1001",
                    provider_name="Новое название",
                    max_amount="50000",
                )
            ]
        )

        self.assertEqual(
            Product.objects.filter(
                source="leads_su",
                external_id="1001",
            ).count(),
            1,
        )

        response = self.get_showcase()

        self.assertContains(
            response,
            "Новое название",
        )
        self.assertContains(
            response,
            "от 1 000 до 50 000 ₽",
        )
        self.assertNotContains(
            response,
            "Старое название",
        )

    def test_offer_removed_from_api_disappears_from_showcase(self):
        self.run_sync(
            [
                make_leads_offer("1001"),
                make_leads_offer(
                    "1002",
                    provider_name="Исчезающий оффер",
                ),
            ]
        )

        first_response = self.get_showcase()

        self.assertContains(
            first_response,
            "Исчезающий оффер",
        )

        # Следующая успешная синхронизация:
        # 1002 больше не пришёл от API.
        self.run_sync(
            [
                make_leads_offer("1001"),
            ]
        )

        removed = Product.objects.get(
            source="leads_su",
            external_id="1002",
        )

        self.assertFalse(removed.is_active)

        second_response = self.get_showcase()

        self.assertNotContains(
            second_response,
            "Исчезающий оффер",
        )

    def test_manual_product_survives_import_sync(self):
        manual = Product.objects.create(
            provider_name="Ручной оффер",
            title="Ручной оффер",
            category=Product.Category.SHORT_TERM,
            amount_text="до 15 000 ₽",
            term_text="до 20 дней",
            rate_text="0,8%",
            product_url=(
                "https://example.com/manual"
            ),
            is_active=True,
        )

        self.run_sync(
            [
                make_leads_offer("1001"),
            ]
        )

        manual.refresh_from_db()

        self.assertTrue(manual.is_active)

        response = self.get_showcase()

        self.assertContains(
            response,
            "Ручной оффер",
        )

    def test_invalid_offer_is_not_published(self):
        invalid = make_leads_offer(
            "1001",
            provider_name="",
        )

        with self.assertLogs(
            "showcase.management.commands."
            "sync_leads_offers",
            level="WARNING",
        ):
            self.run_sync([invalid])

        self.assertFalse(
            Product.objects.filter(
                source="leads_su",
                external_id="1001",
            ).exists()
        )

        response = self.get_showcase()

        self.assertEqual(
            list(response.context["products"]),
            [],
        )

    def test_showcase_orders_imported_offers_by_epc(self):
        self.run_sync(
            [
                make_leads_offer(
                    "low",
                    provider_name="Low EPC",
                    other_epc="10.00",
                ),
                make_leads_offer(
                    "high",
                    provider_name="High EPC",
                    other_epc="100.00",
                ),
                make_leads_offer(
                    "medium",
                    provider_name="Medium EPC",
                    other_epc="50.00",
                ),
            ]
        )

        response = self.get_showcase()

        products = list(
            response.context["products"]
        )

        self.assertEqual(
            [
                product.provider_name
                for product in products
            ],
            [
                "High EPC",
                "Medium EPC",
                "Low EPC",
            ],
        )

    def test_priority_still_beats_higher_epc(self):
        self.run_sync(
            [
                make_leads_offer(
                    "low",
                    provider_name="Priority Low EPC",
                    other_epc="1.00",
                ),
                make_leads_offer(
                    "high",
                    provider_name="Regular High EPC",
                    other_epc="999.00",
                ),
            ]
        )

        priority = Product.objects.get(
            external_id="low",
        )

        priority.is_priority_offer = True
        priority.save(
            update_fields=[
                "is_priority_offer",
            ]
        )

        response = self.get_showcase()

        products = list(
            response.context["products"]
        )

        self.assertEqual(
            products[0].provider_name,
            "Priority Low EPC",
        )
        self.assertEqual(
            products[1].provider_name,
            "Regular High EPC",
        )

    def test_showcase_never_exceeds_maximum(self):
        offers = [
            make_leads_offer(
                str(index),
                provider_name=f"МФО {index}",
                other_epc=str(index),
            )
            for index in range(
                MAX_SHOWCASE_OFFERS + 5
            )
        ]

        self.run_sync(offers)

        self.assertEqual(
            Product.objects.filter(
                source="leads_su",
            ).count(),
            MAX_SHOWCASE_OFFERS + 5,
        )

        response = self.get_showcase()

        self.assertEqual(
            len(response.context["products"]),
            MAX_SHOWCASE_OFFERS,
        )

    def test_epc_is_persisted_as_decimal(self):
        self.run_sync(
            [
                make_leads_offer(
                    "1001",
                    other_epc="123.45",
                )
            ]
        )

        product = Product.objects.get(
            external_id="1001",
        )

        self.assertEqual(
            product.other_epc,
            Decimal("123.45"),
        )

    def test_imported_html_description_is_not_rendered_as_script(self):
        offer = make_leads_offer(
            "1001",
            provider_name="Безопасное МФО",
        )

        offer["description"] = (
            "<script>alert('xss')</script>"
            "<p>Обычный текст</p>"
        )

        self.run_sync([offer])

        product = Product.objects.get(
            external_id="1001",
        )

        self.assertNotIn(
            "<script>",
            product.description,
        )

        response = self.get_showcase()

        self.assertNotContains(
            response,
            "<script>alert('xss')</script>",
            html=False,
        )
