const complaint = document.getElementById("complaint");
const status = document.getElementById("voiceStatus");

const start = document.getElementById("startVoice");
const stop = document.getElementById("stopVoice");

let mediaRecorder = null;
let audioChunks = [];
let microphoneStream = null;

if (start && stop) {

    start.onclick = async () => {

        try {

            microphoneStream = await navigator.mediaDevices.getUserMedia({
                audio: true
            });

            audioChunks = [];

            let options = {};

            if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
                options.mimeType = "audio/webm;codecs=opus";
            }

            mediaRecorder = new MediaRecorder(microphoneStream, options);

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = async () => {

                status.textContent = "Sending recording to Gnani Prisma...";

                const audioBlob = new Blob(audioChunks, {
                    type: mediaRecorder.mimeType
                });

                const formData = new FormData();

                const extension = audioBlob.type.includes("ogg") ? "ogg" : "webm";

                formData.append("audio", audioBlob, `complaint.${extension}`);

                try {

                    const response = await fetch("/transcribe", {
                        method: "POST",
                        body: formData
                    });

                    const result = await response.json();

                    if (!response.ok) {
                        throw new Error(result.error || "Transcription failed");
                    }

                    if (result.transcript) {

                        complaint.value = (
                            complaint.value + " " + result.transcript
                        ).trim();

                        status.textContent =
                            "Transcription successful! Language detected: " +
                            result.detected_language;

                    } else {

                        status.textContent = "No speech detected. Please try again.";

                    }

                } catch (error) {

                    status.textContent = "Error: " + error.message;

                } finally {

                    microphoneStream.getTracks().forEach(track => track.stop());

                }

            };

            mediaRecorder.start();

            status.textContent = "Listening... Speak your complaint.";

            start.disabled = true;
            stop.disabled = false;

        } catch (error) {

            status.textContent = "Microphone error: " + error.message;

        }

    };

    stop.onclick = () => {

        if (mediaRecorder && mediaRecorder.state === "recording") {

            mediaRecorder.stop();

            status.textContent = "Recording stopped. Processing...";

            start.disabled = false;
            stop.disabled = true;

        }

    };

    stop.disabled = true;
}


// Get user's location
const locBtn = document.getElementById("getLocation");

if (locBtn) {

    locBtn.onclick = () => {

        const s = document.getElementById("locStatus");

        if (!navigator.geolocation) {
            s.textContent = "Geolocation is not supported.";
            return;
        }

        s.textContent = "Getting location...";

        navigator.geolocation.getCurrentPosition(

            pos => {

                document.getElementById("latitude").value =
                    pos.coords.latitude;

                document.getElementById("longitude").value =
                    pos.coords.longitude;

                s.textContent = "Location attached successfully.";

            },

            () => {

                s.textContent =
                    "Could not get location. Enter the area manually.";

            }

        );

    };

}
