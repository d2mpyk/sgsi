// Obtener la ruta base por si la app corre en un subdirectorio (ej: /app)
const BASE_PATH = document.body.getAttribute("data-root-path") || "";
const API_PREFIX = document.body.getAttribute("data-api-prefix") || "/api/v1";

// --- Lógica de Pestañas ---
function openTab(evt, tabName) {
    var i, x, tablinks;
    x = document.getElementsByClassName("city");
    for (i = 0; i < x.length; i++) {
        x[i].style.display = "none";
    }
    tablinks = document.getElementsByClassName("tablink");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" w3-red", "");
        tablinks[i].className = tablinks[i].className.replace(" documents-tab-active", "");
    }
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.className += " w3-red documents-tab-active";

    if (tabName === "AdminPanel") {
        loadAuditReportPreview();
    }
}

function loadAuditReportPreview() {
    const iframe = document.getElementById("auditReportPreviewFrame");
    const emptyState = document.getElementById("auditReportPreviewEmpty");

    if (!iframe) return;

    if (!iframe.dataset.loaded) {
        iframe.src = iframe.dataset.src;
        iframe.dataset.loaded = "true";
    }

    iframe.style.display = "block";
    if (emptyState) {
        emptyState.style.display = "none";
    }
}

// --- Marcar como Leído ---
async function markAsRead(docId, btnElement) {
    if (!confirm("¿Confirmas que has leído y comprendido este documento?")) return;

    const originalText = btnElement.innerHTML;
    btnElement.disabled = true;
    btnElement.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Procesando';

    try {
        const response = await fetch(`${BASE_PATH}${API_PREFIX}/documents/${docId}/read`, {
            method: 'POST'
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.href = url;
            a.download = `Certificado_Lectura_${docId}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();

            const parent = btnElement.parentElement;
            btnElement.remove();
            const badge = document.createElement("span");
            badge.className = "w3-tag w3-round-large documents-read-tag";
            badge.innerHTML = '<i class="fa fa-check"></i> Leído (Certificado Descargado)';
            parent.appendChild(badge);
        } else {
            const err = await response.json();

            if (
                response.status === 409 &&
                err.action === "download_required" &&
                err.download_url
            ) {
                alert(err.detail);
                window.open(err.download_url, "_blank", "noopener");
            } else {
                alert("Error: " + err.detail);
            }

            btnElement.disabled = false;
            btnElement.innerHTML = originalText;
        }
    } catch (error) {
        console.error(error);
        alert("Error de conexión");
        btnElement.disabled = false;
        btnElement.innerHTML = originalText;
    }
}

document.addEventListener("DOMContentLoaded", async function () {
    const ctx = document.getElementById('complianceChart');
    if (ctx) {
        try {
            const response = await fetch(`${BASE_PATH}${API_PREFIX}/documents/stats`);
            const data = await response.json();

            const labels = data.map(item => item.code ? `${item.code} ${item.title}` : item.title);
            const percentages = data.map(item => item.compliance_percentage);
            const colors = percentages.map(p => p < 50 ? 'rgba(184, 73, 73, 0.78)' : (p < 80 ? 'rgba(58, 108, 158, 0.72)' : 'rgba(43, 92, 138, 0.82)'));

            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '% de Cumplimiento',
                        data: percentages,
                        backgroundColor: colors,
                        borderColor: colors.map(c => c.replace('0.7', '1')),
                        borderWidth: 1
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: {
                                color: '#334155',
                                font: {
                                    family: 'DM Sans'
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            max: 100,
                            ticks: {
                                color: '#5f7186'
                            },
                            grid: {
                                color: 'rgba(51, 65, 85, 0.08)'
                            }
                        },
                        y: {
                            ticks: {
                                color: '#334155',
                                font: {
                                    family: 'DM Sans'
                                }
                            },
                            grid: {
                                display: false
                            }
                        }
                    }
                }
            });

        } catch (error) {
            console.error("Error cargando estadísticas:", error);
        }
    }

    const uploadForm = document.getElementById("uploadForm");
    if (uploadForm) {
        uploadForm.addEventListener("submit", function (e) {
            const fileInput = uploadForm.querySelector("input[name='file']");
            const maxSize = 21 * 1024 * 1024;

            if (fileInput && fileInput.files.length > 0) {
                if (fileInput.files[0].size > maxSize) {
                    e.preventDefault();
                    alert("El archivo excede el tamaño máximo permitido de 21MB.");
                }
            }
        });
    }

    const firstTab = document.querySelector(".tablink");
    if (firstTab) {
        firstTab.classList.add("w3-red", "documents-tab-active");
    }

    const previewButton = document.getElementById("previewAuditReportButton");
    if (previewButton) {
        previewButton.addEventListener("click", function () {
            loadAuditReportPreview();
            const iframe = document.getElementById("auditReportPreviewFrame");
            if (iframe) {
                iframe.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        });
    }
});
