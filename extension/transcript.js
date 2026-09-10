const PREFERRED_LANGUAGES = [
    "en",
    "en-US",
    "en-GB",
    "hi",
    "es",
    "fr",
    "de",
    "ja",
    "pt",
    "ko",
];

function decodeHtml(text) {
    const textarea = document.createElement("textarea");
    textarea.innerHTML = text;
    return textarea.value;
}

function pickCaptionTrack(tracks) {
    for (const code of PREFERRED_LANGUAGES) {
        const match = tracks.find(
            (track) => track.languageCode === code
        );
        if (match) {
            return match;
        }
    }

    return tracks[0];
}

function parseTranscriptXml(xmlText) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(xmlText, "text/xml");
    const nodes = doc.querySelectorAll("text");

    return Array.from(nodes).map((node) => ({
        text: decodeHtml(node.textContent || "").trim(),
        start: parseFloat(node.getAttribute("start") || "0"),
        duration: parseFloat(node.getAttribute("dur") || "0"),
    })).filter((segment) => segment.text.length > 0);
}

async function fetchYouTubeTranscript(videoId) {
    const response = await fetch(
        `https://www.youtube.com/watch?v=${videoId}`,
        {
            credentials: "include",
        }
    );

    if (!response.ok) {
        throw new Error("Could not load the YouTube video page.");
    }

    const html = await response.text();
    const captionsMarker = '"captions":';

    if (!html.includes(captionsMarker)) {
        throw new Error(
            "No transcript is available for this video."
        );
    }

    const captionsPart = html
        .split(captionsMarker)[1]
        .split(',"videoDetails"')[0]
        .replace(/\n/g, "");

    let captionsJson;
    try {
        captionsJson = JSON.parse(captionsPart);
    } catch {
        throw new Error(
            "Could not read caption data for this video."
        );
    }

    const tracks =
        captionsJson?.playerCaptionsTracklistRenderer?.captionTracks;

    if (!tracks?.length) {
        throw new Error(
            "No transcript is available for this video."
        );
    }

    const track = pickCaptionTrack(tracks);
    const transcriptResponse = await fetch(track.baseUrl, {
        credentials: "include",
    });

    if (!transcriptResponse.ok) {
        throw new Error(
            "Could not download the transcript for this video."
        );
    }

    const segments = parseTranscriptXml(
        await transcriptResponse.text()
    );

    if (!segments.length) {
        throw new Error(
            "The transcript for this video is empty."
        );
    }

    return {
        language: track.languageCode,
        languageName: track.name?.simpleText || track.languageCode,
        isGenerated: track.kind === "asr",
        segments,
    };
}
