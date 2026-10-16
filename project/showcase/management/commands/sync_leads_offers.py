import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from showcase.integrations.leads_su import (LeadsSuAPIError, LeadsSuClient,
                                            OfferValidationError,
                                            normalize_offer)
from showcase.models import Product

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Синхронизирует активные офферы Leads.su "
        "с карточками витрины."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Получить и проверить данные API, "
                "но не менять базу данных."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        client = LeadsSuClient(
            api_token=settings.LEADS_API_TOKEN,
            platform_id=settings.LEADS_PLATFORM_ID,
        )

        try:
            raw_offers = client.fetch_all_active_offers()
        except LeadsSuAPIError as exc:
            raise CommandError(
                f"Синхронизация Leads.su не выполнена: {exc}"
            ) from exc

        received_external_ids: set[str] = set()
        normalized_offers = []

        skipped_count = 0

        for raw_offer in raw_offers:
            raw_external_id = str(raw_offer.get("id", "")).strip()

            # Добавляем ID до нормализации. Если конкретный оффер
            # имеет неполные данные, существующая карточка не будет
            # автоматически выключена только из-за этой ошибки.
            if raw_external_id:
                received_external_ids.add(raw_external_id)

            try:
                normalized_offer = normalize_offer(
                    raw_offer,
                    platform_id=settings.LEADS_PLATFORM_ID,
                )
            except OfferValidationError as exc:
                skipped_count += 1

                logger.warning(
                    "Оффер Leads.su %s пропущен: %s",
                    raw_external_id or "<unknown>",
                    exc,
                )
                continue

            normalized_offers.append(normalized_offer)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Тестовый запуск завершён: "
                    f"получено={len(raw_offers)}, "
                    f"готово к сохранению={len(normalized_offers)}, "
                    f"пропущено={skipped_count}. "
                    "Изменения в БД не вносились."
                )
            )
            return

        created_count = 0
        updated_count = 0
        deactivated_count = 0

        # Все операции с БД выполняются только после того,
        # как API успешно вернуло полный набор страниц.
        with transaction.atomic():
            for offer in normalized_offers:
                _, created = Product.objects.update_or_create(
                    source="leads_su",
                    external_id=offer.external_id,
                    defaults={
                        "provider_name": offer.provider_name,
                        "title": offer.title,
                        "category": offer.category,
                        "is_for_new_clients": (
                            offer.is_for_new_clients
                        ),
                        "amount_text": offer.amount_text,
                        "term_text": offer.term_text,
                        "rate_text": offer.rate_text,
                        "feature_label": offer.feature_label,
                        "feature_value": offer.feature_value,
                        "description": offer.description,
                        "product_url": offer.product_url,
                        "logo_url": offer.logo_url,
                        "external_modified_at": (
                            offer.external_modified_at
                        ),
                        "is_active": offer.is_active,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            # Отключаем только импортированные карточки Leads.su,
            # которые отсутствуют в полностью успешном ответе API.
            #
            # Ручные карточки source="manual" не затрагиваются.
            #
            # Офферы с некорректными данными не деактивируются:
            # их ID уже есть в received_external_ids.
            deactivated_count = Product.objects.filter(
                source="leads_su",
                is_active=True,
            ).exclude(
                external_id__in=received_external_ids,
            ).update(
                is_active=False,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Синхронизация Leads.su завершена: "
                f"получено={len(raw_offers)}, "
                f"создано={created_count}, "
                f"обновлено={updated_count}, "
                f"деактивировано={deactivated_count}, "
                f"пропущено={skipped_count}."
            )
        )
