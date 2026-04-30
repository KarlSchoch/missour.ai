import os
from django.test import TestCase
from transcription.models import Transcript, Chunk, Topic, Tag
from transcription.tagging.tagging_manager import TaggingManager, Classification
from unittest.mock import patch
from transcription.tests.test_utils import FakeLLM

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

    def _make_transcript(self, text=""):
        payload = text or (IT_VOCAB + " " + WF_VOCAB)
        return Transcript.objects.create(
            name=f"Transcript {Transcript.objects.count() + 1}",
            transcript_text=payload,
        )

    @classmethod
    def setUpTestData(cls):
        cls.transcript = Transcript.objects.create(
            name="Dummy Transcript",
            transcript_text= IT_VOCAB + " " + WF_VOCAB
        )
        cls.topic_it = Topic.objects.create(
            topic = "Information Technology",
            description = ""
        )
        cls.topic_wf = Topic.objects.create(
            topic = "Workforce Training",
            description = ""
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
            topics = [self.topic_it, self.topic_wf]
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
            topics = [self.topic_it, self.topic_wf]
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

    def test_tag_transcript_reuses_existing_chunks_without_creating_new_ones(self):
        transcript = self._make_transcript("alpha beta gamma delta epsilon zeta eta theta")
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
        transcript = self._make_transcript("lorem ipsum dolor sit amet consectetur")
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
        )

        tags = manager.tag_transcript()
        self.assertEqual(len(tags), 1)
        self.assertTrue(hasattr(manager, "failed_pairs"))
        self.assertEqual(len(manager.failed_pairs), 1)
        self.assertEqual(
            Tag.objects.filter(chunk__transcript=transcript, topic=self.topic_it).count(),
            1,
        )

    def test_tag_chunk_uses_text_values_for_prompt_inputs(self):
        transcript = self._make_transcript("alpha beta gamma")
        chunk = Chunk.objects.create(transcript=transcript, chunk_text="alpha beta")
        topic = Topic.objects.create(topic="Prompt Topic", description="")

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
