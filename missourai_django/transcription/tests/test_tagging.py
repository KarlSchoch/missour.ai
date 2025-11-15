import os
from django.test import TestCase
from transcription.models import Transcript, Chunk, Topic, Tag
from transcription.tagging.tagging_manager import TaggingManager

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

# Create your tests here.
class TaggingTests(TestCase):
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
        # Tag.objects.create(
        #     chunk=cls.chunk_wf, 
        #     topic=cls.topic_wf,
        #     topic_present = True,
        #     relevant_section = WF_VOCAB[:50],
        #     user_validation = False,
        # )

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
        before = Tag.objects.count()
        blah = TaggingManager(
            os.getenv('OPENAI_API_KEY'),
            transcript = self.transcript,
            topics = [self.topic_it, self.topic_wf]
        )
        created_chunks = blah.chunk()
        created_tags = blah.tag_chunk()
        after = Tag.objects.count()
        
        # Validate that tags are actually created
        self.assertGreater(after, before)
        ## Validate that the correct number of records were created
        self.assertEqual(after, before + len(created_tags))
        ## Validate that the specific chunks are in the database
        print("created_tags")
        for tag in created_tags:
            print(tag)

    def test_tag_transcript(self):
        # Count initial number of Tags and Chunks associated with the transcript
        chunk_ct_initial = Chunk.objects.filter(transcript=self.transcript).count()
        # related_chunk = Chunk.objects.filter(transcript__name="Dummy Transcript")[:1]
        tag_ct_initial = Tag.objects.filter(chunk__transcript__name="Dummy Transcript").count()

        # Run the transcription manager
        blah = TaggingManager(os.getenv('OPENAI_API_KEY'))
        created_records = blah.tag_transcript()
        print("created_records")
        for record in created_records:
            print(record)

        # Count final number of Tags and Chunks associated the transcript
        chunk_ct_final = Chunk.objects.filter(transcript=self.transcript).count()
        # related_chunks = Chunk.objects.filter(transcript__name="Dummy Transcript")
        tag_ct_final = Tag.objects.filter(chunk__transcript__name="Dummy Transcript").count()

        # Ensure tags and chunks are actually created
        self.assertGreater(chunk_ct_initial, chunk_ct_final)
        self.assertGreater(tag_ct_initial, tag_ct_final)

        # Ensure the correct number of records are created
        # TO DO: Understand how to filter created_recrods into tags and chunks
        # self.assertEqual(chunk_ct_final, chunk_ct_initial + len(???))
        # self.assertEqual(tag_ct_final, tag_ct_initial + len(???))

        # Ensure the specific chunks and tags are in the database