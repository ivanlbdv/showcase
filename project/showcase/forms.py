from django import forms

from .models import Product


class DashboardProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
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
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["description"].widget.attrs["rows"] = 4
        self.fields["sort_order"].widget.attrs["min"] = 0
