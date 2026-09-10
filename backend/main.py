from fastapi import FastAPI, HTTPException

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from rag import (
    answer_question,
    video_exists,
    index_video
)


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="YouTube RAG API",
    version="1.0.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"]
)


# ============================================================
# REQUEST MODELS
# ============================================================

class VideoRequest(BaseModel):

    video_id: str


class ChatRequest(BaseModel):

    video_id: str

    question: str


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def health_check():

    return {
        "status": "running",
        "message": "YouTube RAG API is working"
    }


# ============================================================
# REGISTER VIDEO
# ============================================================

@app.post("/video/register")
def register_video(
    request: VideoRequest
):

    try:

        video_id = request.video_id


        if video_exists(
            video_id
        ):

            return {
                "status": "already_indexed",
                "video_id": video_id
            }


        print(
            f"Indexing video: {video_id}"
        )


        index_video(
            video_id
        )


        return {
            "status": "indexed",
            "video_id": video_id
        }


    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# ============================================================
# CHAT
# ============================================================

@app.post("/chat")
def chat(
    request: ChatRequest
):

    try:

        result = answer_question(
            request.video_id,
            request.question
        )

        return result


    except Exception as e:

        print(
            "ERROR:",
            str(e)
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )