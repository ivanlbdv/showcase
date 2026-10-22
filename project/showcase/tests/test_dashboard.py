from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from showcase.models import Product


class DashboardTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.staff_user = User.objects.create_user(
            username="admin",
            password="test-password-123",
            is_staff=True,
        )

        cls.regular_user = User.objects.create_user(
            username="regular",
            password="test-password-123",
            is_staff=False,
        )

        cls.product = Product.objects.create(
            provider_name="Test MFO",
            title="Test Product",
            category=Product.Category.SHORT_TERM,
            amount_text="до 30 000 ₽",
            term_text="до 30 дней",
            rate_text="0,8%",
            psk_text="292,00%",
            product_url="https://example.com/product",
            is_active=True,
            is_priority_offer=False,
        )

    def setUp(self):
        self.client.force_login(self.staff_user)

    def test_dashboard_requires_authentication(self):
        self.client.logout()

        response = self.client.get(
            reverse("showcase:dashboard"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("showcase:dashboard_login"),
            response.url,
        )

    def test_dashboard_rejects_non_staff_user(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(
            reverse("showcase:dashboard"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("showcase:dashboard_login"),
            response.url,
        )

    def test_staff_user_can_open_dashboard(self):
        response = self.client.get(
            reverse("showcase:dashboard"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.provider_name)

    def test_invalid_filter_falls_back_to_all(self):
        response = self.client.get(
            reverse("showcase:dashboard"),
            {"filter": "invalid-filter"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["filter"], "all")

    def test_delete_rejects_get(self):
        response = self.client.get(
            reverse(
                "showcase:dashboard_delete",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(
            Product.objects.filter(pk=self.product.pk).exists()
        )

    def test_delete_accepts_staff_post(self):
        response = self.client.post(
            reverse(
                "showcase:dashboard_delete",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Product.objects.filter(pk=self.product.pk).exists()
        )

    def test_delete_requires_staff(self):
        self.client.force_login(self.regular_user)

        response = self.client.post(
            reverse(
                "showcase:dashboard_delete",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Product.objects.filter(pk=self.product.pk).exists()
        )

    def test_toggle_active_rejects_get(self):
        response = self.client.get(
            reverse(
                "showcase:dashboard_toggle_active",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(response.status_code, 405)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_toggle_active_accepts_post(self):
        response = self.client.post(
            reverse(
                "showcase:dashboard_toggle_active",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_toggle_priority_rejects_get(self):
        response = self.client.get(
            reverse(
                "showcase:dashboard_toggle_priority",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(response.status_code, 405)

        self.product.refresh_from_db()
        self.assertFalse(self.product.is_priority_offer)

    def test_toggle_priority_accepts_post(self):
        response = self.client.post(
            reverse(
                "showcase:dashboard_toggle_priority",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_priority_offer)

    def test_bulk_action_rejects_get(self):
        response = self.client.get(
            reverse("showcase:dashboard_bulk"),
        )

        self.assertEqual(response.status_code, 405)

    def test_bulk_hide(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "hide",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_bulk_show(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "show",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_bulk_make_priority(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "make_priority",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_priority_offer)

    def test_bulk_delete(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "delete",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Product.objects.filter(pk=self.product.pk).exists()
        )

    def test_bulk_ignores_invalid_primary_keys(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "delete",
                "pks": ["not-an-integer"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Product.objects.filter(pk=self.product.pk).exists()
        )

    def test_logout_rejects_get(self):
        response = self.client.get(
            reverse("showcase:dashboard_logout"),
        )

        self.assertEqual(response.status_code, 405)

    def test_logout_accepts_post(self):
        response = self.client.post(
            reverse("showcase:dashboard_logout"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("showcase:dashboard_login"),
        )


class DashboardCsrfTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.staff_user = User.objects.create_user(
            username="admin",
            password="test-password-123",
            is_staff=True,
        )

        cls.product = Product.objects.create(
            provider_name="Test MFO",
            title="Test Product",
            category=Product.Category.SHORT_TERM,
            amount_text="до 30 000 ₽",
            term_text="до 30 дней",
            rate_text="0,8%",
            product_url="https://example.com/product",
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.staff_user)

    def test_delete_without_csrf_token_is_rejected(self):
        response = self.client.post(
            reverse(
                "showcase:dashboard_delete",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            Product.objects.filter(pk=self.product.pk).exists()
        )

    def test_toggle_without_csrf_token_is_rejected(self):
        response = self.client.post(
            reverse(
                "showcase:dashboard_toggle_active",
                args=[self.product.pk],
            ),
        )

        self.assertEqual(response.status_code, 403)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_bulk_action_without_csrf_token_is_rejected(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "delete",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            Product.objects.filter(pk=self.product.pk).exists()
        )
