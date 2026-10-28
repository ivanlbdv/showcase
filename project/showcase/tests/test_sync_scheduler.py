from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class SyncSchedulerTests(SimpleTestCase):
    @override_settings(
        SHOWCASE_SYNC_INTERVAL_SECONDS=60,
    )
    @patch(
        "showcase.management.commands."
        "run_offer_sync_scheduler.time.sleep"
    )
    @patch(
        "showcase.management.commands."
        "run_offer_sync_scheduler.call_command"
    )
    def test_runs_sync_with_configured_interval(
        self,
        call_command_mock,
        sleep_mock,
    ):
        sleep_mock.side_effect = KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            call_command(
                "run_offer_sync_scheduler",
                stdout=StringIO(),
            )

        self.assertEqual(
            call_command_mock.call_args.args,
            ("sync_leads_offers",),
        )

        sleep_mock.assert_called_once_with(60)

    @override_settings(
        SHOWCASE_SYNC_INTERVAL_SECONDS=0,
    )
    def test_rejects_zero_interval(self):
        with self.assertRaises(CommandError):
            call_command(
                "run_offer_sync_scheduler",
                stdout=StringIO(),
            )

    @override_settings(
        SHOWCASE_SYNC_INTERVAL_SECONDS=-1,
    )
    def test_rejects_negative_interval(self):
        with self.assertRaises(CommandError):
            call_command(
                "run_offer_sync_scheduler",
                stdout=StringIO(),
            )

    @override_settings(
        SHOWCASE_SYNC_INTERVAL_SECONDS=60,
    )
    @patch(
        "showcase.management.commands."
        "run_offer_sync_scheduler.time.sleep"
    )
    @patch(
        "showcase.management.commands."
        "run_offer_sync_scheduler.call_command"
    )
    def test_scheduler_survives_sync_error(
        self,
        call_command_mock,
        sleep_mock,
    ):
        call_command_mock.side_effect = CommandError(
            "API unavailable"
        )

        sleep_mock.side_effect = KeyboardInterrupt

        with (
            self.assertLogs(
                "showcase.management.commands."
                "run_offer_sync_scheduler",
                level="ERROR",
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            call_command(
                "run_offer_sync_scheduler",
                stdout=StringIO(),
            )

        sleep_mock.assert_called_once_with(60)
