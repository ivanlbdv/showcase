from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from showcase.integrations.leads_su import (LeadsSuAPIError, LeadsSuClient,
                                            OfferValidationError,
                                            _is_valid_https_url,
                                            _optional_https_url,
                                            _select_tracking_url)


class HttpsUrlValidationTests(SimpleTestCase):
    def test_accepts_https_url(self):
        self.assertTrue(
            _is_valid_https_url(
                "https://example.com/path?foo=bar"
            )
        )

    def test_rejects_http_url(self):
        self.assertFalse(
            _is_valid_https_url(
                "http://example.com/path"
            )
        )

    def test_rejects_relative_url(self):
        self.assertFalse(
            _is_valid_https_url(
                "/internal/path"
            )
        )

    def test_rejects_url_without_host(self):
        self.assertFalse(
            _is_valid_https_url(
                "https:///path"
            )
        )

    def test_optional_logo_rejects_non_https_url(self):
        result = _optional_https_url(
            "http://example.com/logo.png",
            "logo",
        )

        self.assertEqual(result, "")


class TrackingUrlTests(SimpleTestCase):
    def test_selects_https_url_for_correct_platform(self):
        tracking_urls = [
            {
                "platform_id": "123",
                "urls": [
                    "https://example.com/landing",
                ],
            }
        ]

        result = _select_tracking_url(
            tracking_urls,
            "123",
        )

        self.assertEqual(
            result,
            "https://example.com/landing",
        )

    def test_rejects_http_only_tracking_urls(self):
        tracking_urls = [
            {
                "platform_id": "123",
                "urls": [
                    "http://example.com/landing",
                ],
            }
        ]

        with self.assertRaises(OfferValidationError):
            _select_tracking_url(
                tracking_urls,
                "123",
            )

    def test_does_not_use_url_from_another_platform(self):
        tracking_urls = [
            {
                "platform_id": "999",
                "urls": [
                    "https://example.com/landing",
                ],
            }
        ]

        with self.assertRaises(OfferValidationError):
            _select_tracking_url(
                tracking_urls,
                "123",
            )


class LeadsSuClientTests(SimpleTestCase):
    def test_empty_token_is_rejected(self):
        client = LeadsSuClient(
            api_token="",
            platform_id="123",
        )

        with self.assertRaises(LeadsSuAPIError):
            client.fetch_all_active_offers()

    def test_empty_platform_id_is_rejected(self):
        client = LeadsSuClient(
            api_token="test-token",
            platform_id="",
        )

        with self.assertRaises(LeadsSuAPIError):
            client.fetch_all_active_offers()

    @patch("showcase.integrations.leads_su.requests.Session.get")
    def test_request_uses_fixed_leads_su_endpoint(
        self,
        mock_get,
    ):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "status": "success",
            "code": 200,
            "count": 0,
            "data": [],
        }
        response.raise_for_status.return_value = None

        mock_get.return_value = response

        client = LeadsSuClient(
            api_token="test-secret-token",
            platform_id="123",
        )

        result = client.fetch_all_active_offers()

        self.assertEqual(result, [])

        mock_get.assert_called_once()

        args, kwargs = mock_get.call_args

        self.assertEqual(
            args[0],
            LeadsSuClient.BASE_URL,
        )

        self.assertEqual(
            kwargs["params"]["token"],
            "test-secret-token",
        )
        self.assertEqual(
            kwargs["params"]["platform_id"],
            "123",
        )
        self.assertEqual(
            kwargs["params"]["status"],
            "active",
        )
        self.assertEqual(
            kwargs["timeout"],
            (5, 30),
        )
