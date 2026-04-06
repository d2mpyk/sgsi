(function () {
    const controlsDataNode = document.getElementById("iso-controls-data");
    if (!controlsDataNode) return;

    const controls = JSON.parse(controlsDataNode.textContent || "[]");
    const controlsByCode = new Map(controls.map(item => [item.control, item]));

    function normalizeTerm(value) {
        return (value || "").toString().trim().toLowerCase();
    }

    function extractControlCode(value) {
        if (!value) return "";
        const match = value.toUpperCase().match(/A\.[5-8]\.\d+/);
        return match ? match[0] : "";
    }

    function setupTypeahead(root) {
        const input = root.querySelector("[data-iso-visible]");
        const hidden = root.querySelector("[data-iso-hidden]");
        const menu = root.querySelector("[data-iso-menu]");
        if (!input || !hidden || !menu) return;

        let activeIndex = -1;
        let currentItems = [];

        function getDisplayText(item) {
            return `${item.control} - ${item.nombre}`;
        }

        function selectItem(item) {
            input.value = getDisplayText(item);
            hidden.value = item.control;
            menu.style.display = "none";
            activeIndex = -1;
        }

        function resolveFromInput() {
            const raw = input.value || "";
            const extracted = extractControlCode(raw);
            if (extracted && controlsByCode.has(extracted)) {
                return controlsByCode.get(extracted);
            }
            const normalized = normalizeTerm(raw);
            return controls.find(item =>
                normalizeTerm(item.control) === normalized ||
                normalizeTerm(item.nombre) === normalized ||
                normalizeTerm(getDisplayText(item)) === normalized
            ) || null;
        }

        function renderMenu(items) {
            currentItems = items;
            menu.innerHTML = "";

            if (!currentItems.length) {
                menu.innerHTML = '<div class="audit-typeahead-empty">Sin coincidencias</div>';
                menu.style.display = "block";
                return;
            }

            currentItems.forEach((item, index) => {
                const option = document.createElement("button");
                option.type = "button";
                option.className = "audit-typeahead-option";
                option.dataset.index = String(index);
                option.innerHTML = `
                    <span class="audit-typeahead-code">${item.control}</span>
                    <span class="audit-typeahead-name">${item.nombre}</span>
                    <span class="audit-typeahead-theme">${item.tema}</span>
                `;
                option.addEventListener("mousedown", (event) => {
                    event.preventDefault();
                    selectItem(item);
                });
                menu.appendChild(option);
            });

            menu.style.display = "block";
        }

        function refreshItems() {
            const term = normalizeTerm(input.value);
            if (!term) {
                renderMenu(controls);
                return;
            }
            const filtered = controls.filter(item =>
                normalizeTerm(item.control).includes(term) ||
                normalizeTerm(item.nombre).includes(term) ||
                normalizeTerm(item.tema).includes(term)
            );
            renderMenu(filtered);
        }

        function setActiveItem(index) {
            const options = menu.querySelectorAll(".audit-typeahead-option");
            options.forEach(option => option.classList.remove("active"));
            if (index >= 0 && index < options.length) {
                options[index].classList.add("active");
                options[index].scrollIntoView({ block: "nearest" });
            }
        }

        if (hidden.value && controlsByCode.has(hidden.value)) {
            input.value = getDisplayText(controlsByCode.get(hidden.value));
        }

        input.addEventListener("focus", refreshItems);
        input.addEventListener("input", () => {
            const resolved = resolveFromInput();
            hidden.value = resolved ? resolved.control : "";
            activeIndex = -1;
            refreshItems();
        });

        input.addEventListener("keydown", (event) => {
            if (menu.style.display !== "block") return;
            if (event.key === "ArrowDown") {
                event.preventDefault();
                activeIndex = Math.min(activeIndex + 1, currentItems.length - 1);
                setActiveItem(activeIndex);
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                activeIndex = Math.max(activeIndex - 1, 0);
                setActiveItem(activeIndex);
            } else if (event.key === "Enter") {
                if (activeIndex >= 0 && currentItems[activeIndex]) {
                    event.preventDefault();
                    selectItem(currentItems[activeIndex]);
                } else {
                    const resolved = resolveFromInput();
                    if (resolved) {
                        event.preventDefault();
                        selectItem(resolved);
                    }
                }
            } else if (event.key === "Escape") {
                menu.style.display = "none";
            }
        });

        input.addEventListener("blur", () => {
            const resolved = resolveFromInput();
            hidden.value = resolved ? resolved.control : "";
            if (resolved) {
                input.value = getDisplayText(resolved);
            }
        });

        document.addEventListener("mousedown", (event) => {
            if (root.contains(event.target)) return;
            menu.style.display = "none";
        });

        const parentForm = root.closest("form");
        if (parentForm) {
            parentForm.addEventListener("submit", (event) => {
                const required = root.dataset.required === "true";
                const resolved = resolveFromInput();
                hidden.value = resolved ? resolved.control : "";

                if (required && !hidden.value) {
                    event.preventDefault();
                    input.focus();
                    input.setCustomValidity("Seleccione un control ISO válido de la lista.");
                    input.reportValidity();
                    return;
                }
                input.setCustomValidity("");
            });
        }
    }

    document.querySelectorAll("[data-iso-typeahead]").forEach(setupTypeahead);
})();
