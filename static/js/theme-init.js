(function () {
    try {
        var savedTheme = localStorage.getItem("sgsi-theme");
        var preferredTheme = savedTheme
            || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
        document.documentElement.setAttribute("data-theme", preferredTheme);
    } catch (error) {
        document.documentElement.setAttribute("data-theme", "light");
    }
})();
