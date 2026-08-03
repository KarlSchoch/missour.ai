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
)


@admin.register(ModelPrice)
class ModelPriceAdmin(admin.ModelAdmin):
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
    readonly_fields = ("created_at",)

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(TaskPricing)
class TaskPricingAdmin(admin.ModelAdmin):
    list_display = (
        "task_type",
        "model_price",
        "multiplier",
        "effective_from",
        "effective_to",
    )
    list_filter = ("task_type",)
    readonly_fields = ("created_at",)

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

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
