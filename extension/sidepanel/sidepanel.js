// ============================================================
// CONFIGURATION
// ============================================================

const API_URL =
    "http://127.0.0.1:8000";


// ============================================================
// GLOBAL STATE
// ============================================================

let currentVideoId = null;


// ============================================================
// GET CURRENT TAB
// ============================================================

async function getCurrentTab() {

    const tabs =
        await chrome.tabs.query({

            active: true,

            currentWindow: true

        });


    return tabs[0];

}


// ============================================================
// EXTRACT YOUTUBE VIDEO ID
// ============================================================

function getVideoId(url) {

    try {

        const parsedUrl =
            new URL(url);


        // Normal YouTube URL
        //
        // https://www.youtube.com/watch?v=ABC123

        if (
            parsedUrl.hostname.includes(
                "youtube.com"
            )
        ) {

            return parsedUrl
                .searchParams
                .get("v");

        }


        // Short YouTube URL
        //
        // https://youtu.be/ABC123

        if (
            parsedUrl.hostname ===
            "youtu.be"
        ) {

            return parsedUrl
                .pathname
                .substring(1);

        }


        return null;

    }

    catch (error) {

        console.error(
            "URL parsing error:",
            error
        );

        return null;

    }

}


// ============================================================
// DETECT VIDEO
// ============================================================

async function detectVideo() {

    try {

        const tab =
            await getCurrentTab();


        if (
            !tab ||
            !tab.url
        ) {

            currentVideoId = null;

            updateVideoStatus(
                "No active tab"
            );

            return null;

        }


        const videoId =
            getVideoId(
                tab.url
            );


        if (!videoId) {

            currentVideoId = null;

            updateVideoStatus(
                "Open a YouTube video"
            );

            return null;

        }


        currentVideoId =
            videoId;


        updateVideoStatus(
            `Video: ${videoId}`
        );


        console.log(
            "Current YouTube video:",
            videoId
        );


        return videoId;

    }

    catch (error) {

        console.error(
            "Video detection error:",
            error
        );

        return null;

    }

}


// ============================================================
// UPDATE VIDEO STATUS
// ============================================================

function updateVideoStatus(
    text
) {

    const status =
        document.getElementById(
            "video-status"
        );


    status.textContent =
        text;

}


// ============================================================
// ASK RAG BACKEND
// ============================================================

async function askRAG(
    videoId,
    question
) {

    console.log(
        "Sending to backend:",
        {
            videoId,
            question
        }
    );


    const response =
        await fetch(

            `${API_URL}/chat`,

            {

                method: "POST",

                headers: {

                    "Content-Type":
                        "application/json"

                },

                body: JSON.stringify({

                    video_id:
                        videoId,

                    question:
                        question

                })

            }

        );


    if (!response.ok) {

        const errorText =
            await response.text();


        throw new Error(
            errorText
        );

    }


    const result =
        await response.json();


    console.log(
        "Backend response:",
        result
    );


    return result;

}


// ============================================================
// ADD MESSAGE
// ============================================================

function addMessage(
    text,
    type
) {

    const container =
        document.getElementById(
            "chat-container"
        );


    const message =
        document.createElement(
            "div"
        );


    message.className =
        `message ${type}`;


    message.textContent =
        text;


    container.appendChild(
        message
    );


    container.scrollTop =
        container.scrollHeight;


    // IMPORTANT:
    // Return the HTML element
    // so we can later update it.

    return message;

}


// ============================================================
// CHAT FORM
// ============================================================

document
    .getElementById("chat-form")
    .addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();


            const input =
                document.getElementById(
                    "question"
                );


            const sendButton =
                document.getElementById(
                    "send-button"
                );


            const question =
                input.value.trim();


            // ------------------------------------------------
            // Empty question
            // ------------------------------------------------

            if (!question) {

                return;

            }


            // ------------------------------------------------
            // Detect current video
            // ------------------------------------------------

            const videoId =
                await detectVideo();


            if (!videoId) {

                addMessage(

                    "Please open a YouTube video first.",

                    "ai"

                );

                return;

            }


            // ------------------------------------------------
            // Show user message
            // ------------------------------------------------

            addMessage(
                question,
                "user"
            );


            // Clear input

            input.value = "";


            // Disable button

            sendButton.disabled =
                true;


            // ------------------------------------------------
            // Loading message
            // ------------------------------------------------

            const loadingMessage =
                addMessage(
                    "Thinking...",
                    "ai"
                );


            try {

                // ------------------------------------------------
                // Call backend
                // ------------------------------------------------

                const result =
                    await askRAG(
                        videoId,
                        question
                    );


                console.log(
                    "Answer:",
                    result.answer
                );


                // ------------------------------------------------
                // IMPORTANT:
                //
                // DO NOT DO:
                //
                // loadingMessage.textContent = result;
                //
                // That creates:
                //
                // [object Object]
                //
                // We specifically use:
                //
                // result.answer
                // ------------------------------------------------

                if (
                    result &&
                    typeof result.answer ===
                        "string"
                ) {

                    loadingMessage.textContent =
                        result.answer;

                }

                else {

                    loadingMessage.textContent =
                        "The backend returned an invalid response.";

                }


            }

            catch (error) {

                console.error(
                    "RAG error:",
                    error
                );


                loadingMessage.textContent =
                    "❌ Could not connect to the RAG backend.";

            }


            finally {

                sendButton.disabled =
                    false;

                input.focus();

            }

        }
    );


// ============================================================
// INITIALIZE
// ============================================================

async function initialize() {

    console.log(
        "YouTube RAG extension initialized"
    );


    await detectVideo();

}


initialize();