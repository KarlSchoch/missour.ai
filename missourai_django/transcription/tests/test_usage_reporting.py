from datetime import timedelta
from decimal import Decimal

from transcription.models import TaskPricing, UsageEvent
from transcription.services import usage_reporting as reporting
from .usage_fixtures import UsageTestCase


class UsageReportingTests(UsageTestCase):
    def details(self, **filters):
        return reporting.get_event_details(start=self.start, end=self.end, **filters)

    def test_details_include_all_statuses_unless_explicitly_filtered(self):
        succeeded = self.event()
        pending = self.event(status=UsageEvent.Status.PENDING)
        failed = self.event(status=UsageEvent.Status.FAILED)

        self.assertEqual(list(self.details()), [failed, pending, succeeded])
        for status, expected in (
            (UsageEvent.Status.SUCCEEDED, succeeded),
            (UsageEvent.Status.PENDING, pending),
            (UsageEvent.Status.FAILED, failed),
        ):
            with self.subTest(status=status):
                self.assertEqual(list(self.details(status=status)), [expected])

    def test_details_filter_user_and_half_open_time_window(self):
        at_start = self.event()
        before_end = self.event(occurred_at=self.end - timedelta(microseconds=1))
        self.event(user=self.other)
        self.event(occurred_at=self.start - timedelta(microseconds=1))
        self.event(occurred_at=self.end)

        self.assertEqual(list(self.details(user_id=self.user.pk)), [before_end, at_start])

    def test_details_filter_task_and_model(self):
        summary = self.event()
        tagging = self.event(task_type=TaskPricing.TaskType.TAGGING)
        self.assertEqual(list(self.details(task_type=TaskPricing.TaskType.SUMMARY)), [summary])
        self.assertEqual(list(self.details(model_name=self.price.model_name)), [tagging, summary])
        self.assertEqual(list(self.details(model_name="another-model")), [])

    def test_totals_sum_stored_amounts_and_exclude_unsuccessful_events(self):
        self.event()
        self.event(base_cost=Decimal("3.75"), billed_cost=Decimal("7.50"))
        self.event(user=self.other, task_type=TaskPricing.TaskType.TAGGING)
        # Nonzero costs ensure exclusion is by status, not by null/zero amounts.
        for status in (UsageEvent.Status.FAILED, UsageEvent.Status.PENDING):
            self.event(status=status, base_cost=Decimal("100"), billed_cost=Decimal("200"))

        self.assertEqual(list(reporting._totals(self.details())), [dict(
            currency="USD", event_count=3,
            base_cost=Decimal("6.25"), billed_cost=Decimal("12.50"),
        )])
        self.assertEqual(list(reporting._totals(self.details(), "task_type")), [
            dict(task_type=TaskPricing.TaskType.SUMMARY, currency="USD", event_count=2,
                 base_cost=Decimal("5"), billed_cost=Decimal("10")),
            dict(task_type=TaskPricing.TaskType.TAGGING, currency="USD", event_count=1,
                 base_cost=Decimal("1.25"), billed_cost=Decimal("2.50")),
        ])
        self.assertEqual(list(reporting._totals(self.details(status=UsageEvent.Status.FAILED))), [])
