import logging
import time

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Периодически синхронизирует витрину с Leads.su."

    def handle(self, *args, **options):
        interval = settings.SHOWCASE_SYNC_INTERVAL_SECONDS

        if interval <= 0:
            raise CommandError(
                "SHOWCASE_SYNC_INTERVAL_SECONDS должен быть больше 0."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Автоматическая синхронизация запущена. "
                f"Интервал: {interval} сек."
            )
        )

        while True:
            self._sync()

            self.stdout.write(
                f"Следующая синхронизация через {interval} сек."
            )

            time.sleep(interval)

    def _sync(self):
        try:
            call_command(
                "sync_leads_offers",
                stdout=self.stdout,
                stderr=self.stderr,
            )
        except CommandError:
            logger.exception(
                "Ошибка автоматической синхронизации Leads.su."
            )
