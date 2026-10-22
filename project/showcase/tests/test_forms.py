from django.test import TestCase
from showcase.forms import DashboardProductForm
from showcase.models import Product


def valid_form_data(**overrides):
    data = {
        "provider_name": "Тест МФО",
        "title": "Тестовый продукт",
        "category": Product.Category.SHORT_TERM,
        "is_for_new_clients": True,
        "amount_text": "от 1 000 до 30 000 ₽",
        "term_text": "от 5 до 30 дней",
        "rate_text": "0,8%",
        "psk_text": "0,00 – 292,00%",
        "logo_url": "https://example.com/logo.png",
        "product_url": "https://example.com/product",
        "description": "Описание продукта",
        "is_active": True,
        "is_priority_offer": False,
        "sort_order": 5,
    }

    data.update(overrides)

    return data


class DashboardProductFormTests(TestCase):
    def test_valid_form(self):
        form = DashboardProductForm(
            data=valid_form_data(),
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

    def test_expected_fields_are_present(self):
        form = DashboardProductForm()

        self.assertEqual(
            list(form.fields),
            [
                "provider_name",
                "title",
                "category",
                "is_for_new_clients",
                "amount_text",
                "term_text",
                "rate_text",
                "psk_text",
                "logo_url",
                "product_url",
                "description",
                "is_active",
                "is_priority_offer",
                "sort_order",
            ],
        )

    def test_technical_fields_are_not_editable(self):
        form = DashboardProductForm()

        forbidden_fields = {
            "source",
            "external_id",
            "external_modified_at",
            "other_epc",
            "created_at",
            "updated_at",
        }

        self.assertTrue(
            forbidden_fields.isdisjoint(
                form.fields.keys()
            )
        )

    def test_description_has_four_rows(self):
        form = DashboardProductForm()

        self.assertEqual(
            form.fields["description"]
            .widget.attrs["rows"],
            4,
        )

    def test_sort_order_widget_has_min_zero(self):
        form = DashboardProductForm()

        self.assertEqual(
            form.fields["sort_order"]
            .widget.attrs["min"],
            0,
        )

    def test_negative_sort_order_is_rejected(self):
        form = DashboardProductForm(
            data=valid_form_data(
                sort_order=-1,
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "sort_order",
            form.errors,
        )

    def test_invalid_product_url_is_rejected(self):
        form = DashboardProductForm(
            data=valid_form_data(
                product_url="javascript:alert(1)",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "product_url",
            form.errors,
        )

    def test_invalid_logo_url_is_rejected(self):
        form = DashboardProductForm(
            data=valid_form_data(
                logo_url="not-a-url",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "logo_url",
            form.errors,
        )

    def test_blank_logo_url_is_allowed(self):
        form = DashboardProductForm(
            data=valid_form_data(
                logo_url="",
            )
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

    def test_blank_psk_is_allowed(self):
        form = DashboardProductForm(
            data=valid_form_data(
                psk_text="",
            )
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

    def test_provider_name_is_required(self):
        form = DashboardProductForm(
            data=valid_form_data(
                provider_name="",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "provider_name",
            form.errors,
        )

    def test_title_is_required(self):
        form = DashboardProductForm(
            data=valid_form_data(
                title="",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "title",
            form.errors,
        )

    def test_category_must_be_valid_choice(self):
        form = DashboardProductForm(
            data=valid_form_data(
                category="something-else",
            )
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "category",
            form.errors,
        )

    def test_form_creates_product(self):
        form = DashboardProductForm(
            data=valid_form_data(),
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        product = form.save()

        self.assertIsNotNone(product.pk)
        self.assertEqual(
            product.provider_name,
            "Тест МФО",
        )
        self.assertEqual(
            product.sort_order,
            5,
        )
        self.assertTrue(
            product.is_for_new_clients,
        )

    def test_form_updates_existing_product(self):
        product = Product.objects.create(
            provider_name="Старое МФО",
            title="Старый продукт",
            category=Product.Category.SHORT_TERM,
            amount_text="до 10 000 ₽",
            term_text="до 10 дней",
            rate_text="0,8%",
            product_url="https://example.com/old",
        )

        form = DashboardProductForm(
            data=valid_form_data(
                provider_name="Новое МФО",
                title="Новый продукт",
            ),
            instance=product,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        updated = form.save()

        self.assertEqual(
            updated.pk,
            product.pk,
        )
        self.assertEqual(
            updated.provider_name,
            "Новое МФО",
        )
        self.assertEqual(
            updated.title,
            "Новый продукт",
        )

    def test_form_cannot_change_import_metadata(self):
        product = Product.objects.create(
            source="leads_su",
            external_id="1001",
            provider_name="Старое МФО",
            title="Старый продукт",
            category=Product.Category.SHORT_TERM,
            amount_text="до 10 000 ₽",
            term_text="до 10 дней",
            rate_text="0,8%",
            product_url="https://example.com/old",
        )

        data = valid_form_data()

        # Даже если клиент вручную подставит эти POST-поля,
        # ModelForm не должен их использовать.
        data["source"] = "attacker"
        data["external_id"] = "hacked"
        data["other_epc"] = "999999"

        form = DashboardProductForm(
            data=data,
            instance=product,
        )

        self.assertTrue(
            form.is_valid(),
            form.errors.as_json(),
        )

        updated = form.save()

        self.assertEqual(
            updated.source,
            "leads_su",
        )
        self.assertEqual(
            updated.external_id,
            "1001",
        )
