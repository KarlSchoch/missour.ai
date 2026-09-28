"""Pricing writes require an explicit, signed preview confirmation."""
import json

from django.core import signing
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ModelPrice, TaskPricing
from .usage_serializers import ModelPriceSerializer, TaskPricingSerializer
from .services.pricing_administration import (
    PricingSelectionRequired,
    change_pricing,
    readiness,
)


class ChangeFields(serializers.Serializer):
    selected_supersedes = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    activate_now = serializers.BooleanField(default=False)
    effective_from = serializers.DateTimeField(required=False)
    effective_to = serializers.DateTimeField(required=False, allow_null=True, default=None)


class ModelChange(ChangeFields):
    provider = serializers.ChoiceField(choices=ModelPrice.Provider.choices, default="openai")
    model_name = serializers.CharField(max_length=100)
    currency = serializers.ChoiceField(choices=["USD"], default="USD")
    billing_unit = serializers.ChoiceField(choices=ModelPrice.BillingUnit.choices)
    input_rate_per_million = serializers.DecimalField(max_digits=20, decimal_places=10, min_value=0, required=False, allow_null=True, default=None)
    cached_input_rate_per_million = serializers.DecimalField(max_digits=20, decimal_places=10, min_value=0, required=False, allow_null=True, default=None)
    output_rate_per_million = serializers.DecimalField(max_digits=20, decimal_places=10, min_value=0, required=False, allow_null=True, default=None)
    rate_per_minute = serializers.DecimalField(max_digits=20, decimal_places=10, min_value=0, required=False, allow_null=True, default=None)


class TaskChange(ChangeFields):
    task_type = serializers.ChoiceField(choices=TaskPricing.TaskType.choices)
    model_price_id = serializers.IntegerField(min_value=1)
    multiplier = serializers.DecimalField(max_digits=12, decimal_places=6)


def pricing_post(request, kind):
    if not request.user.has_perm("transcription.manage_usage_pricing"):
        raise PermissionDenied("Pricing changes require manage_usage_pricing.")
    token = request.data.get("confirmation_token")
    expected = None
    if token:
        try:
            signed = signing.loads(token, salt="usage-pricing", max_age=900)
        except (signing.BadSignature, TypeError) as exc:
            raise ValidationError("Invalid or expired confirmation. Preview again.") from exc
        if signed["kind"] != kind or signed["user_id"] != request.user.pk:
            raise PermissionDenied("This confirmation belongs to another operation or user.")
        payload = signed["data"]
        expected = signed["fingerprint"]
    else:
        payload = request.data
    validator = (ModelChange if kind == "model" else TaskChange)(data=payload)
    validator.is_valid(raise_exception=True)
    data = dict(validator.validated_data)
    if not token and data.get("activate_now"):
        data["effective_from"] = timezone.now()
    if "effective_from" not in data:
        raise ValidationError({"effective_from": "Provide a future timestamp or select immediate activation."})
    # Confirming uses the exact timestamp shown in the preview, not a new one.
    if kind == "task" and not ModelPrice.objects.filter(pk=data["model_price_id"]).exists():
        raise ValidationError({"model_price_id": "Model price not found."})
    try:
        candidate, closed, created, impacts, version = change_pricing(
            kind, data, request.user, preview=not bool(token), expected_fingerprint=expected,
        )
    except PricingSelectionRequired as exc:
        serializer = ModelPriceSerializer if kind == "model" else TaskPricingSerializer
        return Response({
            "code": "configuration_conflict" if exc.conflict else "selection_required",
            "detail": (
                "Multiple pricing records apply at this activation time. "
                "The configuration must be corrected before pricing can be changed."
                if exc.conflict else
                "Multiple possible records were found. Select the record to supersede."
            ),
            "candidates": serializer(exc.candidates, many=True).data,
        }, status=409)
    except ModelValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc
    except IntegrityError as exc:
        raise ValidationError("Pricing changed concurrently. Preview again.") from exc
    serialized = (ModelPriceSerializer if kind == "model" else TaskPricingSerializer)(candidate).data
    created_records = []
    for record in created:
        record_data = TaskPricingSerializer(record).data
        if record.model_price_id is None:
            record_data["model_price_id"] = "proposed_model_price"
        created_records.append({"kind": "task", "record": record_data})
    result = {
        "record": serialized,
        "closes": closed,
        "creates": created_records,
        "task_pricing_impacts": impacts,
    }
    if not token:
        result["confirmation_token"] = signing.dumps({
            "kind": kind, "user_id": request.user.pk,
            "data": json.loads(json.dumps(data, default=str)), "fingerprint": version,
        }, salt="usage-pricing")
        result["warning"] = (
            "The applicable model price will be superseded. Linked task multipliers "
            "will be closed and carried forward to the replacement price."
            if kind == "model" and closed else
            "Review the proposed effective period before confirming."
        )
    return Response(result, status=201 if token else 200)


class PricingReadinessAPIView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        if not (request.user.has_perm("transcription.view_all_usage") or request.user.has_perm("transcription.manage_usage_pricing")):
            raise PermissionDenied("Pricing readiness requires usage-reporting or pricing-management permission.")
        return Response({"tasks": readiness()})
