Things to test
1. Chunking strategy
    - Goal: Do the chunks present topics that are "close" to each other
    - Dimensions to test
        - Personal thoughts
            - "Closeness": Do they relate to a single topic/completely cover a single topic.  Ideally, you don't want to have to pull multiple chunks together to create a topic.  This will just be an eye test/something that I potentially return to when I do the tagging
            - Length: Want to make sure that I have a reasonable length so that you aren't pulling out too much for someone to read.
            - Cost: If I am using an approach that utilizes embeddings, how much does it cost to generate the embeddings and is the additional cost associated with the embeddings worth it by being able to use a cheaper LLM.  There is also the potential to self host an embedding endpoint via FastAPI, but that might get overwhelm the size of my instance.
        - Chat GPT Input
            - Chunk coherence: Does each chunk make sense by itself?
            - Topic Coverage: Are cunks likely to contain the relevant topic signal.
            - Redundancy: Does overlap introduce too much repetition
            - LLM Cost efficiency: Fever, denser chunks -> cheaper eval
            - False Positive/Negative Rate: Does the chunking method lead to more accurate topic detection
    - Approaches (outlined by ChatGPT with my thoughts)
        - (*Low Interest - Awkward splitting*) Fixed Size Overlapping Windows
            - Method: Split text into chunks of N tokens/words (e.g. 500-token chunks with 100-token overlap)
            - Pros: Simplicity, ensures contextual continuity
            - Cons: May split sentences or paragraphs awkwardly
            - Thoughts: Concerned with this approach due to splitting things awkwardly.  This might create a situation where I don't get the full relevant extract
        - (*Out - Transcript format*) Paragraph-based Chunking
            - Method: Split by paragraphs (or logical sections), optionally merging smaller ones until a size limit is reached.
            - Pros: Maintains semantic integrity.  Good for topics that follow structureal cues.
            - Cons: Paragraphs vary in size - some may be too small or too long
            - Thoughts: Think this one is out since the transcripts don't really have paragraphs.  They're basically just sentences.
        - (*Low Interest - Awkward Splittling*) Sentence-Level with Merging
            - Method: Tokenize into sentences, then merge adjacent ones until a max token limit is hit.
            - Pros: Clean boundaries; customizable for context
            - Cons: Merging can still result in odd breaks; topic continuity not guaranteed.
            - Thoughts: Once again, not really sure that this will capture the full topic due to the splitting.  Also, could just end up being really long
        - (*High Interest*) Semantic Chunking via Embeddings
            - Method: Compute embeddings for paragraps/sentences and group semantically similar ones together.
            - Pros: Dynamically forms coherent topic blocks.
            - Cons: More complex; requires embedding  + clustering (e.g. cosine similarity + KMeans or sliding merge)
            - Thoughts: This seems like the best one to do.
        - (*High Interest - Adjust Based on Topic Shifts*) Sliding Windows with Semantic Anchoring
            - Method: Start with fixed-size windows but adjust boundaries at natural language cues (e.g. sentence breaks or topic shifts using embeddings).
            - Pros: Balances structure and coherence.
            - Cons: More engineering required.
            - Thoughts: I like this one, ESPECIALLY if I can do the adjustment based on topic shifts using embeddings.
    - Analysis
        - Go with following
            1. Semantic Chunking via Embedding
            2. 
        - Consider the tooling
2. Topic Detection Approach: I am thinking that there are different ways to do this that will make sense
    - Possible Approaches:
        - My thoughts
            - No chunking, just feed the thing into an LLM
            - Chunk and then feed the chunks into an LLM
        - ChatGPT Input
            - Chunk-by-chunk classification
            - Chunk-by-chunk extraction: Basically, feed it a prompt that says to summarize if the chunk contains the topic
    - Dimensions to test: Basically, just feeding this into 
        - Cost: How much does it cost to run a get a label?
        - Accuracy: Do we get the correct labels?
    - Operationalizing the test: Basically just try labeling with different models, layered over the chunking strategy.
        | Model        | Input/Output Cost per 1M Tokens | Notes                            |
        | ------------ | ------------------------------- | -------------------------------- |
        | GPT-4.1 nano | $0.10/$0.40                     | Good option                      |
        | GPT-4.1 mini | $0.40/$1.60                     | Just better version of nano      |
        | GPT-4o mini  | $0.15/$0.60                     | Unnecessary - Multi-modal        |
        | o4-mini      | $1.10/$4.40                     | Unnecessary - STEM/visual        |
        | o3-mini      | $1.10/$4.40                     | Unnecessary - STEM               |
        | o3           | $10.00/$40.00                   | Unnecessary - Strategic Planning |
        | o1           | $15.00/$60.00                   | Unnecessary - Coding/Science     |

Considerations
- Since I am looking at the department transcripts for the purpose of the work, I need to focus specifically on department transcripts
- How am I going to do the testing?  Should I create evals for the chunking AND the topic labeling at once, OR should I do it in a two step process where I evaluate the chunking then try the labeling.
- Can I get tooling out of the box (thinking LangChain) that does the chunking approach for me?
- Include the "Chunk-by-chunk Extraction" labelling approach as opposed to just "Chunk-by-chunk Classification" if I'm not getting good results since it adds an element of interpretability.  To keep costs down, though, just go with one layer
- Similar logic for the "None" chunking strategy.  TBH I can just test this in the web app.

Experiment Matrix

| Chunking Strategy                      | Tagging Model | 
| -------------------------------------- | ------------- |
| Semantic Chunking via Embeddings       | GPT-4.1 nano  |
|                                        | GPT-4.1 mini  |
| Sliding Window with Semantic Anchoring | GPT-4.1 nano  |
|                                        | GPT-4.1 mini  |