from decimal import Decimal

from django.urls import reverse
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from transcription.models import TaskPricing, UsageEvent
from transcription.usage_api_views import UsageAPIView
from .usage_fixtures import UsageTestCase


class UsageAPIViewTests(UsageTestCase):
    def setUp(self):
        self.client = APIClient()
        self.own = self.event()
        self.others = self.event(
            user=self.other, task_type=TaskPricing.TaskType.TAGGING,
            base_cost=Decimal("5"), billed_cost=Decimal("10"),
        )

    def view(self, user, **params):
        request = APIRequestFactory().get("/", {"month": "2026-01", **params})
        force_authenticate(request, user=user)
        view = UsageAPIView()
        view.request = view.initialize_request(request)
        return view

    def get(self, endpoint, **params):
        return self.client.get(reverse("api:" + endpoint), {"month": "2026-01", **params})

    def test_all_usage_endpoints_require_authentication(self):
        for endpoint in ("usage-summary", "usage-events", "usage-users",
                         "usage-model-prices", "usage-task-pricing"):
            with self.subTest(endpoint=endpoint):
                response = self.get(endpoint)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(set(response.data), {"detail"})

    def test_can_view_all_uses_reporting_permission(self):
        self.assertFalse(self.view(self.user).can_view_all())
        self.assertTrue(self.view(self.viewer).can_view_all())

    def test_report_context_scopes_rows_by_permission(self):
        for user, params, expected_id, expected_events in (
            (self.viewer, {}, None, [self.others, self.own]),
            (self.viewer, {"user_id": self.other.pk}, self.other.pk, [self.others]),
            (self.user, {}, self.user.pk, [self.own]),
            (self.user, {"user_id": self.user.pk}, self.user.pk, [self.own]),
        ):
            with self.subTest(user=user.username, params=params):
                start, end, user_id, events = self.view(user, **params).report_context()
                self.assertEqual((start, end, user_id), (self.start, self.end, expected_id))
                self.assertEqual(list(events), expected_events)
        with self.assertRaises(PermissionDenied):
            self.view(self.user, user_id=self.other.pk).report_context()

    def test_invalid_filter_values_raise_validation_error(self):
        for field, value in (
            ("month", "January"), ("month", "2026-13"),
            ("user_id", "abc"), ("user_id", 0),
            ("task_type", "invalid"), ("status", "invalid"),
            ("model_name", "x" * 101),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError) as raised:
                    self.view(self.user, **{field: value}).report_context()
                self.assertIn(field, raised.exception.detail)

    def test_ordinary_user_cannot_request_other_users_or_privileged_reports(self):
        self.client.force_authenticate(self.user)
        for endpoint in ("usage-summary", "usage-events"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.get(endpoint, user_id=self.other.pk).status_code, 403)
        for endpoint in ("usage-users", "usage-model-prices", "usage-task-pricing"):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.get(endpoint).status_code, 403)

    def test_event_endpoint_only_returns_own_rows_and_public_fields(self):
        self.client.force_authenticate(self.user)
        response = self.get("usage-events")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        row, = response.data["results"]
        self.assertEqual(row["id"], self.own.pk)
        self.assertEqual(row["user_id"], self.user.pk)
        for field in ("base_cost", "multiplier", "model_price_id", "task_pricing_id", "provider_request_id"):
            self.assertNotIn(field, row)

    def test_summary_only_contains_own_totals_tasks_and_status_counts(self):
        self.event(user=self.other, status=UsageEvent.Status.FAILED)
        self.client.force_authenticate(self.user)
        response = self.get("usage-summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scope"], {"kind": "user", "user_id": self.user.pk})
        total = dict(currency="USD", event_count=1, billed_cost="2.5000000000")
        self.assertEqual(response.data["totals"], [total])
        self.assertEqual(response.data["tasks"], [dict(total, task_type=TaskPricing.TaskType.SUMMARY)])
        self.assertEqual(response.data["status_counts"], [{"status": "succeeded", "event_count": 1}])
        self.assertNotIn("users", response.data)
        self.assertNotIn("pricing_periods", response.data)

    def test_privileged_summary_includes_organization_and_user_totals(self):
        self.client.force_authenticate(self.viewer)
        response = self.get("usage-summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scope"], {"kind": "organization", "user_id": None})
        self.assertEqual(response.data["totals"], [dict(
            currency="USD", event_count=2, base_cost="6.2500000000", billed_cost="12.5000000000",
        )])
        self.assertEqual(response.data["users"], [
            dict(user_id=self.user.pk, currency="USD", event_count=1,
                 base_cost="1.2500000000", billed_cost="2.5000000000"),
            dict(user_id=self.other.pk, currency="USD", event_count=1,
                 base_cost="5.0000000000", billed_cost="10.0000000000"),
        ])
