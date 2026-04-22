(() => {
    const form = document.getElementById("lmsQuizForm");
    if (!form) return;

    const submitUrl = form.dataset.submitUrl;
    const postsUrl = form.dataset.postsUrl;
    const resultNode = document.getElementById("quizResult");
    if (!submitUrl || !resultNode) return;

    function openInBackground(url) {
        if (!url) return;
        const newTab = window.open(url, "_blank", "noopener,noreferrer");
        if (newTab) {
            newTab.blur();
            window.focus();
            return;
        }
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.focus();
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const answers = [];
        const inputs = form.querySelectorAll("input[type='radio']:checked");
        for (const input of inputs) {
            const questionId = Number(input.name.replace("question_", ""));
            answers.push({
                question_id: questionId,
                option_id: Number(input.value),
            });
        }

        try {
            const response = await fetch(submitUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ answers }),
            });
            const payload = await response.json();
            if (!response.ok) {
                resultNode.textContent = payload.detail || "No fue posible registrar el intento.";
                return;
            }

            resultNode.textContent = `Intento #${payload.attempt_number}: ${payload.score_percentage}% (${payload.is_passed ? "Aprobado" : "No aprobado"})`;
            if (payload.certificate_url) {
                openInBackground(payload.certificate_url);
            }
            if (payload.is_passed && postsUrl) {
                setTimeout(() => {
                    window.location.assign(postsUrl);
                }, 400);
            }
        } catch (_error) {
            resultNode.textContent = "Error de conexión al enviar la evaluación.";
        }
    });
})();
