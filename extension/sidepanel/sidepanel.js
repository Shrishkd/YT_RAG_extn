const DEFAULT_API_URL = "http://127.0.0.1:8000";

let currentVideoId = null;
let apiUrl = DEFAULT_API_URL;
let isBusy = false;

const elements = {
    chatForm: document.getElementById("chat-form"),
    chatContainer: document.getElementById("chat-container"),
    questionInput: document.getElementById("question"),
    sendButton: document.getElementById("send-button"),
    videoStatus: document.getElementById("video-status"),
    videoStatusText: document.getElementById("video-status-text"),
    suggestions: document.getElementById("suggestions"),
    settingsButton: document.getElementById("settings-button"),
    settingsDialog: document.getElementById("settings-dialog"),
    settingsForm: document.getElementById("settings-form"),
    apiUrlInput: document.getElementById("api-url"),
    cancelSettings: document.getElementById("cancel-settings"),
};

async function loadSettings() {
    const stored = await chrome.storage.sync.get(["apiUrl"]);
    apiUrl = (stored.apiUrl || DEFAULT_API_URL).replace(/\/$/, "");
    elements.apiUrlInput.value = apiUrl;
}

async function saveSettings(url) {
    apiUrl = url.replace(/\/$/, "");
    await chrome.storage.sync.set({ apiUrl });
}

function setVideoStatus(text, state = "default") {
    elements.videoStatus.className = `video-status ${state}`;
    elements.videoStatusText.textContent = text;
}

async function getCurrentTab() {
    const tabs = await chrome.tabs.query({
        active: true,
        currentWindow: true,
    });
    return tabs[0];
}

function getVideoId(url) {
    try {
        const parsedUrl = new URL(url);

        if (parsedUrl.hostname.includes("youtube.com")) {
            if (parsedUrl.pathname.startsWith("/shorts/")) {
                return parsedUrl.pathname.split("/")[2] || null;
            }
            return parsedUrl.searchParams.get("v");
        }

        if (parsedUrl.hostname === "youtu.be") {
            return parsedUrl.pathname.substring(1) || null;
        }

        return null;
    } catch {
        return null;
    }
}

async function apiRequest(path, options = {}) {
    const response = await fetch(`${apiUrl}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
    });

    let payload = null;
    const contentType = response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
        payload = await response.json();
    } else {
        payload = { detail: await response.text() };
    }

    if (!response.ok) {
        const detail =
            typeof payload.detail === "string"
                ? payload.detail
                : JSON.stringify(payload.detail || payload);
        throw new Error(detail || `Request failed (${response.status})`);
    }

    return payload;
}

async function checkBackendHealth() {
    try {
        await apiRequest("/");
        return true;
    } catch {
        return false;
    }
}

async function fetchVideoStatus(videoId) {
    return apiRequest(`/video/${videoId}/status`);
}

async function registerVideo(videoId) {
    return apiRequest("/video/register", {
        method: "POST",
        body: JSON.stringify({ video_id: videoId }),
    });
}

async function askRAG(videoId, question) {
    return apiRequest("/chat", {
        method: "POST",
        body: JSON.stringify({
            video_id: videoId,
            question,
        }),
    });
}

function addMessage(content, type = "ai") {
    const message = document.createElement("div");
    message.className = `message ${type}`;

    if (typeof content === "string") {
        message.textContent = content;
    } else {
        message.appendChild(content);
    }

    elements.chatContainer.appendChild(message);
    elements.chatContainer.scrollTop = elements.chatContainer.scrollHeight;
    return message;
}

function addLoadingMessage() {
    const wrapper = document.createElement("div");
    wrapper.className = "typing-dots";
    wrapper.innerHTML = "<span></span><span></span><span></span>";

    const message = addMessage(wrapper, "ai loading");
    message.prepend(document.createTextNode("Thinking "));
    return message;
}

function setInputEnabled(enabled) {
    elements.questionInput.disabled = !enabled;
    elements.sendButton.disabled = !enabled;
    isBusy = !enabled;
}

async function prepareVideo(videoId) {
    setVideoStatus("Checking transcript...", "loading");

    const status = await fetchVideoStatus(videoId);

    if (!status.transcript?.available) {
        setVideoStatus(
            status.transcript?.error || "No transcript for this video",
            "error"
        );
        elements.suggestions.hidden = true;
        return false;
    }

    if (status.indexed) {
        setVideoStatus("Ready — transcript indexed", "ready");
        elements.suggestions.hidden = false;
        return true;
    }

    setVideoStatus("Indexing transcript (first question may take longer)...", "loading");

    await registerVideo(videoId);
    setVideoStatus("Ready — transcript indexed", "ready");
    elements.suggestions.hidden = false;
    return true;
}

async function detectVideo() {
    try {
        const tab = await getCurrentTab();

        if (!tab?.url) {
            currentVideoId = null;
            setVideoStatus("No active tab", "warning");
            elements.suggestions.hidden = true;
            return null;
        }

        const videoId = getVideoId(tab.url);

        if (!videoId) {
            currentVideoId = null;
            setVideoStatus("Open a YouTube video to start", "warning");
            elements.suggestions.hidden = true;
            return null;
        }

        if (videoId === currentVideoId) {
            return videoId;
        }

        currentVideoId = videoId;
        setVideoStatus(`Video detected: ${videoId}`, "loading");

        const healthy = await checkBackendHealth();
        if (!healthy) {
            setVideoStatus("Backend unreachable — check Settings", "error");
            elements.suggestions.hidden = true;
            return videoId;
        }

        await prepareVideo(videoId);
        return videoId;
    } catch (error) {
        console.error("Video detection error:", error);
        setVideoStatus(error.message || "Failed to prepare video", "error");
        elements.suggestions.hidden = true;
        return currentVideoId;
    }
}

async function handleQuestion(question) {
    const trimmed = question.trim();
    if (!trimmed || isBusy) {
        return;
    }

    const videoId = await detectVideo();
    if (!videoId) {
        addMessage("Please open a YouTube video first.", "ai error");
        return;
    }

    addMessage(trimmed, "user");
    elements.questionInput.value = "";
    setInputEnabled(false);

    const loadingMessage = addLoadingMessage();

    try {
        const result = await askRAG(videoId, trimmed);

        if (result?.answer) {
            loadingMessage.className = "message ai";
            loadingMessage.textContent = result.answer;
        } else {
            loadingMessage.className = "message ai error";
            loadingMessage.textContent = "The backend returned an invalid response.";
        }
    } catch (error) {
        console.error("RAG error:", error);
        loadingMessage.className = "message ai error";
        loadingMessage.textContent = error.message || "Could not reach the RAG backend.";
    } finally {
        setInputEnabled(true);
        elements.questionInput.focus();
    }
}

elements.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await handleQuestion(elements.questionInput.value);
});

document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", async () => {
        await handleQuestion(chip.dataset.question || "");
    });
});

elements.settingsButton.addEventListener("click", () => {
    elements.apiUrlInput.value = apiUrl;
    elements.settingsDialog.showModal();
});

elements.cancelSettings.addEventListener("click", () => {
    elements.settingsDialog.close();
});

elements.settingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const nextUrl = elements.apiUrlInput.value.trim();
    if (!nextUrl) {
        return;
    }

    await saveSettings(nextUrl);
    elements.settingsDialog.close();

    if (currentVideoId) {
        await prepareVideo(currentVideoId);
    }
});

chrome.tabs.onActivated.addListener(() => {
    detectVideo();
});

chrome.tabs.onUpdated.addListener((_tabId, changeInfo) => {
    if (changeInfo.url) {
        detectVideo();
    }
});

async function initialize() {
    await loadSettings();

    const healthy = await checkBackendHealth();
    if (!healthy) {
        setVideoStatus("Backend offline — set API URL in Settings", "warning");
    }

    await detectVideo();
}

initialize();
