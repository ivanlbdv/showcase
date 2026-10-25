from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase
from showcase.integrations.leads_su import (DEFAULT_PSK_TEXT,
                                            DEFAULT_RATE_TEXT, LeadsSuAPIError,
                                            LeadsSuClient,
                                            OfferValidationError,
                                            _extract_psk,
                                            _extract_terms_from_text,
                                            _parse_other_epc,
                                            _select_tracking_url, _strip_html,
                                            normalize_offer)


def make_offer(**overrides):
    """
    Минимальный валидный оффер Leads.su для unit-тестов.
    """
    offer = {
        "id": "1001",
        "status": "active",
        "site_name": "Тест МФО",
        "description": "<p>Тестовое описание</p>",
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
                "other_epc": "12.50",
            }
        },
    }

    offer.update(overrides)
    return offer


class LeadsSuPaginationTests(SimpleTestCase):
    def setUp(self):
        self.client = LeadsSuClient(
            api_token="test-token",
            platform_id="123",
        )

    @patch.object(LeadsSuClient, "_request_page")
    def test_fetches_all_pages(self, request_page):
        request_page.side_effect = [
            {
                "count": 3,
                "data": [
                    {"id": "1"},
                    {"id": "2"},
                ],
            },
            {
                "count": 3,
                "data": [
                    {"id": "3"},
                ],
            },
        ]

        result = self.client.fetch_all_active_offers()

        self.assertEqual(
            [offer["id"] for offer in result],
            ["1", "2", "3"],
        )

        self.assertEqual(request_page.call_count, 2)
        request_page.assert_any_call(offset=0)
        request_page.assert_any_call(offset=2)

    @patch.object(LeadsSuClient, "_request_page")
    def test_empty_first_page_is_valid_when_count_is_zero(
        self,
        request_page,
    ):
        request_page.return_value = {
            "count": 0,
            "data": [],
        }

        result = self.client.fetch_all_active_offers()

        self.assertEqual(result, [])

    @patch.object(LeadsSuClient, "_request_page")
    def test_empty_page_before_expected_count_raises_error(
        self,
        request_page,
    ):
        request_page.side_effect = [
            {
                "count": 2,
                "data": [{"id": "1"}],
            },
            {
                "count": 2,
                "data": [],
            },
        ]

        with self.assertRaises(LeadsSuAPIError):
            self.client.fetch_all_active_offers()

    @patch.object(LeadsSuClient, "_request_page")
    def test_changed_count_between_pages_raises_error(
        self,
        request_page,
    ):
        request_page.side_effect = [
            {
                "count": 3,
                "data": [{"id": "1"}],
            },
            {
                "count": 4,
                "data": [{"id": "2"}],
            },
        ]

        with self.assertRaises(LeadsSuAPIError):
            self.client.fetch_all_active_offers()

    @patch.object(LeadsSuClient, "_request_page")
    def test_non_list_data_raises_error(
        self,
        request_page,
    ):
        request_page.return_value = {
            "count": 1,
            "data": {"id": "1"},
        }

        with self.assertRaises(LeadsSuAPIError):
            self.client.fetch_all_active_offers()

    @patch.object(LeadsSuClient, "_request_page")
    def test_invalid_count_raises_error(
        self,
        request_page,
    ):
        request_page.return_value = {
            "count": "invalid",
            "data": [],
        }

        with self.assertRaises(LeadsSuAPIError):
            self.client.fetch_all_active_offers()

    @patch.object(LeadsSuClient, "_request_page")
    def test_negative_count_raises_error(
        self,
        request_page,
    ):
        request_page.return_value = {
            "count": -1,
            "data": [],
        }

        with self.assertRaises(LeadsSuAPIError):
            self.client.fetch_all_active_offers()


class LeadsSuHttpTests(SimpleTestCase):
    def setUp(self):
        self.client = LeadsSuClient(
            api_token="secret-test-token",
            platform_id="123",
        )

    @patch.object(LeadsSuClient, "_sleep_before_retry")
    def test_retries_after_500(self, sleep_mock):
        failed_response = Mock()
        failed_response.status_code = 500
        failed_response.headers = {}

        successful_response = Mock()
        successful_response.status_code = 200
        successful_response.headers = {}
        successful_response.raise_for_status.return_value = None
        successful_response.json.return_value = {
            "status": "success",
            "code": 200,
            "count": 0,
            "data": [],
        }

        self.client.session.get = Mock(
            side_effect=[
                failed_response,
                successful_response,
            ]
        )

        result = self.client._request_page(offset=0)

        self.assertEqual(result["status"], "success")
        self.assertEqual(self.client.session.get.call_count, 2)
        sleep_mock.assert_called_once()

    @patch.object(LeadsSuClient, "_sleep_before_retry")
    def test_retries_after_429(self, sleep_mock):
        rate_limited = Mock()
        rate_limited.status_code = 429
        rate_limited.headers = {
            "Retry-After": "1",
        }

        successful = Mock()
        successful.status_code = 200
        successful.headers = {}
        successful.raise_for_status.return_value = None
        successful.json.return_value = {
            "status": "success",
            "code": 200,
            "count": 0,
            "data": [],
        }

        self.client.session.get = Mock(
            side_effect=[
                rate_limited,
                successful,
            ]
        )

        result = self.client._request_page(offset=0)

        self.assertEqual(result["code"], 200)
        sleep_mock.assert_called_once()

    @patch.object(LeadsSuClient, "_sleep_before_retry")
    def test_network_error_is_retried(
        self,
        sleep_mock,
    ):
        successful = Mock()
        successful.status_code = 200
        successful.headers = {}
        successful.raise_for_status.return_value = None
        successful.json.return_value = {
            "status": "success",
            "code": 200,
            "count": 0,
            "data": [],
        }

        self.client.session.get = Mock(
            side_effect=[
                requests.ConnectionError("network error"),
                successful,
            ]
        )

        result = self.client._request_page(offset=0)

        self.assertEqual(result["status"], "success")
        self.assertEqual(self.client.session.get.call_count, 2)
        sleep_mock.assert_called_once()

    @patch.object(LeadsSuClient, "_sleep_before_retry")
    def test_network_error_after_all_retries_raises_api_error(
        self,
        sleep_mock,
    ):
        self.client.session.get = Mock(
            side_effect=requests.ConnectionError(
                "network error"
            )
        )

        with self.assertRaises(LeadsSuAPIError):
            self.client._request_page(offset=0)

        self.assertEqual(
            self.client.session.get.call_count,
            LeadsSuClient.MAX_RETRIES,
        )

    def test_invalid_json_raises_api_error(self):
        response = Mock()
        response.status_code = 200
        response.headers = {}
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError(
            "invalid json"
        )

        self.client.session.get = Mock(
            return_value=response
        )

        with self.assertRaises(LeadsSuAPIError):
            self.client._request_page(offset=0)

    def test_json_must_be_dictionary(self):
        response = Mock()
        response.status_code = 200
        response.headers = {}
        response.raise_for_status.return_value = None
        response.json.return_value = []

        self.client.session.get = Mock(
            return_value=response
        )

        with self.assertRaises(LeadsSuAPIError):
            self.client._request_page(offset=0)

    def test_api_error_status_raises_api_error(self):
        response = Mock()
        response.status_code = 200
        response.headers = {}
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "error",
            "code": 400,
            "error": "test error",
        }

        self.client.session.get = Mock(
            return_value=response
        )

        with self.assertRaises(LeadsSuAPIError):
            self.client._request_page(offset=0)

    def test_token_and_platform_are_sent_in_params(self):
        response = Mock()
        response.status_code = 200
        response.headers = {}
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "success",
            "code": 200,
            "count": 0,
            "data": [],
        }

        self.client.session.get = Mock(
            return_value=response
        )

        self.client._request_page(offset=500)

        _, kwargs = self.client.session.get.call_args

        self.assertEqual(
            kwargs["params"]["token"],
            "secret-test-token",
        )
        self.assertEqual(
            kwargs["params"]["platform_id"],
            "123",
        )
        self.assertEqual(
            kwargs["params"]["offset"],
            500,
        )
        self.assertEqual(
            kwargs["params"]["limit"],
            LeadsSuClient.PAGE_SIZE,
        )
        self.assertEqual(
            kwargs["timeout"],
            (5, 30),
        )


class OfferNormalizationTests(SimpleTestCase):
    def test_normalizes_valid_offer(self):
        result = normalize_offer(
            make_offer(),
            platform_id="123",
        )

        self.assertEqual(result.external_id, "1001")
        self.assertEqual(
            result.provider_name,
            "Тест МФО",
        )
        self.assertEqual(
            result.title,
            "Тест МФО",
        )
        self.assertEqual(
            result.amount_text,
            "от 1 000 до 30 000 ₽",
        )
        self.assertEqual(
            result.term_text,
            "от 5 до 30 дней",
        )
        self.assertEqual(
            result.rate_text,
            "0,8%",
        )
        self.assertTrue(result.is_for_new_clients)
        self.assertEqual(
            result.other_epc,
            Decimal("12.50"),
        )
        self.assertEqual(
            result.product_url,
            "https://example.com/offer",
        )
        self.assertEqual(
            result.logo_url,
            "https://example.com/logo.png",
        )
        self.assertTrue(result.is_active)

    def test_rejects_offer_without_id(self):
        offer = make_offer(id="")

        with self.assertRaises(OfferValidationError):
            normalize_offer(
                offer,
                platform_id="123",
            )

    def test_rejects_offer_without_provider(self):
        offer = make_offer(site_name="")

        with self.assertRaises(OfferValidationError):
            normalize_offer(
                offer,
                platform_id="123",
            )

    def test_rejects_explicitly_inactive_offer(self):
        offer = make_offer(status="inactive")

        with self.assertRaises(OfferValidationError):
            normalize_offer(
                offer,
                platform_id="123",
            )

    def test_missing_status_is_allowed(self):
        offer = make_offer()
        offer.pop("status")

        result = normalize_offer(
            offer,
            platform_id="123",
        )

        self.assertEqual(result.external_id, "1001")

    def test_long_term_category_for_more_than_30_days(self):
        offer = make_offer()

        offer["extendedFields"]["Условия кредитования"][
            "Срок кредитования до"
        ] = "31"

        result = normalize_offer(
            offer,
            platform_id="123",
        )

        self.assertEqual(
            result.category,
            "long_term",
        )

    def test_short_term_category_for_exactly_30_days(self):
        result = normalize_offer(
            make_offer(),
            platform_id="123",
        )

        self.assertEqual(
            result.category,
            "short_term",
        )

    def test_invalid_structured_rate_uses_default(self):
        offer = make_offer()

        offer["extendedFields"]["Условия кредитования"][
            "Проценты по кредиту"
        ] = "99"

        result = normalize_offer(
            offer,
            platform_id="123",
        )

        self.assertEqual(
            result.rate_text,
            DEFAULT_RATE_TEXT,
        )

    def test_missing_psk_uses_default(self):
        result = normalize_offer(
            make_offer(),
            platform_id="123",
        )

        self.assertEqual(
            result.psk_text,
            DEFAULT_PSK_TEXT,
        )

    def test_psk_window_does_not_cross_lines(self):
        result = _extract_psk(
            "ПСК от 255,5% до 292% годовых\n"
            "Одобрение за 1 минуту"
        )

        self.assertEqual(result, "255,50 – 292,00%")

    def test_invalid_logo_does_not_reject_offer(self):
        offer = make_offer(
            logo="http://example.com/logo.png",
        )

        with self.assertLogs(
            "showcase.integrations.leads_su",
            level="WARNING",
        ):
            result = normalize_offer(
                offer,
                platform_id="123",
            )

        self.assertEqual(result.logo_url, "")

    def test_html_is_removed_from_description(self):
        offer = make_offer(
            description=(
                "<p>Hello</p>"
                "<script>alert(1)</script>"
                "<div>World</div>"
            ),
        )

        result = normalize_offer(
            offer,
            platform_id="123",
        )

        self.assertNotIn("<script>", result.description)
        self.assertNotIn("</script>", result.description)
        self.assertIn("Hello", result.description)
        self.assertIn("World", result.description)

    def test_fallback_parses_terms_from_text(self):
        offer = make_offer(
            extendedFields={},
            site_condition=(
                "Сумма займа от 1 000 до 20 000 ₽. "
                "Срок от 5 до 25 дней. "
                "Ставка 0,5%."
            ),
        )

        result = normalize_offer(
            offer,
            platform_id="123",
        )

        self.assertEqual(
            result.amount_text,
            "от 1 000 до 20 000 ₽",
        )
        self.assertEqual(
            result.term_text,
            "от 5 до 25 дней",
        )
        self.assertEqual(
            result.rate_text,
            "0,5%",
        )

    def test_missing_required_amount_is_rejected(self):
        offer = make_offer(
            extendedFields={},
            site_condition="Срок до 30 дней.",
        )

        with self.assertRaises(OfferValidationError):
            normalize_offer(
                offer,
                platform_id="123",
            )


class OfferHelperTests(SimpleTestCase):
    def test_strip_html_handles_encoded_html(self):
        result = _strip_html(
            "&lt;p&gt;Hello&lt;/p&gt;"
            "&lt;div&gt;World&lt;/div&gt;"
        )

        self.assertNotIn("<p>", result)
        self.assertNotIn("<div>", result)
        self.assertIn("Hello", result)
        self.assertIn("World", result)

    def test_extracts_amount_and_term(self):
        result = _extract_terms_from_text(
            "Займ от 2 000 до 40 000 ₽. "
            "Срок от 7 до 28 дней."
        )

        self.assertEqual(result["min_amount"], 2000)
        self.assertEqual(result["max_amount"], 40000)
        self.assertEqual(result["min_term_days"], 7)
        self.assertEqual(result["max_term_days"], 28)

    def test_other_epc_invalid_value_becomes_zero(self):
        self.assertEqual(
            _parse_other_epc("invalid"),
            Decimal("0.00"),
        )

    def test_other_epc_negative_value_becomes_zero(self):
        self.assertEqual(
            _parse_other_epc("-10"),
            Decimal("0.00"),
        )

    def test_tracking_url_prefers_default_landing(self):
        result = _select_tracking_url(
            [
                {
                    "platform_id": "123",
                    "urls": [
                        "https://example.com/?url_id=99",
                        "https://example.com/default",
                    ],
                }
            ],
            platform_id="123",
        )

        self.assertEqual(
            result,
            "https://example.com/default",
        )

    def test_legal_info_is_built_from_licenses_group(self):
        offer = make_offer()

        offer["extendedFields"]["Лицензии"] = {
            "Наименование ЮЛ": "ООО МКК «Алистар»",
            "Юридический адрес": "107023, Г.МОСКВА, ПЕР. СЕМЁНОВСКИЙ, Д. 19",
            "Телефон": "+7 (991) 760-62-82",
            "Email": "info@ali-star.ru",
            "ОГРН": "1247700596659",
            "ИНН": "9704249544",
            "Лицензия (N c датой)": "2403045010104 от 25.10.2024",
        }

        result = normalize_offer(offer, platform_id="123")

        self.assertIn("ООО МКК «Алистар»", result.legal_info)
        self.assertIn("ОГРН: 1247700596659", result.legal_info)
        self.assertIn("Лицензия (N c датой): 2403045010104", result.legal_info)
        # Контакты в витринный блок не попадают
        self.assertNotIn("Телефон", result.legal_info)
        self.assertNotIn("Email", result.legal_info)

    def test_legal_info_is_empty_without_licenses_group(self):
        result = normalize_offer(make_offer(), platform_id="123")

        self.assertEqual(result.legal_info, "")

    def test_weeks_convert_separately_for_low_and_high(self):
        result = _extract_terms_from_text(
            "Срок от 7 дней до 24 недель."
        )

        self.assertEqual(result["min_term_days"], 7)
        self.assertEqual(result["max_term_days"], 168)
