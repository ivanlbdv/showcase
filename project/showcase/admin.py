import io

from django.contrib import admin, messages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import path
from django.utils.html import format_html

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    empty_value_display = "—"

    list_display = (
        "active_badge",
        "is_priority_offer",
        "logo_preview",
        "provider_name",
        "category_badge",
        "new_clients_badge",
        "conditions",
        "epc_preview",
        "source_badge",
        "sort_order",
        "product_link",
        "updated_preview",
    )

    list_display_links = (
        "provider_name",
    )

    list_editable = (
        "is_priority_offer",
        "sort_order",
    )

    list_filter = (
        "is_active",
        "is_priority_offer",
        "category",
        "is_for_new_clients",
        "source",
    )

    search_fields = (
        "provider_name",
        "title",
        "external_id",
        "product_url",
    )

    # Список по умолчанию в витринном порядке: приоритетные
    # наверху, активные выше неактивных, дальше sort_order.
    ordering = (
        "-is_priority_offer",
        "is_active",
        "sort_order",
        "-created_at",
        "id",
    )

    actions_on_top = True
    actions_on_bottom = False

    date_hierarchy = "created_at"
    list_per_page = 25
    save_on_top = True

    actions = (
        "activate_products",
        "deactivate_products",
        "toggle_priority",
    )

    fieldsets = (
        (
            "Публикация",
            {
                "fields": (
                    "is_active",
                    "is_priority_offer",
                    "sort_order",
                ),
                "description": (
                    "Активные карточки участвуют в показе на витрине. "
                    "Приоритетные поднимаются наверх и выделяются визуально. "
                    "Порядок показа: чем меньше sort_order, тем выше карточка "
                    "внутри своей группы EPC."
                ),
            },
        ),
        (
            "Что видит пользователь",
            {
                "fields": (
                    "provider_name",
                    "title",
                    "logo_url",
                    "category",
                    "is_for_new_clients",
                    "amount_text",
                    "term_text",
                    "psk_text",
                    "rate_text",
                    "product_url",
                ),
            },
        ),
        (
            "Описание (только админка)",
            {
                "classes": ("collapse",),
                "fields": ("description",),
            },
        ),
        (
            "Служебные данные",
            {
                "classes": ("collapse",),
                "fields": (
                    "source",
                    "external_id",
                    "external_modified_at",
                    "other_epc",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    readonly_fields = (
        "source",
        "external_id",
        "external_modified_at",
        "other_epc",
        "created_at",
        "updated_at",
    )

    class Media:
        css = {
            "all": ("showcase/css/admin.css",),
        }

    # ---------- URL синхронизации ----------

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "sync/",
                self.admin_site.admin_view(self.sync_offers_view),
                name="showcase_product_sync",
            ),
        ]

        return custom_urls + urls

    def sync_offers_view(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        """
        Запускает management command sync_leads_offers
        и возвращает пользователя на список офферов
        с отчётом в уведомлении админки.
        """
        if not request.user.has_perm("showcase.change_product"):
            raise PermissionDenied

        output = io.StringIO()

        try:
            call_command(
                "sync_leads_offers",
                stdout=output,
                no_color=True,
            )
        except CommandError as exc:
            self.message_user(
                request,
                f"Синхронизация не выполнена: {exc}",
                level=messages.ERROR,
            )
        else:
            report = output.getvalue().strip()

            self.message_user(
                request,
                report or "Синхронизация завершена.",
                level=messages.SUCCESS,
            )

        return redirect("admin:showcase_product_changelist")

    # ---------- Компактные столбцы списка ----------

    @admin.display(
        boolean=True,
        description="Актив.",
        ordering="is_active",
    )
    def active_badge(self, obj):
        return obj.is_active

    @admin.display(description="Логотип")
    def logo_preview(self, obj):
        if not obj.logo_url:
            return self.empty_value_display

        return format_html(
            '<img src="{}" width="48" height="20" class="logo-thumb" />',
            obj.logo_url,
        )

    @admin.display(
        description="Срок",
        ordering="category",
    )
    def category_badge(self, obj):
        return (
            "30+ дн"
            if obj.category == Product.Category.LONG_TERM
            else "до 30 дн"
        )

    @admin.display(
        boolean=True,
        description="Новым",
        ordering="is_for_new_clients",
    )
    def new_clients_badge(self, obj):
        return obj.is_for_new_clients

    @admin.display(description="Условия")
    def conditions(self, obj):
        psk = obj.psk_text or self.empty_value_display

        return format_html(
            '<span class="cond-line cond-line--main">{}</span>'
            '<span class="cond-line">{}</span>'
            '<span class="cond-line cond-line--muted">{} · ПСК {}</span>',
            obj.amount_text,
            obj.term_text,
            obj.rate_text,
            psk,
        )

    @admin.display(
        description="EPC",
        ordering="other_epc",
    )
    def epc_preview(self, obj):
        return format_html(
            '<span class="epc{}">{}</span>',
            " epc--zero" if obj.other_epc == 0 else "",
            f"{obj.other_epc:.2f}".replace(".", ","),
        )

    @admin.display(description="Источник", ordering="source")
    def source_badge(self, obj):
        label = "Leads.su" if obj.source == "leads_su" else "Ручная"

        return format_html(
            '<span class="source-chip source-chip--{}">{}</span>',
            obj.source,
            label,
        )

    @admin.display(description="↗", ordering="product_url")
    def product_link(self, obj):
        if not obj.product_url:
            return self.empty_value_display

        return format_html(
            '<a href="{}" target="_blank" rel="noopener" '
            'class="ext-link" title="{}">↗</a>',
            obj.product_url,
            obj.product_url,
        )

    @admin.display(description="Обновлено", ordering="updated_at")
    def updated_preview(self, obj):
        return obj.updated_at.strftime("%d.%m.%y %H:%M")

    # ---------- Массовые действия ----------

    @admin.action(description="Включить на витрине")
    def activate_products(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Включено предложений: {updated}.",
        )

    @admin.action(description="Выключить с витрины")
    def deactivate_products(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Выключено предложений: {updated}.",
        )

    @admin.action(description="Переключить приоритет")
    def toggle_priority(self, request, queryset):
        for product in queryset:
            product.is_priority_offer = not product.is_priority_offer
            product.save(update_fields=["is_priority_offer", "updated_at"])

        self.message_user(
            request,
            f"Приоритет переключён у предложений: {queryset.count()}.",
        )
