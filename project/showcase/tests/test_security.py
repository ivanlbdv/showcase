from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from showcase.models import Product


class TemplateSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.staff_user = User.objects.create_user(
            username="admin",
            password="test-password-123",
            is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.staff_user)

    def test_provider_name_is_html_escaped_in_dashboard(self):
        product = Product.objects.create(
            provider_name='<script>alert("xss")</script>',
            title="Test Product",
            category=Product.Category.SHORT_TERM,
            amount_text="до 30 000 ₽",
            term_text="до 30 дней",
            rate_text="0,8%",
            product_url="https://example.com/product",
        )

        response = self.client.get(
            reverse("showcase:dashboard"),
        )

        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        self.assertNotIn(
            '<script>alert("xss")</script>',
            content,
        )
        self.assertIn(
            '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;',
            content,
        )

    def test_provider_name_is_not_inserted_into_delete_javascript(self):
        malicious_name = "');alert(document.domain);//"

        Product.objects.create(
            provider_name=malicious_name,
            title="Test Product",
            category=Product.Category.SHORT_TERM,
            amount_text="до 30 000 ₽",
            term_text="до 30 дней",
            rate_text="0,8%",
            product_url="https://example.com/product",
        )

        response = self.client.get(
            reverse("showcase:dashboard"),
        )

        content = response.content.decode()

        self.assertNotIn(
            f"Удалить оффер «{malicious_name}»",
            content,
        )
        self.assertContains(
            response,
            "Удалить этот оффер без возможности восстановления?",
        )
