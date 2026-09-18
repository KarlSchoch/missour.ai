import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import TestCase
from transcription.models import (
    Transcript, Chunk, Topic, Tag, ModelPrice, TaskPricing, UsageEvent,
)
from transcription.services.pricing import PricingResolutionError
from transcription.tagging.tagging_manager import TaggingManager, Classification
from unittest.mock import patch
from transcription.tests.test_utils import FakeLLM

User = get_user_model()

IT_VOCAB = """
cloud computing microservices kubernetes containers orchestration devops ci cd
infrastructure automation terraform ansible helm service mesh observability
telemetry tracing logging metrics promethus grafana loadbalancer api gateway
rest graphql grpc backend frontend javascript typescript react django flask
python java go rust csharp dotnet postgresql mysql sqlite redis kafka
eventstream pubsub schema registry protobuf avro parquet data lake warehouse
etl elt airflow dbt spark databricks lakehouse mlops model registry feature
store embeddings vector database faiss pgvector milvus llama inference
latency throughput scalability highavailability faulttolerance resiliency
security auth oauth oidc jwt tls certificate rotation secrets vault kms
sso rbac abac encryption at rest in transit key rotation pentest
"""

WF_VOCAB = """
apprenticeship reskilling upskilling workforce development learning pathways
competency frameworks curriculum design instructional design microlearning
mentorship coaching internship onboarding compliance training lms assessment
credential certification badging career ladder career lattice performance
review training needs analysis job task analysis ojt on the job training
capstone projects bootcamp cohort peer learning simulation roleplay softskills
communication teamwork leadership problem solving critical thinking
digital literacy inclusion accessibility universal design adult learning
andragogy evaluation kirkpatrick outcomes placement employability internship
apprentice stipend scholarship outreach recruitment retention scalability
"""


class FakeLLMWithExceptions(FakeLLM):
    def invoke(self, prompt):
        self.invocations.append(prompt)
        try:
            next_result = self.scripted_results.pop(0)
        except IndexError:
            raise AssertionError("FakeLLm ran out of scripted responses")

        if isinstance(next_result, Exception):
            raise next_result

        return next_result

# Create your tests here.
class TaggingTests(TestCase):
    model_name = "tagging-manager-test-model"

    def setUp(self):
        # Call TestCase's setUp() 
        super().setUp()
        # Create patcher for environment variables
        self.env_patcher = patch.dict(
            os.environ,
            {
                "MODEL_ENV": "test",
                "OPENAI_API_KEY": "test-key",
            },
            clear=False,
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)
        model_patcher = patch(
            "transcription.tagging.tagging_manager.settings.TAGGING_MODEL",
            self.model_name,
        )
        model_patcher.start()
        self.addCleanup(model_patcher.stop)

        # Create fakeLLM with 8 fake responses
        fake_responses = [
            Classification(tag=True, relevant_section=IT_VOCAB[:25]),
            Classification(tag=False, relevant_section=""),
            Classification(tag=True, relevant_section=IT_VOCAB[len(IT_VOCAB) - 25:]),
            Classification(tag=False, relevant_section=""),
            Classification(tag=False, relevant_section=""),
            Classification(tag=True, relevant_section=WF_VOCAB[:25]),
            Classification(tag=False, relevant_section=""),
            Classification(tag=True, relevant_section=WF_VOCAB[len(WF_VOCAB) - 25:]),
        ]
        self.fake_llm = FakeLLM(fake_responses)

        # Assocate LLM to patch
        patcher = patch(
            "transcription.tagging.tagging_manager.init_chat_model",
            return_value=self.fake_llm
        )
        self.addCleanup(patcher.stop)
        self.mock_init = patcher.start()

        self.model_price = ModelPrice.objects.create(
            provider=ModelPrice.Provider.OPENAI,
            model_name=self.model_name,
            billing_unit=ModelPrice.BillingUnit.TEXT_TOKENS,
            input_rate_per_million=Decimal("1.00"),
            cached_input_rate_per_million=Decimal("0.25"),
            output_rate_per_million=Decimal("2.00"),
            currency="USD",
            effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        self.task_pricing = TaskPricing.objects.create(
            task_type=TaskPricing.TaskType.TAGGING,
            model_price=self.model_price,
            multiplier=Decimal("1.0"),
            effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )

    def _response(self, classification, request_id):
        raw = SimpleNamespace(
            id=request_id,
            usage_metadata={
                "input_tokens": 100,
                "output_tokens": 20,
                "input_token_details": {"cache_read": 10},
            },
            response_metadata={},
        )
        return {"parsed": classification, "raw": raw}

    def _make_transcript(self, text=""):
        payload = text or (IT_VOCAB + " " + WF_VOCAB)
        return Transcript.objects.create(
            name=f"Transcript {Transcript.objects.count() + 1}",
            transcript_text=payload,
            created_by=self.user,
        )

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tagging-user", password="pw")
        cls.other_user = User.objects.create_user(username="other-user", password="pw")
        cls.transcript = Transcript.objects.create(
            name="Dummy Transcript",
            transcript_text= IT_VOCAB + " " + WF_VOCAB,
            created_by=cls.user,
        )
        cls.topic_it = Topic.objects.create(
            topic = "Information Technology",
            description = "",
            created_by=cls.user,
        )
        cls.topic_wf = Topic.objects.create(
            topic = "Workforce Training",
            description = "",
            created_by=cls.user,
        )
        cls.chunk_wf = Chunk.objects.create(
            transcript = cls.transcript,
            chunk_text = WF_VOCAB,
        )

    def test_chunk(self):
        # Validate that the chunks are actually in the database
        before = Chunk.objects.count()
        blah = TaggingManager(os.getenv('OPENAI_API_KEY'), self.transcript)
        created_chunks = blah.chunk()
        after = Chunk.objects.count()
        ## Validate that some records were created
        self.assertGreater(after, before)
        ## Validate that the correct number of records were created
        self.assertEqual(after, before + len(created_chunks))
        ## Validate that the specific chunks are in the database
        db_pks = set(
            Chunk.objects.filter(transcript=self.transcript)\
                .values_list("id", flat=True)
        )
        self.assertTrue(
            {c.pk for c in created_chunks}.issubset(db_pks)
        )

    def test_tag_chunk(self):
        # Define mock used by init_chat_model
        fake_responses = [
            Classification(tag=True, relevant_section="cloud computing microservices kubernetes"),
            Classification(tag=False, relevant_section="")
        ]

        before = Tag.objects.count()
        blah = TaggingManager(
            os.getenv('OPENAI_API_KEY'),
            transcript = self.transcript,
            topics = [self.topic_it, self.topic_wf],
            tagging_model=self.model_name,
        )
        created_chunks = blah.chunk()
        tgt_chunk = created_chunks[0]
        created_tags = blah.tag_chunk(tgt_chunk)
        # Validated that you did not reach out to the API
        self.mock_init.assert_called()
        after = Tag.objects.count()
        
        # Validate that tags are actually created
        self.assertGreater(after, before)
        ## Validate that the correct number of records were created
        self.assertEqual(after, before + len(created_tags))
        ## Validate that the specific tags are in the database
        db_pks = set(
            Tag.objects.filter(chunk=tgt_chunk)\
                .values_list("id", flat=True)
        )
        self.assertTrue(
            {c.pk for c in created_tags}.issubset(db_pks)
        )

    def test_tag_transcript(self):
        # Count initial number of Tags and Chunks associated with the transcript
        chunk_ct_initial = Chunk.objects.filter(transcript=self.transcript).count()
        # related_chunk = Chunk.objects.filter(transcript__name="Dummy Transcript")[:1]
        tag_ct_initial = Tag.objects.filter(chunk__transcript__name="Dummy Transcript").count()

        # Run the transcription manager
        blah = TaggingManager(
            os.getenv('OPENAI_API_KEY'),
            transcript = self.transcript,
            topics = [self.topic_it, self.topic_wf],
            tagging_model=self.model_name,
        )
        created_records = blah.tag_transcript()
        # Validated that you did not reach out to the API
        self.mock_init.assert_called()

        # Count final number of Tags and Chunks associated the transcript
        chunk_ct_final = Chunk.objects.filter(transcript=self.transcript).count()
        # related_chunks = Chunk.objects.filter(transcript__name="Dummy Transcript")
        tag_ct_final = Tag.objects.filter(chunk__transcript__name="Dummy Transcript").count()

        # Ensure tags and chunks are actually created
        self.assertGreater(chunk_ct_final, chunk_ct_initial)
        self.assertGreater(tag_ct_final, tag_ct_initial)

        # Ensure the correct number of records are created
        # Tags: 8 (4 for Information Technology, 4 for Workforce Training)
        wf_tng_tags = Tag.objects.filter(
            chunk__transcript__name="Dummy Transcript", topic__topic="Workforce Training"
        )
        self.assertEqual(4, len(wf_tng_tags))
        it_tags = Tag.objects.filter(
            chunk__transcript__name="Dummy Transcript", topic__topic="Information Technology"
        )
        self.assertEqual(4, len(it_tags))
        # Ensure that the usage events are tracked
        events = UsageEvent.objects.filter(transcript=self.transcript)
        self.assertEqual(events.count(), len(created_records))
        self.assertTrue(events.exists())
        # Validate specific elements within the usage events records
        ## No Failed/In Progress records exist
        self.assertFalse(events.exclude(status=UsageEvent.Status.SUCCEEDED).exists())
        ## Usage Event records are associated with tags
        self.assertFalse(events.filter(tag__isnull=True).exists())
        self.assertEqual(
            set(events.values_list("tag_id", flat=True)),
            {tag.pk for tag in created_records},
        )

    def test_tag_transcript_creates_chunks_when_none_exist(self):
        transcript = self._make_transcript(IT_VOCAB)
        self.assertFalse(Chunk.objects.filter(transcript=transcript).exists())

        self.mock_init.return_value = FakeLLM([
            Classification(tag=True, relevant_section="hit"),
        ] * 100)

        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"),
            transcript=transcript,
            topics=[self.topic_it],
        )
        manager.tag_transcript()

        chunk_count = Chunk.objects.filter(transcript=transcript).count()
        tag_count = Tag.objects.filter(chunk__transcript=transcript, topic=self.topic_it).count()

        self.assertGreater(chunk_count, 0)
        self.assertEqual(tag_count, chunk_count)

    def test_reconciliation_preserves_tagged_history_and_is_repeatable(self):
        transcript = self._make_transcript("alpha beta\n\ngamma delta\n\nepsilon zeta")
        stale = Chunk.objects.create(transcript=transcript, chunk_text="alpha")
        historical = Tag.objects.create(
            chunk=stale, topic=self.topic_it, topic_present=True,
            relevant_section="alpha", user_validation=True,
        )
        from transcription.services.pricing import create_pending_usage_event, complete_token_event
        event = create_pending_usage_event(
            user=transcript.created_by, transcript=transcript, tag=historical,
            task_type=TaskPricing.TaskType.TAGGING, provider="openai",
            model_name=self.model_name, idempotency_key="historical-tag",
        )
        event = complete_token_event(event, input_tokens=10, output_tokens=2)
        original_cost = event.billed_cost
        reusable = Chunk.objects.create(transcript=transcript, chunk_text="gamma delta")
        negative = Tag.objects.create(chunk=reusable, topic=self.topic_it, topic_present=False)
        unused = Chunk.objects.create(transcript=transcript, chunk_text="epsilon")
        llm = FakeLLM([Classification(tag=True, relevant_section="hit")] * 2)
        self.mock_init.return_value = llm
        manager = TaggingManager("test-key", transcript, [self.topic_it], chunk_size=14, chunk_overlap=0)
        manager.tag_transcript()
        stale.refresh_from_db()
        historical.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(event.tag_id, historical.pk)
        self.assertEqual(event.billed_cost, original_cost)
        self.assertEqual(event.status, UsageEvent.Status.SUCCEEDED)
        negative.refresh_from_db()
        self.assertTrue(stale.is_superseded)
        self.assertTrue(historical.user_validation)
        self.assertFalse(negative.topic_present)
        self.assertFalse(Chunk.objects.filter(pk=unused.pk).exists())
        current = list(Chunk.objects.filter(transcript=transcript, is_superseded=False).order_by("position"))
        self.assertEqual([c.chunk_text for c in current], ["alpha beta", "gamma delta", "epsilon zeta"])
        self.assertEqual(current[1].pk, reusable.pk)
        self.assertEqual(len(llm.invocations), 2)
        self.assertEqual(manager.tag_transcript(), [])
        self.assertEqual(len(llm.invocations), 2)
        self.assertEqual(Chunk.objects.filter(transcript=transcript).count(), 4)
        from transcription.api_views import TagViewSet
        from transcription.templatetags.transcription_tags import render_view_transcript_chunks_section

        request = SimpleNamespace(user=transcript.created_by)
        view = TagViewSet()
        view.request = request
        self.assertNotIn(historical.pk, view.get_queryset().values_list("pk", flat=True))
        payload = render_view_transcript_chunks_section({"request": request, "transcript": transcript})
        self.assertEqual(
            [row["chunk_id"] for row in payload["initial_payload"]["rows"]],
            [c.pk for c in current],
        )

    def test_reconciliation_rolls_back_partial_creation(self):
        transcript = self._make_transcript("alpha beta\n\ngamma delta")
        original = Chunk.objects.create(transcript=transcript, chunk_text="alpha")
        manager = TaggingManager("test-key", transcript, chunk_size=12, chunk_overlap=0)
        create = Chunk.objects.create
        calls = 0

        def fail_second(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("interrupted chunk creation")
            return create(**kwargs)

        with patch.object(Chunk.objects, "create", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                manager.reconcile_chunks()
        self.assertEqual(list(Chunk.objects.filter(transcript=transcript)), [original])
        self.assertEqual(manager.chunks, [])

    def test_reconciliation_preserves_repeated_text_occurrences(self):
        transcript = self._make_transcript("alpha beta\n\nalpha beta")
        original = Chunk.objects.create(transcript=transcript, chunk_text="  alpha beta  ")
        manager = TaggingManager("test-key", transcript, chunk_size=12, chunk_overlap=0)
        current = manager.reconcile_chunks()
        self.assertEqual(len(current), 2)
        self.assertEqual(current[0].pk, original.pk)
        self.assertNotEqual(current[0].pk, current[1].pk)
        self.assertEqual([c.pk for c in manager.reconcile_chunks()], [c.pk for c in current])

    def test_tag_transcript_reuses_existing_chunks_without_creating_new_ones(self):
        transcript = self._make_transcript("alpha beta gamma\n\ndelta epsilon zeta")
        chunk_one = Chunk.objects.create(transcript=transcript, chunk_text="alpha beta gamma")
        chunk_two = Chunk.objects.create(transcript=transcript, chunk_text="delta epsilon zeta")

        self.mock_init.return_value = FakeLLM([
            Classification(tag=False, relevant_section=""),
            Classification(tag=True, relevant_section="delta epsilon"),
        ])

        before = Chunk.objects.filter(transcript=transcript).count()
        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"),
            transcript=transcript,
            topics=[self.topic_it],
            chunk_size=20, chunk_overlap=0,
        )
        manager.tag_transcript()
        after = Chunk.objects.filter(transcript=transcript).count()

        self.assertEqual(before, 2)
        self.assertEqual(after, before)
        self.assertTrue(Chunk.objects.filter(pk=chunk_one.pk).exists())
        self.assertTrue(Chunk.objects.filter(pk=chunk_two.pk).exists())

    def test_tag_transcript_only_processes_missing_chunk_topic_pairs(self):
        transcript = self._make_transcript("first second third fourth")
        chunk_one = Chunk.objects.create(transcript=transcript, chunk_text="first second")
        chunk_two = Chunk.objects.create(transcript=transcript, chunk_text="third fourth")

        Tag.objects.create(
            chunk=chunk_one,
            topic=self.topic_it,
            topic_present=True,
            relevant_section="first",
        )

        llm = FakeLLM([Classification(tag=False, relevant_section="")])
        self.mock_init.return_value = llm

        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"),
            transcript=transcript,
            topics=[self.topic_it],
            chunk_size=13, chunk_overlap=0,
        )
        manager.tag_transcript()

        self.assertEqual(len(llm.invocations), 1)
        self.assertEqual(
            Tag.objects.filter(chunk__transcript=transcript, topic=self.topic_it).count(),
            2,
        )
        self.assertTrue(
            Tag.objects.filter(chunk=chunk_two, topic=self.topic_it).exists()
        )

    def test_tag_transcript_noop_when_all_pairs_already_tagged(self):
        transcript = self._make_transcript("zero one two three")
        chunk_one = Chunk.objects.create(transcript=transcript, chunk_text="zero one")
        chunk_two = Chunk.objects.create(transcript=transcript, chunk_text="two three")

        Tag.objects.create(
            chunk=chunk_one,
            topic=self.topic_it,
            topic_present=False,
            relevant_section="",
        )
        Tag.objects.create(
            chunk=chunk_two,
            topic=self.topic_it,
            topic_present=True,
            relevant_section="three",
        )

        llm = FakeLLM([
            Classification(tag=False, relevant_section=""),
        ] * 50)
        self.mock_init.return_value = llm

        chunk_before = Chunk.objects.filter(transcript=transcript).count()
        tag_before = Tag.objects.filter(chunk__transcript=transcript, topic=self.topic_it).count()

        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"),
            transcript=transcript,
            topics=[self.topic_it],
            chunk_size=10, chunk_overlap=0,
        )
        manager.tag_transcript()

        self.assertEqual(len(llm.invocations), 0)
        self.assertEqual(Chunk.objects.filter(transcript=transcript).count(), chunk_before)
        self.assertEqual(
            Tag.objects.filter(chunk__transcript=transcript, topic=self.topic_it).count(),
            tag_before,
        )

    def test_tag_transcript_initializes_llm_once_per_run(self):
        transcript = self._make_transcript((IT_VOCAB + " ") * 8)
        self.mock_init.reset_mock()
        self.mock_init.return_value = FakeLLM([
            Classification(tag=True, relevant_section="hit"),
        ] * 300)

        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"),
            transcript=transcript,
            topics=[self.topic_it, self.topic_wf],
            chunk_size=120,
            chunk_overlap=0,
        )
        manager.tag_transcript()

        self.assertEqual(self.mock_init.call_count, 1)

    def test_tag_transcript_records_failed_pairs_without_crashing_run(self):
        transcript = self._make_transcript("lorem ipsum\n\ndolor sit amet")
        Chunk.objects.create(transcript=transcript, chunk_text="lorem ipsum")
        Chunk.objects.create(transcript=transcript, chunk_text="dolor sit amet")

        llm = FakeLLMWithExceptions([
            Classification(tag=True, relevant_section="lorem"),
            RuntimeError("simulated model error"),
        ])
        self.mock_init.return_value = llm

        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"),
            transcript=transcript,
            topics=[self.topic_it],
            chunk_size=16, chunk_overlap=0,
        )

        tags = manager.tag_transcript()
        self.assertEqual(len(tags), 1)
        self.assertTrue(hasattr(manager, "failed_pairs"))
        self.assertEqual(len(manager.failed_pairs), 1)
        self.assertEqual(
            Tag.objects.filter(chunk__transcript=transcript, topic=self.topic_it).count(),
            1,
        )

    def test_tag_transcript_pricing_failure_creates_no_usage_event(self):
        transcript = self._make_transcript("missing pricing")
        Chunk.objects.create(transcript=transcript, chunk_text=transcript.transcript_text)
        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"),
            transcript=transcript,
            topics=[self.topic_it],
            tagging_model="model-with-no-price",
        )

        with self.assertRaises(PricingResolutionError):
            manager.tag_transcript()

        self.assertFalse(UsageEvent.objects.filter(transcript=transcript).exists())
        self.assertFalse(Tag.objects.filter(chunk__transcript=transcript).exists())
        self.assertEqual(len(self.fake_llm.invocations), 0)

    def test_tag_transcript_llm_failure_marks_usage_event_failed(self):
        transcript = self._make_transcript("provider failure")
        Chunk.objects.create(transcript=transcript, chunk_text=transcript.transcript_text)
        llm = FakeLLMWithExceptions([RuntimeError("provider unavailable")])
        self.mock_init.return_value = llm

        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"), transcript=transcript, topics=[self.topic_it]
        )
        tags = manager.tag_transcript()

        self.assertEqual(tags, [])
        self.assertFalse(Tag.objects.filter(chunk__transcript=transcript).exists())
        event = UsageEvent.objects.get(transcript=transcript)
        self.assertEqual(event.status, UsageEvent.Status.FAILED)
        self.assertIn(
            "provider unavailable",
            event.calculation_details["lifecycle"]["reason"],
        )

    def test_tag_transcript_regenerate_false_is_noop(self):
        transcript = self._make_transcript("existing classification")
        chunk = Chunk.objects.create(
            transcript=transcript, chunk_text=transcript.transcript_text
        )
        tag = Tag.objects.create(
            chunk=chunk,
            topic=self.topic_it,
            topic_present=True,
            relevant_section="original",
        )
        llm = FakeLLM([Classification(tag=False, relevant_section="replacement")])
        self.mock_init.return_value = llm

        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"), transcript=transcript, topics=[self.topic_it]
        )
        result = manager.tag_transcript(regenerate=False)

        tag.refresh_from_db()
        self.assertEqual(result, [])
        self.assertEqual(tag.relevant_section, "original")
        self.assertEqual(len(llm.invocations), 0)
        self.assertFalse(UsageEvent.objects.filter(transcript=transcript).exists())

    def test_tag_transcript_regenerate_true_updates_tag_and_creates_new_usage(self):
        transcript = self._make_transcript("existing classification")
        chunk = Chunk.objects.create(
            transcript=transcript, chunk_text=transcript.transcript_text
        )
        tag = Tag.objects.create(
            chunk=chunk,
            topic=self.topic_it,
            topic_present=False,
            relevant_section="original",
        )
        first_llm = FakeLLM([
            self._response(
                Classification(tag=True, relevant_section="first replacement"),
                "tag-request-1",
            )
        ])
        self.mock_init.return_value = first_llm
        TaggingManager(
            os.getenv("OPENAI_API_KEY"), transcript=transcript, topics=[self.topic_it]
        ).tag_transcript(regenerate=True)

        second_llm = FakeLLM([
            self._response(
                Classification(tag=False, relevant_section="second replacement"),
                "tag-request-2",
            )
        ])
        self.mock_init.return_value = second_llm
        TaggingManager(
            os.getenv("OPENAI_API_KEY"), transcript=transcript, topics=[self.topic_it]
        ).tag_transcript(regenerate=True)

        tag.refresh_from_db()
        events = UsageEvent.objects.filter(transcript=transcript).order_by("created_at")
        self.assertEqual(Tag.objects.filter(chunk=chunk, topic=self.topic_it).count(), 1)
        self.assertFalse(tag.topic_present)
        self.assertEqual(tag.relevant_section, "second replacement")
        self.assertEqual(events.count(), 2)
        self.assertEqual(
            list(events.values_list("provider_request_id", flat=True)),
            ["tag-request-1", "tag-request-2"],
        )
        self.assertEqual(events.filter(tag=tag).count(), 2)

    def test_tag_transcript_completion_failure_maintains_tag_ands_requires_reconciliation(self):
        transcript = self._make_transcript("ledger failure")
        Chunk.objects.create(transcript=transcript, chunk_text=transcript.transcript_text)
        llm = FakeLLM([
            self._response(
                Classification(tag=True, relevant_section="ledger"),
                "tag-request-reconcile",
            )
        ])
        self.mock_init.return_value = llm
        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"), transcript=transcript, topics=[self.topic_it]
        )

        with patch(
            "transcription.tagging.tagging_manager.complete_token_event",
            side_effect=RuntimeError("ledger completion failed"),
        ):
            tags = manager.tag_transcript()

        self.assertGreater(len(tags), 0)
        self.assertTrue(Tag.objects.filter(chunk__transcript=transcript).exists())
        event = UsageEvent.objects.get(transcript=transcript)
        self.assertEqual(event.status, UsageEvent.Status.RECONCILIATION_REQUIRED)
        self.assertIsNotNone(event.tag)
        self.assertTrue(
            event.calculation_details["lifecycle"]["provider_response_received"]
        )
        self.assertIn(
            "ledger completion failed",
            event.calculation_details["lifecycle"]["reason"],
        )

    def test_tag_transcript_missing_token_usage_keys_requires_reconciliation(self):
        for missing_key in ("input_tokens", "output_tokens"):
            with self.subTest(missing_key=missing_key):
                transcript = self._make_transcript(f"missing {missing_key}")
                Chunk.objects.create(
                    transcript=transcript, chunk_text=transcript.transcript_text
                )
                response = self._response(
                    Classification(tag=True, relevant_section="missing metadata"),
                    f"tag-request-missing-{missing_key}",
                )
                del response["raw"].usage_metadata[missing_key]
                self.mock_init.return_value = FakeLLM([response])
                manager = TaggingManager(
                    os.getenv("OPENAI_API_KEY"),
                    transcript=transcript,
                    topics=[self.topic_it],
                )

                with patch.dict(os.environ, {"MODEL_ENV": "production"}):
                    tags = manager.tag_transcript()

                self.assertGreater(len(tags), 0)
                self.assertTrue(
                    Tag.objects.filter(chunk__transcript=transcript).exists()
                )
                event = UsageEvent.objects.get(transcript=transcript)
                self.assertEqual(
                    event.status, UsageEvent.Status.RECONCILIATION_REQUIRED
                )
                self.assertIsNotNone(event.provider_request_id)
                self.assertIsNone(event.input_tokens)
                self.assertIsNone(event.output_tokens)
                self.assertTrue(
                    event.calculation_details["lifecycle"]
                    ["provider_response_received"]
                )

    def test_tag_chunk_uses_text_values_for_prompt_inputs(self):
        transcript = self._make_transcript("alpha beta gamma")
        chunk = Chunk.objects.create(transcript=transcript, chunk_text="alpha beta")
        topic = Topic.objects.create(
            topic="Prompt Topic",
            description="",
            created_by=self.user,
        )

        with patch(
            "transcription.tagging.tagging_manager.ChatPromptTemplate.from_template"
        ) as prompt_mock:
            prompt_instance = prompt_mock.return_value
            prompt_instance.invoke.return_value = {"prompt": "ok"}

            llm = FakeLLM([Classification(tag=True, relevant_section="alpha")])
            self.mock_init.return_value = llm

            manager = TaggingManager(
                os.getenv("OPENAI_API_KEY"),
                transcript=transcript,
                topics=[topic],
            )
            manager.tag_chunk(chunk, [topic])

            invoked_payload = prompt_instance.invoke.call_args[0][0]
            self.assertEqual(invoked_payload["passage"], chunk.chunk_text)
            self.assertEqual(invoked_payload["topic"], topic.topic)

    def test_tagging_rejects_topic_owned_by_different_user(self):
        other_topic = Topic.objects.create(
            topic="Other User Topic",
            description="",
            created_by=self.other_user,
        )
        manager = TaggingManager(
            os.getenv("OPENAI_API_KEY"),
            transcript=self.transcript,
            topics=[other_topic],
        )

        with self.assertRaises(ValueError):
            manager.tag_transcript()
