import os
import time
from pathlib import Path

from dotenv import load_dotenv

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)

from langchain_core.prompts import PromptTemplate


load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_EMBEDDING_MODEL = os.getenv(
    "GEMINI_EMBEDDING_MODEL",
    "models/gemini-embedding-001",
)

if not GOOGLE_API_KEY:
    raise ValueError(
        "GOOGLE_API_KEY not found. Add it to backend/.env"
    )

PREFERRED_LANGUAGES = [
    lang.strip()
    for lang in os.getenv(
        "PREFERRED_LANGUAGES",
        "en,en-US,en-GB,hi,es,fr,de,ja,pt,ko",
    ).split(",")
    if lang.strip()
]

VECTORSTORE_DIR = Path(
    os.getenv("VECTORSTORE_DIR", "vectorstores")
)
VECTORSTORE_DIR.mkdir(exist_ok=True)

embeddings = GoogleGenerativeAIEmbeddings(
    model=GEMINI_EMBEDDING_MODEL,
)

llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=0,
)

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
    input_variables=["context", "question"],
)


def get_transcript(video_id: str) -> tuple[list[dict], str]:
    """Fetch transcript with language priority and automatic fallback."""
    print(f"Fetching transcript for: {video_id}")

    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)

    try:
        transcript = transcript_list.find_transcript(
            PREFERRED_LANGUAGES
        )
    except NoTranscriptFound:
        available = list(transcript_list)
        if not available:
            raise Exception(
                "No transcripts are available for this video."
            )
        transcript = available[0]

    fetched = transcript.fetch()
    transcript_data = fetched.to_raw_data()
    language = transcript.language_code

    print(
        f"Transcript language: {language}, "
        f"entries: {len(transcript_data)}"
    )

    return transcript_data, language


def create_chunks(video_id: str):
    transcript_data, language = get_transcript(video_id)

    transcript = " ".join(
        item["text"] for item in transcript_data
    )

    print(f"Transcript characters: {len(transcript)}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
    )

    chunks = splitter.create_documents([transcript])

    for chunk in chunks:
        chunk.metadata = {
            "video_id": video_id,
            "language": language,
        }

    print(f"Number of chunks: {len(chunks)}")
    return chunks


def index_video(video_id: str):
    print("=" * 60)
    print(f"INDEXING VIDEO: {video_id}")
    print("=" * 60)

    chunks = create_chunks(video_id)

    batch_size = 10
    sleep_time = 5
    vector_store = None

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        batch_number = (i // batch_size) + 1
        total_batches = (len(chunks) + batch_size - 1) // batch_size

        print(f"Processing batch {batch_number}/{total_batches}")

        if vector_store is None:
            vector_store = FAISS.from_documents(
                batch,
                embeddings,
            )
        else:
            vector_store.add_documents(batch)

        if i + batch_size < len(chunks):
            time.sleep(sleep_time)

    save_path = VECTORSTORE_DIR / video_id
    save_path.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(save_path))

    print(f"Vector store saved at: {save_path}")
    print("=" * 60)


def video_exists(video_id: str) -> bool:
    save_path = VECTORSTORE_DIR / video_id
    return (
        save_path.exists()
        and (save_path / "index.faiss").exists()
        and (save_path / "index.pkl").exists()
    )


def load_vector_store(video_id: str):
    if not video_exists(video_id):
        return None

    save_path = VECTORSTORE_DIR / video_id
    return FAISS.load_local(
        str(save_path),
        embeddings,
        allow_dangerous_deserialization=True,
    )


def check_transcript_available(video_id: str) -> dict:
    """Check whether a video has transcripts without indexing."""
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        available = [
            {
                "language": t.language,
                "language_code": t.language_code,
                "is_generated": t.is_generated,
            }
            for t in transcript_list
        ]
        return {
            "available": len(available) > 0,
            "transcripts": available,
        }
    except TranscriptsDisabled:
        return {
            "available": False,
            "error": "Transcripts are disabled for this video.",
        }
    except VideoUnavailable:
        return {
            "available": False,
            "error": "Video is unavailable.",
        }
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
        }


def answer_question(video_id: str, question: str) -> dict:
    print("=" * 60)
    print(f"VIDEO: {video_id}")
    print(f"QUESTION: {question}")
    print("=" * 60)

    vector_store = load_vector_store(video_id)

    if vector_store is None:
        print("Video not indexed. Starting indexing...")
        index_video(video_id)
        vector_store = load_vector_store(video_id)

    if vector_store is None:
        raise Exception("Failed to index video.")

    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 4},
    )

    retrieved_docs = retriever.invoke(question)

    print(f"Retrieved documents: {len(retrieved_docs)}")

    context = "\n\n".join(
        doc.page_content for doc in retrieved_docs
    )

    final_prompt = prompt.invoke(
        {
            "context": context,
            "question": question,
        }
    )

    response = llm.invoke(final_prompt)

    return {
        "answer": response.content,
        "video_id": video_id,
        "sources": [
            {
                "text": doc.page_content,
                "metadata": doc.metadata,
            }
            for doc in retrieved_docs
        ],
    }
