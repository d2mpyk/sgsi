document.addEventListener("DOMContentLoaded", function () {
    const storageKey = "sgsi-theme";
    const root = document.documentElement;
    const toggleButtons = document.querySelectorAll("[data-theme-toggle]");

    function getCurrentTheme() {
        return root.getAttribute("data-theme") || "light";
    }

    function updateToggleButtons(theme) {
        const isDark = theme === "dark";

        toggleButtons.forEach((button) => {
            const icon = button.querySelector(".theme-toggle-icon");
            const label = button.querySelector(".theme-toggle-label");

            button.setAttribute(
                "aria-label",
                isDark ? "Cambiar a modo claro" : "Cambiar a modo oscuro"
            );

            if (icon) {
                icon.className = isDark
                    ? "fa fa-sun-o theme-toggle-icon"
                    : "fa fa-moon-o theme-toggle-icon";
            }

            if (label) {
                label.textContent = isDark ? "Modo claro" : "Modo oscuro";
            }
        });
    }

    function applyTheme(theme) {
        root.setAttribute("data-theme", theme);
        localStorage.setItem(storageKey, theme);
        updateToggleButtons(theme);
    }

    updateToggleButtons(getCurrentTheme());

    toggleButtons.forEach((button) => {
        button.addEventListener("click", function () {
            const nextTheme = getCurrentTheme() === "dark" ? "light" : "dark";
            applyTheme(nextTheme);
        });
    });
});
