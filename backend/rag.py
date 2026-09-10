import os
import time
from pathlib import Path

from dotenv import load_dotenv

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings
)

from langchain_core.prompts import PromptTemplate


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError(
        "GOOGLE_API_KEY not found. "
        "Put it inside backend/.env"
    )


# ============================================================
# MODELS
# ============================================================

embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001"
)


llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash",
    temperature=0
)


# ============================================================
# PROMPT
# ============================================================

prompt = PromptTemplate(
    template="""
You are a helpful AI assistant that answers questions
about a YouTube video.

The context below comes from the video's transcript.

IMPORTANT RULES:

1. Answer only using the provided context.
2. Do not invent information.
3. If the answer is not available in the context,
   say:

   "I couldn't find this information in the video."

4. Answer in the same language as the user's question.
5. Keep the answer clear and easy to understand.

---------------- CONTEXT ----------------

{context}

-------------- END CONTEXT --------------

Question:
{question}

Answer:
""",
    input_variables=[
        "context",
        "question"
    ]
)


# ============================================================
# VECTOR STORE DIRECTORY
# ============================================================

VECTORSTORE_DIR = Path("vectorstores")

VECTORSTORE_DIR.mkdir(
    exist_ok=True
)


# ============================================================
# GET YOUTUBE TRANSCRIPT
# ============================================================

def get_transcript(video_id):

    try:

        print(
            f"Fetching transcript for: {video_id}"
        )

        api = YouTubeTranscriptApi()

        transcript_list = api.fetch(
            video_id,
            languages=["hi"]
        )

        transcript_data = (
            transcript_list.to_raw_data()
        )

        print(
            f"Transcript entries: "
            f"{len(transcript_data)}"
        )

        return transcript_data

    except TranscriptsDisabled:

        raise Exception(
            "Transcripts are disabled for this video."
        )

    except Exception as e:

        raise Exception(
            f"Could not fetch transcript: {str(e)}"
        )


# ============================================================
# CREATE CHUNKS
# ============================================================

def create_chunks(video_id):

    transcript_data = get_transcript(
        video_id
    )

    # Same basic approach as your current RAG
    transcript = " ".join(
        item["text"]
        for item in transcript_data
    )

    print(
        f"Transcript characters: "
        f"{len(transcript)}"
    )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100
    )

    chunks = splitter.create_documents(
        [transcript]
    )

    # Add metadata
    for chunk in chunks:

        chunk.metadata = {
            "video_id": video_id,
            "language": "hi"
        }

    print(
        f"Number of chunks: "
        f"{len(chunks)}"
    )

    return chunks


# ============================================================
# INDEX VIDEO
# ============================================================

def index_video(video_id):

    print("=" * 60)

    print(
        f"INDEXING VIDEO: {video_id}"
    )

    print("=" * 60)

    chunks = create_chunks(
        video_id
    )

    batch_size = 10

    sleep_time = 5

    vector_store = None


    for i in range(
        0,
        len(chunks),
        batch_size
    ):

        batch = chunks[
            i:i + batch_size
        ]

        batch_number = (
            i // batch_size
        ) + 1

        total_batches = (
            len(chunks)
            + batch_size
            - 1
        ) // batch_size


        print(
            f"Processing batch "
            f"{batch_number}/"
            f"{total_batches}"
        )


        if vector_store is None:

            vector_store = (
                FAISS.from_documents(
                    batch,
                    embeddings
                )
            )

        else:

            vector_store.add_documents(
                batch
            )


        # Avoid hitting embedding rate limits
        if (
            i + batch_size
            < len(chunks)
        ):

            time.sleep(
                sleep_time
            )


    # Save vector store

    save_path = (
        VECTORSTORE_DIR
        / video_id
    )

    save_path.mkdir(
        parents=True,
        exist_ok=True
    )


    vector_store.save_local(
        str(save_path)
    )


    print(
        f"Vector store saved at:"
    )

    print(
        save_path
    )

    print("=" * 60)


# ============================================================
# CHECK VIDEO
# ============================================================

def video_exists(video_id):

    save_path = (
        VECTORSTORE_DIR
        / video_id
    )

    return (
        save_path.exists()
        and
        (save_path / "index.faiss").exists()
        and
        (save_path / "index.pkl").exists()
    )


# ============================================================
# LOAD VECTOR STORE
# ============================================================

def load_vector_store(video_id):

    save_path = (
        VECTORSTORE_DIR
        / video_id
    )

    if not video_exists(video_id):

        return None


    vector_store = FAISS.load_local(
        str(save_path),
        embeddings,
        allow_dangerous_deserialization=True
    )

    return vector_store


# ============================================================
# ANSWER QUESTION
# ============================================================

def answer_question(
    video_id,
    question
):

    print("=" * 60)

    print(
        f"VIDEO: {video_id}"
    )

    print(
        f"QUESTION: {question}"
    )

    print("=" * 60)


    # --------------------------------------------------------
    # Load existing vector store
    # --------------------------------------------------------

    vector_store = (
        load_vector_store(
            video_id
        )
    )


    # --------------------------------------------------------
    # If video is not indexed, index it
    # --------------------------------------------------------

    if vector_store is None:

        print(
            "Video not indexed."
        )

        print(
            "Starting indexing..."
        )

        index_video(
            video_id
        )

        vector_store = (
            load_vector_store(
                video_id
            )
        )


    # --------------------------------------------------------
    # Retriever
    # --------------------------------------------------------

    retriever = (
        vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": 4
            }
        )
    )


    # --------------------------------------------------------
    # Retrieve documents
    # --------------------------------------------------------

    retrieved_docs = (
        retriever.invoke(
            question
        )
    )


    print(
        f"Retrieved documents: "
        f"{len(retrieved_docs)}"
    )


    # --------------------------------------------------------
    # Create context
    # --------------------------------------------------------

    context = "\n\n".join(
        doc.page_content
        for doc in retrieved_docs
    )


    # --------------------------------------------------------
    # Create prompt
    # --------------------------------------------------------

    final_prompt = prompt.invoke(
        {
            "context": context,
            "question": question
        }
    )


    # --------------------------------------------------------
    # Generate answer
    # --------------------------------------------------------

    response = llm.invoke(
        final_prompt
    )


    # --------------------------------------------------------
    # Return result
    # --------------------------------------------------------

    return {

        "answer": response.content,

        "sources": [
            {
                "text": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in retrieved_docs
        ]

    }