from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from showcase.integrations.leads_su import LeadsSuAPIError
from showcase.models import Product


def make_raw_offer(
    external_id="1001",
    provider_name="Тест МФО",
):
    return {
        "id": external_id,
        "status": "active",
        "site_name": provider_name,
        "description": "<p>Описание оффера</p>",
        "site_condition": "",
        "extendedFields": {
            "Условия кредитования": {
                "Сумма кредита от": "1000",
                "Сумма кредита до": "30000",
                "Срок кредитования от": "5",
                "Срок кредитования до": "30",
                "Проценты по кредиту": "0.8",
                "Первый займ под 0%": "да",
            }
        },
        "tracking_urls": [
            {
                "platform_id": "123",
                "urls": [
                    "https://example.com/offer",
                ],
            }
        ],
        "logo": "https://example.com/logo.png",
        "modified": "2026-01-01 12:00:00",
        "detail_stats": {
            "system": {
                "other_epc": "10.50",
            }
        },
    }


@override_settings(
    LEADS_API_TOKEN="test-token",
    LEADS_PLATFORM_ID="123",
)
class SyncLeadsOffersTests(TestCase):
    def create_imported_product(
        self,
        external_id,
        *,
        provider_name="Старое название",
        is_active=True,
    ):
        return Product.objects.create(
            source="leads_su",
            external_id=external_id,
            provider_name=provider_name,
            title=provider_name,
            category=Product.Category.SHORT_TERM,
            amount_text="до 10 000 ₽",
            term_text="до 10 дней",
            rate_text="0,8%",
            product_url="https://example.com/old",
            is_active=is_active,
        )

    def create_manual_product(self):
        return Product.objects.create(
            source="manual",
            provider_name="Ручной оффер",
            title="Ручной оффер",
            category=Product.Category.SHORT_TERM,
            amount_text="до 10 000 ₽",
            term_text="до 10 дней",
            rate_text="0,8%",
            product_url="https://example.com/manual",
            is_active=True,
        )

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_creates_new_offer(
        self,
        fetch_mock,
    ):
        fetch_mock.return_value = [
            make_raw_offer("1001"),
        ]

        call_command(
            "sync_leads_offers",
            stdout=StringIO(),
        )

        product = Product.objects.get(
            source="leads_su",
            external_id="1001",
        )

        self.assertEqual(
            product.provider_name,
            "Тест МФО",
        )
        self.assertEqual(
            product.amount_text,
            "от 1 000 до 30 000 ₽",
        )
        self.assertTrue(product.is_active)

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_updates_existing_offer(
        self,
        fetch_mock,
    ):
        product = self.create_imported_product(
            "1001",
            provider_name="Старое название",
        )

        fetch_mock.return_value = [
            make_raw_offer(
                "1001",
                provider_name="Новое название",
            ),
        ]

        call_command(
            "sync_leads_offers",
            stdout=StringIO(),
        )

        product.refresh_from_db()

        self.assertEqual(
            product.provider_name,
            "Новое название",
        )
        self.assertEqual(
            product.title,
            "Новое название",
        )
        self.assertTrue(product.is_active)

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_missing_imported_offer_is_deactivated(
        self,
        fetch_mock,
    ):
        existing = self.create_imported_product(
            "old-offer",
        )

        fetch_mock.return_value = [
            make_raw_offer("new-offer"),
        ]

        call_command(
            "sync_leads_offers",
            stdout=StringIO(),
        )

        existing.refresh_from_db()

        self.assertFalse(existing.is_active)

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_manual_products_are_never_deactivated(
        self,
        fetch_mock,
    ):
        manual = self.create_manual_product()

        fetch_mock.return_value = []

        call_command(
            "sync_leads_offers",
            stdout=StringIO(),
        )

        manual.refresh_from_db()

        self.assertTrue(manual.is_active)

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_empty_successful_api_response_deactivates_imported_offers(
        self,
        fetch_mock,
    ):
        existing = self.create_imported_product(
            "1001",
        )

        fetch_mock.return_value = []

        call_command(
            "sync_leads_offers",
            stdout=StringIO(),
        )

        existing.refresh_from_db()

        self.assertFalse(existing.is_active)

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_api_failure_does_not_deactivate_existing_offers(
        self,
        fetch_mock,
    ):
        existing = self.create_imported_product(
            "1001",
        )

        fetch_mock.side_effect = LeadsSuAPIError(
            "API unavailable"
        )

        with self.assertRaises(CommandError):
            call_command(
                "sync_leads_offers",
                stdout=StringIO(),
            )

        existing.refresh_from_db()

        self.assertTrue(existing.is_active)

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_invalid_received_offer_does_not_deactivate_existing_product(
        self,
        fetch_mock,
    ):
        existing = self.create_imported_product(
            "1001",
        )

        invalid_offer = make_raw_offer("1001")

        # Делаем оффер невалидным, сохраняя его ID.
        invalid_offer["site_name"] = ""

        fetch_mock.return_value = [
            invalid_offer,
        ]

        with self.assertLogs(
            "showcase.management.commands.sync_leads_offers",
            level="WARNING",
        ):
            call_command(
                "sync_leads_offers",
                stdout=StringIO(),
            )

        existing.refresh_from_db()

        # Ключевая проверка:
        # ID был получен от API, поэтому временно битый оффер
        # не должен исчезнуть с витрины.
        self.assertTrue(existing.is_active)

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_invalid_new_offer_is_not_created(
        self,
        fetch_mock,
    ):
        invalid_offer = make_raw_offer("1001")
        invalid_offer["site_name"] = ""

        fetch_mock.return_value = [
            invalid_offer,
        ]

        with self.assertLogs(
            "showcase.management.commands.sync_leads_offers",
            level="WARNING",
        ):
            call_command(
                "sync_leads_offers",
                stdout=StringIO(),
            )

        self.assertFalse(
            Product.objects.filter(
                source="leads_su",
                external_id="1001",
            ).exists()
        )

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_dry_run_does_not_create_product(
        self,
        fetch_mock,
    ):
        fetch_mock.return_value = [
            make_raw_offer("1001"),
        ]

        output = StringIO()

        call_command(
            "sync_leads_offers",
            dry_run=True,
            stdout=output,
        )

        self.assertFalse(
            Product.objects.filter(
                source="leads_su",
                external_id="1001",
            ).exists()
        )

        self.assertIn(
            "Изменения в БД не вносились",
            output.getvalue(),
        )

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_dry_run_does_not_update_existing_product(
        self,
        fetch_mock,
    ):
        product = self.create_imported_product(
            "1001",
            provider_name="Старое название",
        )

        fetch_mock.return_value = [
            make_raw_offer(
                "1001",
                provider_name="Новое название",
            ),
        ]

        call_command(
            "sync_leads_offers",
            dry_run=True,
            stdout=StringIO(),
        )

        product.refresh_from_db()

        self.assertEqual(
            product.provider_name,
            "Старое название",
        )

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_dry_run_does_not_deactivate_missing_product(
        self,
        fetch_mock,
    ):
        product = self.create_imported_product(
            "1001",
        )

        fetch_mock.return_value = []

        call_command(
            "sync_leads_offers",
            dry_run=True,
            stdout=StringIO(),
        )

        product.refresh_from_db()

        self.assertTrue(product.is_active)

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_sync_does_not_create_duplicate_for_existing_external_id(
        self,
        fetch_mock,
    ):
        self.create_imported_product("1001")

        fetch_mock.return_value = [
            make_raw_offer("1001"),
        ]

        call_command(
            "sync_leads_offers",
            stdout=StringIO(),
        )

        self.assertEqual(
            Product.objects.filter(
                source="leads_su",
                external_id="1001",
            ).count(),
            1,
        )

    @patch(
        "showcase.management.commands.sync_leads_offers."
        "LeadsSuClient.fetch_all_active_offers"
    )
    def test_sync_output_contains_statistics(
        self,
        fetch_mock,
    ):
        fetch_mock.return_value = [
            make_raw_offer("1001"),
        ]

        output = StringIO()

        call_command(
            "sync_leads_offers",
            stdout=output,
        )

        text = output.getvalue()

        self.assertIn("получено=1", text)
        self.assertIn("создано=1", text)
        self.assertIn("обновлено=0", text)
        self.assertIn("деактивировано=0", text)
        self.assertIn("пропущено=0", text)
