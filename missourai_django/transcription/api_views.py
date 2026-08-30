from rest_framework import viewsets, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from celery.result import AsyncResult
from django.contrib.auth import get_user_model
from django.http import Http404
from django.shortcuts import get_object_or_404
from os import environ

from .serializers import (
    BackgroundJobSerializer,
    TopicSerializer,
    SummarySerializer,
    TagSerializer,
    AppliedPricingPeriodSerializer,
    ModelPriceSerializer,
    MonthlyTaskTotalSerializer,
    OverallMonthlyTotalSerializer,
    TaskPricingSerializer,
    UsageEventDetailSerializer,
    UsageStatusCountSerializer,
    UsageUserChoiceSerializer,
    UserMonthlyTotalSerializer,
)
from .models import (
    BackgroundJob,
    ModelPrice,
    Summary,
    Tag,
    TaskPricing,
    Topic,
    Transcript,
    UsageEvent,
)
from .services.usage_reporting import (
    DEFAULT_CURRENCY,
    UsageReportFilterError,
    apply_event_filters,
    get_applied_pricing_periods,
    get_event_details,
    get_month_bounds,
    get_organization_summary,
    get_report_month_label,
    get_status_counts,
    get_task_breakdown,
    get_usage_queryset,
    get_user_summary,
    get_user_totals,
)
from transcription.summary.summary_manager import SummaryManager
from transcription.tagging.tagging_manager import TaggingManager

summary_manager = SummaryManager(api_key=environ['OPENAI_API_KEY'])

VIEW_ALL_USAGE_PERMISSION = "transcription.view_all_usage"


class UsagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class UsageAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _can_view_all(self, request):
        return request.user.has_perm(VIEW_ALL_USAGE_PERMISSION)

    def _target_user(self, request):
        requested_id = request.query_params.get("user_id")
        can_view_all = self._can_view_all(request)
        if requested_id is None:
            return None if can_view_all else request.user

        try:
            requested_id = int(requested_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"user_id": "user_id must be an integer."}) from exc

        if requested_id != request.user.pk and not can_view_all:
            raise PermissionDenied("You cannot view another user's usage.")

        user = get_user_model().objects.filter(pk=requested_id).first()
        if user is None:
            raise NotFound("The requested user does not exist.")
        return user

    def _report_context(self, request):
        try:
            start, end = get_month_bounds(request.query_params.get("month"))
        except UsageReportFilterError as exc:
            raise ValidationError({"month": str(exc)}) from exc

        task_type = request.query_params.get("task_type")
        event_status = request.query_params.get("status")
        valid_task_types = {choice for choice, _ in TaskPricing.TaskType.choices}
        valid_statuses = {choice for choice, _ in UsageEvent.Status.choices}
        errors = {}
        if task_type and task_type not in valid_task_types:
            errors["task_type"] = "Unknown task_type."
        if event_status and event_status not in valid_statuses:
            errors["status"] = "Unknown status."
        if errors:
            raise ValidationError(errors)

        target_user = self._target_user(request)
        queryset = get_usage_queryset(start=start, end=end, user=target_user)
        queryset = apply_event_filters(
            queryset,
            task_type=task_type,
            model_name=request.query_params.get("model_name"),
            status=event_status,
        )
        return start, end, target_user, queryset


class UsageSummaryAPIView(UsageAPIView):
    def get(self, request):
        start, end, target_user, queryset = self._report_context(request)
        totals = (
            get_user_summary(queryset)
            if target_user is not None
            else get_organization_summary(queryset)
        )
        serializer_context = {
            "include_internal_costs": self._can_view_all(request),
        }
        payload = {
            "period": {
                "month": get_report_month_label(start),
                "start": start,
                "end": end,
                "currency": DEFAULT_CURRENCY,
            },
            "scope": {
                "kind": "user" if target_user is not None else "organization",
                "user_id": target_user.pk if target_user is not None else None,
                "username": (
                    target_user.get_username() if target_user is not None else None
                ),
            },
            "totals": OverallMonthlyTotalSerializer(
                totals, context=serializer_context
            ).data,
            "tasks": MonthlyTaskTotalSerializer(
                get_task_breakdown(queryset),
                many=True,
                context=serializer_context,
            ).data,
            "status_counts": UsageStatusCountSerializer(
                get_status_counts(queryset), many=True
            ).data,
        }
        if self._can_view_all(request):
            payload["pricing_periods"] = AppliedPricingPeriodSerializer(
                get_applied_pricing_periods(queryset),
                many=True,
                context=serializer_context,
            ).data
        if target_user is None:
            payload["users"] = UserMonthlyTotalSerializer(
                get_user_totals(queryset),
                many=True,
                context=serializer_context,
            ).data
        return Response(payload)


class UsageEventListAPIView(UsageAPIView):
    def get(self, request):
        _, _, _, queryset = self._report_context(request)
        paginator = UsagePagination()
        page = paginator.paginate_queryset(get_event_details(queryset), request)
        serializer = UsageEventDetailSerializer(
            page,
            many=True,
            context={"include_internal_costs": self._can_view_all(request)},
        )
        return paginator.get_paginated_response(serializer.data)


class UsageUserListAPIView(UsageAPIView):
    def get(self, request):
        if not self._can_view_all(request):
            raise PermissionDenied("Viewing the usage user list requires permission.")
        users = (
            get_user_model().objects.filter(usage_events__isnull=False)
            .distinct()
            .order_by("username", "pk")
            .values("id", "username")
        )
        return Response(UsageUserChoiceSerializer(users, many=True).data)


class UsagePricingAPIView(UsageAPIView):
    def _require_permission(self, request):
        if not self._can_view_all(request):
            raise PermissionDenied("Viewing usage pricing requires permission.")


class ModelPriceListAPIView(UsagePricingAPIView):
    def get(self, request):
        self._require_permission(request)
        queryset = ModelPrice.objects.select_related("created_by").all()
        return Response(ModelPriceSerializer(queryset, many=True).data)


class TaskPricingListAPIView(UsagePricingAPIView):
    def get(self, request):
        self._require_permission(request)
        queryset = TaskPricing.objects.select_related("model_price", "created_by").all()
        return Response(TaskPricingSerializer(queryset, many=True).data)


class BackgroundJobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BackgroundJobSerializer
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        queryset = BackgroundJob.objects.filter(
            created_by=self.request.user
        ).order_by("-created_at")

        kind = self.request.query_params.get("kind")
        if kind:
            queryset = queryset.filter(kind=kind)

        related_object_id = self.request.query_params.get("related_object_id")
        if related_object_id:
            queryset = queryset.filter(related_object_id=related_object_id)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = list(self.filter_queryset(self.get_queryset())[:25])

        active = request.query_params.get("active")
        if active is not None:
            wants_active = active.lower() in {"1", "true", "yes"}
            queryset = [
                job
                for job in queryset
                if AsyncResult(job.task_id).ready() is not wants_active
            ]

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class TopicViewSet(viewsets.ModelViewSet):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer

    def get_queryset(self):
        return Topic.objects.filter(created_by = self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(created_by = self.request.user)

class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.none()
    serializer_class = TagSerializer

    def get_queryset(self):
        return Tag.objects.filter(
            chunk__transcript__created_by=self.request.user,
            topic__created_by=self.request.user,
        )

class SummaryViewSet(viewsets.ModelViewSet):
    queryset = Summary.objects.all()
    serializer_class = SummarySerializer
    filterset_fields = ["transcript"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Summary.objects.filter(transcript__created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        # 1. Build serializer from request and validate
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 2. Custom Logic
        # Extract data from request for downstream processing
        data = request.data
        try: 
            summary_type = data['summary_type']
            transcript = data['transcript']
        except KeyError as e:
            return Response(
                f"Key used in backend ({e.args[0]}) not found in frontend request",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            return Response(
                str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            # Query the DB for the transcript
            tgt_transcript = get_object_or_404(
                Transcript,
                pk=int(transcript),
                created_by=request.user,
            )
            # Check whether this is a general or topic level summary
            ## General
            if summary_type == 'general':
                ### Extract the text that needs to be summarized
                tgt_text = tgt_transcript.transcript_text
                ### Call the OpenAI API through the summary manager
                summary_obj = summary_manager.summarize(
                    transcript_content=tgt_text,
                    tgt_transcript=tgt_transcript
                )
                ### Create a summary object: transcript, summary_type, topic, text
            ## Topic Level
            elif summary_type == 'topic':
                # 1. Through Chunk query the tags for a given transcript (transcript_tags)
                transcript_tags = Tag.objects.filter(
                    chunk__transcript=tgt_transcript,
                    topic__created_by=request.user,
                ).select_related('topic', 'chunk')
                # 2. Extract the set of topics tags have been generated for (generated_tag_topics)
                generated_tag_topics = set(
                    transcript_tags.values_list("topic_id", flat=True)
                )
                # 3. Compare generated_tags against the topic passed
                topic = data['topic']
                tgt_topic_obj = get_object_or_404(
                    Topic,
                    pk=int(topic),
                    created_by=request.user,
                )
                # 3.a. Topic passed back not in generated_tags
                if tgt_topic_obj.pk not in generated_tag_topics:
                    # 3.a.i.  Generate tags for that topic
                    ## Instantiate the tagging manager
                    tagging_manager = TaggingManager(
                        api_key=environ['OPENAI_API_KEY'],
                        transcript=tgt_transcript,
                        topics=[tgt_topic_obj]
                    )
                    new_transcript_tags = tagging_manager.tag_transcript()
                    # 3.a.ii. Requery transcript_tags
                    transcript_tags = Tag.objects.filter(chunk__transcript=tgt_transcript).select_related('topic', 'chunk')
                # 3.b. Topic passed back in generated_tags
                else:
                    # 3.b.i.  Pass
                    pass
                # 4. Filter tags to only where topic_present field == True that are for the tgt_topic
                transcript_tags = transcript_tags.filter(
                    topic=tgt_topic_obj,
                    topic_present = True
                )
                # Save summary and return if there are no relevant tags for the topic
                if len(transcript_tags) == 0:
                    summary_obj = Summary(
                        transcript=tgt_transcript,
                        summary_type='topic',
                        topic=tgt_topic_obj,
                        text='No content related to this topic in the transcript.'
                    )
                    summary_obj.save()
                    serializer = SummarySerializer(summary_obj)
                    headers = self.get_success_headers(serializer.data)
                    return Response(
                        serializer.data, status=status.HTTP_201_CREATED, headers=headers
                    )        
                # 5. Create prompt based on Chunk's chunk_text field
                transcript_content = transcript_tags.values_list(
                    "chunk__chunk_text",
                    flat=True
                )
                # 6. Pass prompt to the Summary Manager (saves summary in db)
                summary_obj = summary_manager.summarize(
                    transcript_content=transcript_content,
                    tgt_transcript=tgt_transcript,
                    tgt_topic=tgt_topic_obj,
                )

            # TO DO: Offload as job to celery
            # TO DO: Save all non API call dependent fields

            # 3. Save HANDLED IN summary_manager.py
            # Create a summary entry based on the summary_text
            # serializer.save()

            # 4 (???) Custom Logic Post Save

            # 5. Return
            serializer = SummarySerializer(summary_obj)
            headers = self.get_success_headers(serializer.data)
            return Response(
                serializer.data, status=status.HTTP_201_CREATED, headers=headers
            )
        except Http404:
            raise
        except Exception as e:
            return Response(
                str(e),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
