import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rag import (
    answer_question,
    check_transcript_available,
    index_video,
    video_exists,
)


app = FastAPI(
    title="YouTube RAG API",
    version="1.2.0",
)

allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = (
    ["*"]
    if allowed_origins_env.strip() == "*"
    else [
        origin.strip()
        for origin in allowed_origins_env.split(",")
        if origin.strip()
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TranscriptSegment(BaseModel):
    text: str = Field(..., min_length=1)
    start: float = 0
    duration: float = 0


class VideoRequest(BaseModel):
    video_id: str = Field(..., min_length=6, max_length=20)
    language: str | None = None
    segments: list[TranscriptSegment] | None = None


class ChatRequest(BaseModel):
    video_id: str = Field(..., min_length=6, max_length=20)
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/")
def health_check():
    return {
        "status": "running",
        "message": "YouTube RAG API is working",
        "version": "1.2.0",
        "transcript_mode": "client_or_server",
    }


@app.get("/video/{video_id}/status")
def video_status(video_id: str, check_youtube: bool = False):
    result = {
        "video_id": video_id,
        "indexed": video_exists(video_id),
    }

    if check_youtube:
        result["transcript"] = check_transcript_available(video_id)

    return result


@app.post("/video/register")
def register_video(request: VideoRequest):
    try:
        video_id = request.video_id

        if video_exists(video_id):
            return {
                "status": "already_indexed",
                "video_id": video_id,
            }

        if request.segments:
            transcript_data = [
                {
                    "text": segment.text,
                    "start": segment.start,
                    "duration": segment.duration,
                }
                for segment in request.segments
            ]

            print(
                f"Indexing video from client transcript: {video_id}"
            )
            index_video(
                video_id,
                transcript_data=transcript_data,
                language=request.language,
            )
        else:
            transcript = check_transcript_available(video_id)
            if not transcript.get("available"):
                raise HTTPException(
                    status_code=404,
                    detail=transcript.get(
                        "error",
                        "No transcript available for this video.",
                    ),
                )

            print(f"Indexing video from server transcript: {video_id}")
            index_video(video_id)

        return {
            "status": "indexed",
            "video_id": video_id,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        if not video_exists(request.video_id):
            raise HTTPException(
                status_code=404,
                detail=(
                    "Video is not indexed yet. "
                    "Open the video in the extension and wait "
                    "for indexing to finish."
                ),
            )

        return answer_question(
            request.video_id,
            request.question,
        )

    except HTTPException:
        raise
    except Exception as exc:
        print("ERROR:", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
