from django.contrib import admin

# Register your models here.
from .models import (
    BackgroundJob,
    Chunk,
    ModelPrice,
    Summary,
    Tag,
    TaskPricing,
    Topic,
    Transcript,
    TranscriptionChunkMetric,
    TranscriptionJobMetric,
    UsageEvent,
)


VIEW_ALL_USAGE_PERMISSION = "transcription.view_all_usage"
MANAGE_USAGE_PRICING_PERMISSION = "transcription.manage_usage_pricing"


class PricingPermissionAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.has_perm(
            VIEW_ALL_USAGE_PERMISSION
        ) or request.user.has_perm(MANAGE_USAGE_PRICING_PERMISSION)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return request.user.has_perm(MANAGE_USAGE_PRICING_PERMISSION)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ModelPrice)
class ModelPriceAdmin(PricingPermissionAdmin):
    list_display = (
        "model_name",
        "provider",
        "billing_unit",
        "currency",
        "effective_from",
        "effective_to",
    )
    list_filter = ("provider", "billing_unit", "currency")
    search_fields = ("model_name",)
    readonly_fields = ("created_by", "created_at")

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(TaskPricing)
class TaskPricingAdmin(PricingPermissionAdmin):
    list_display = (
        "task_type",
        "model_price",
        "multiplier",
        "effective_from",
        "effective_to",
    )
    list_filter = ("task_type",)
    readonly_fields = ("created_by", "created_at")

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(UsageEvent)
class UsageEventAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at",
        "user",
        "task_type",
        "model_name",
        "status",
        "base_cost",
        "billed_cost",
        "currency",
    )
    list_filter = ("status", "task_type", "billing_unit", "usage_source")
    search_fields = ("idempotency_key", "provider_request_id", "model_name")
    readonly_fields = tuple(field.name for field in UsageEvent._meta.fields)

    def has_module_permission(self, request):
        return request.user.has_perm(VIEW_ALL_USAGE_PERMISSION)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(VIEW_ALL_USAGE_PERMISSION)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register([
    BackgroundJob,
    Transcript,
    Topic,
    Chunk,
    Tag,
    Summary,
    TranscriptionJobMetric,
    TranscriptionChunkMetric,
])
