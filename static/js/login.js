document.addEventListener("DOMContentLoaded", function () {

    // Refactor: Leer configuración desde data-attribute del body
    const BASE_PATH = document.body.getAttribute("data-root-path") || "";

    // Función auxiliar para manejar expiración de sesión (401/403)
    function handleSessionExpiration(response) {
        if (response.status === 401 || response.status === 403) {
            alert("La sesión o el enlace han expirado. Serás redirigido al inicio.");
            window.location.href = `${BASE_PATH}/`;
            return true;
        }
        return false;
    }

    function setButtonLoading(button, loadingText) {
        if (!button) return () => {};
        const originalText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = `<strong>${loadingText}</strong>`;
        return function restore() {
            button.disabled = false;
            button.innerHTML = originalText;
        };
    }

    // JS LOGIN
    const formLogin = document.getElementById("loginForm");
    if (formLogin) {
        formLogin.addEventListener("submit", async function (e) {
            e.preventDefault();
            const username = formLogin.querySelector("input[name='username']").value;
            const password = formLogin.querySelector("input[name='password']").value;
            const submitBtn = formLogin.querySelector("button[type='submit']");
            const restoreButton = setButtonLoading(submitBtn, "Validando...");

            try {
                const formData = new URLSearchParams();
                formData.append('username', username);
                formData.append('password', password);

                const tokenResponse = await fetch(`${BASE_PATH}/api/v1/auth/token`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    body: formData
                });

                if (!tokenResponse.ok) {
                    const contentType = tokenResponse.headers.get("content-type");
                    if (contentType && contentType.includes("application/json")) {
                        const errorData = await tokenResponse.json();
                        console.error("Error del servidor:", errorData);
                    } else {
                        const errorText = await tokenResponse.text();
                        console.error("Error del servidor (No JSON):", errorText);
                    }
                    if (tokenResponse.status === 404) {
                        throw new Error("Ruta no encontrada (404). Verifica la configuración del Proxy.");
                    }
                    throw new Error("Credenciales inválidas o error del servidor (" + tokenResponse.status + ")");
                }

                await tokenResponse.json();

                window.location.href = `${BASE_PATH}/api/v1/dashboard/`;

            } catch (error) {
                alert("Error en autenticación: " + error.message);
            } finally {
                restoreButton();
            }
        });
    }

    // JS RECOVERY
    const formRecovery = document.getElementById("forgotPasswordForm");
    if (formRecovery) {
        formRecovery.addEventListener("submit", async function (e) {
            e.preventDefault();
            const email = formRecovery.querySelector("input[name='email']").value;
            const submitBtn = formRecovery.querySelector("button");
            const restoreButton = setButtonLoading(submitBtn, "Enviando...");

            try {
                const response = await fetch(`${BASE_PATH}/api/v1/users/forgot-password`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ email: email })
                });

                if (handleSessionExpiration(response)) return;

                const data = await response.json();

                if (response.ok) {
                    alert(data.message);
                    window.location.href = `${BASE_PATH}/`;
                } else {
                    alert("Error: " + (data.detail || "Ocurrió un error inesperado"));
                }

            } catch (error) {
                alert("Error de conexión: " + error.message);
            } finally {
                restoreButton();
            }
        });
    }

    const formResend = document.getElementById("resendVerificationForm");
    if (formResend) {
        formResend.addEventListener("submit", async function (e) {
            e.preventDefault();
            const email = formResend.querySelector("input[name='email']").value;
            const submitBtn = formResend.querySelector("button[type='submit']");
            const restoreButton = setButtonLoading(submitBtn, "Enviando...");

            try {
                const formData = new URLSearchParams();
                formData.append('email', email);

                const response = await fetch(`${BASE_PATH}/api/v1/users/resend-verification`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    body: formData
                });

                if (response.redirected) {
                    window.location.href = response.url;
                } else if (response.ok) {
                    window.location.href = `${BASE_PATH}/`;
                }
            } catch (error) {
                alert("Error de conexión: " + error.message);
            } finally {
                restoreButton();
            }
        });
    }

    // JS RESET
    const formReset = document.getElementById("resetPasswordForm");
    // Solo ejecutar lógica de reset si el formulario existe (Evita alertas en Login)
    if (formReset) {
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('token');
        const p1 = document.getElementById("new_password");
        const p2 = document.getElementById("confirm_password");
        const errorMsg = document.getElementById("matchError");

        if (!token) {
            alert("Token no encontrado o enlace inválido. Por favor solicita un nuevo enlace.");
            const inputs = formReset.querySelectorAll("input, button");
            inputs.forEach(input => input.disabled = true);
            return;
        }

        function syncPasswordMatchState() {
            if (!p1 || !p2 || !errorMsg) return true;
            const matches = p1.value === p2.value || !p2.value;
            errorMsg.style.display = matches ? "none" : "block";
            return matches;
        }

        if (p1 && p2) {
            p1.addEventListener("input", syncPasswordMatchState);
            p2.addEventListener("input", syncPasswordMatchState);
        }

        formReset.addEventListener("submit", async function (e) {
            e.preventDefault();
            const newPassword = p1.value;
            const confirmPassword = p2.value;
            const submitBtn = formReset.querySelector("button");

            if (!syncPasswordMatchState() || newPassword !== confirmPassword) {
                return;
            }

            const restoreButton = setButtonLoading(submitBtn, "Actualizando...");

            try {
                const response = await fetch(`${BASE_PATH}/api/v1/users/reset-password/${token}`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ new_password: newPassword })
                });

                if (handleSessionExpiration(response)) return;

                const data = await response.json();

                if (response.ok) {
                    alert(data.message);
                    window.location.href = `${BASE_PATH}/`;
                } else {
                    alert("Error: " + (data.detail || "Ocurrió un error inesperado"));
                }

            } catch (error) {
                alert("Error de conexión: " + error.message);
            } finally {
                restoreButton();
            }
        });
    }

});
