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
    version="1.1.0",
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


class VideoRequest(BaseModel):
    video_id: str = Field(..., min_length=6, max_length=20)


class ChatRequest(BaseModel):
    video_id: str = Field(..., min_length=6, max_length=20)
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/")
def health_check():
    return {
        "status": "running",
        "message": "YouTube RAG API is working",
        "version": "1.1.0",
    }


@app.get("/video/{video_id}/status")
def video_status(video_id: str):
    transcript = check_transcript_available(video_id)
    return {
        "video_id": video_id,
        "indexed": video_exists(video_id),
        "transcript": transcript,
    }


@app.post("/video/register")
def register_video(request: VideoRequest):
    try:
        video_id = request.video_id

        transcript = check_transcript_available(video_id)
        if not transcript.get("available"):
            raise HTTPException(
                status_code=404,
                detail=transcript.get(
                    "error",
                    "No transcript available for this video.",
                ),
            )

        if video_exists(video_id):
            return {
                "status": "already_indexed",
                "video_id": video_id,
            }

        print(f"Indexing video: {video_id}")
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
        transcript = check_transcript_available(request.video_id)
        if not transcript.get("available"):
            raise HTTPException(
                status_code=404,
                detail=transcript.get(
                    "error",
                    "No transcript available for this video.",
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
