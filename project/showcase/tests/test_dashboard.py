from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from showcase.models import Product
from showcase.views import MAX_SHOWCASE_OFFERS


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

    def test_dashboard_always_contains_all_products(self):
        hidden = Product.objects.create(
            provider_name="Hidden MFO",
            title="Hidden Product",
            category=Product.Category.SHORT_TERM,
            amount_text="до 20 000 ₽",
            term_text="до 20 дней",
            rate_text="0,8%",
            product_url="https://example.com/hidden",
            is_active=False,
        )

        priority = Product.objects.create(
            provider_name="Priority MFO",
            title="Priority Product",
            category=Product.Category.SHORT_TERM,
            amount_text="до 40 000 ₽",
            term_text="до 30 дней",
            rate_text="0,8%",
            product_url="https://example.com/priority",
            is_active=True,
            is_priority_offer=True,
        )

        response = self.client.get(
            reverse("showcase:dashboard"),
        )

        self.assertEqual(response.status_code, 200)

        products = list(response.context["products"])

        self.assertIn(self.product, products)
        self.assertIn(hidden, products)
        self.assertIn(priority, products)

    def test_dashboard_renders_filter_state_as_data_attributes(self):
        self.product.is_priority_offer = True
        self.product.save(
            update_fields=["is_priority_offer"],
        )

        response = self.client.get(
            reverse("showcase:dashboard"),
        )

        self.assertContains(
            response,
            'data-active="true"',
            html=False,
        )
        self.assertContains(
            response,
            'data-priority="true"',
            html=False,
        )
        self.assertContains(
            response,
            'data-showcase="true"',
            html=False,
        )

    def test_hidden_product_is_available_for_client_filter(self):
        hidden = Product.objects.create(
            provider_name="Hidden MFO",
            title="Hidden Product",
            category=Product.Category.SHORT_TERM,
            amount_text="до 20 000 ₽",
            term_text="до 20 дней",
            rate_text="0,8%",
            product_url="https://example.com/hidden",
            is_active=False,
        )

        response = self.client.get(
            reverse("showcase:dashboard"),
        )

        self.assertContains(
            response,
            hidden.provider_name,
        )

        self.assertContains(
            response,
            'data-active="false"',
            html=False,
        )

    def test_showcase_ids_respect_showcase_limit(self):
        for index in range(20):
            Product.objects.create(
                provider_name=f"MFO {index}",
                title=f"Product {index}",
                category=Product.Category.SHORT_TERM,
                amount_text="до 30 000 ₽",
                term_text="до 30 дней",
                rate_text="0,8%",
                product_url=(
                    f"https://example.com/product/{index}"
                ),
                is_active=True,
                other_epc=index,
            )

        response = self.client.get(
            reverse("showcase:dashboard"),
        )

        showcase_product_ids = response.context[
            "showcase_product_ids"
        ]

        self.assertEqual(
            len(showcase_product_ids),
            MAX_SHOWCASE_OFFERS,
        )

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

    def test_bulk_toggle_visible_turns_active_off(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "toggle_visible",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_bulk_toggle_visible_turns_inactive_on(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "toggle_visible",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_bulk_toggle_visible_ignores_invalid_primary_keys(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "toggle_visible",
                "pks": ["not-an-integer"],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_bulk_toggle_priority_turns_on(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "toggle_priority",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_priority_offer)

    def test_bulk_toggle_priority_turns_off(self):
        self.product.is_priority_offer = True
        self.product.save(update_fields=["is_priority_offer"])

        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "toggle_priority",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertFalse(self.product.is_priority_offer)

    def test_bulk_unknown_action_does_not_change_product(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {
                "action": "nonsense",
                "pks": [str(self.product.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)

        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)
        self.assertFalse(self.product.is_priority_offer)

    def test_bulk_without_pks_shows_warning(self):
        response = self.client.post(
            reverse("showcase:dashboard_bulk"),
            {"action": "toggle_visible"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Product.objects.filter(is_active=False).exists()
        )

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
