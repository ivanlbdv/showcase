from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'provider_name',
        'title',
        'source',
        'external_id',
        'category',
        'is_for_new_clients',
        'amount_text',
        'term_text',
        'is_active',
        'sort_order',
        'created_at',
    )

    list_filter = (
        'source',
        'is_active',
        'is_for_new_clients',
        'category',
    )

    search_fields = (
        'provider_name',
        'title',
        'description',
        'external_id',
    )

    list_editable = (
        'is_active',
        'sort_order',
    )

    readonly_fields = (
        'source',
        'external_id',
        'external_modified_at',
        'logo_url',
        'created_at',
        'updated_at',
    )

    ordering = (
        'sort_order',
        '-created_at',
        'id',
    )

    fieldsets = (
        (
            'Источник данных',
            {
                'fields': (
                    'source',
                    'external_id',
                    'external_modified_at',
                    'logo_url',
                ),
            },
        ),
        (
            'Основная информация',
            {
                'fields': (
                    'provider_name',
                    'title',
                    'category',
                    'is_for_new_clients',
                ),
            },
        ),
        (
            'Условия продукта',
            {
                'fields': (
                    'amount_text',
                    'term_text',
                    'rate_text',
                    'feature_label',
                    'feature_value',
                    'description',
                    'product_url',
                ),
            },
        ),
        (
            'Публикация на витрине',
            {
                'fields': (
                    'is_active',
                    'sort_order',
                ),
            },
        ),
        (
            'Служебная информация',
            {
                'fields': (
                    'created_at',
                    'updated_at',
                ),
            },
        ),
    )
