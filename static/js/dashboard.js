// Get the Sidebar
var mySidebar = document.getElementById("mySidebar");

// Get the DIV with overlay effect
var overlayBg = document.getElementById("myOverlay");
var mobileSidebarQuery = window.matchMedia("(max-width: 992px)");

function isMobileSidebarViewport() {
    return mobileSidebarQuery.matches;
}

function setSidebarState(isOpen) {
    if (!mySidebar || !overlayBg) {
        return;
    }

    if (!isMobileSidebarViewport()) {
        mySidebar.classList.remove("is-open");
        overlayBg.classList.remove("is-open");
        return;
    }

    mySidebar.classList.toggle("is-open", isOpen);
    overlayBg.classList.toggle("is-open", isOpen);
}

// Toggle between showing and hiding the sidebar, and add overlay effect
function w3_open() {
    if (!mySidebar || !overlayBg || !isMobileSidebarViewport()) {
        return;
    }

    setSidebarState(!mySidebar.classList.contains("is-open"));
}

// Close the sidebar with the close button
function w3_close() {
    setSidebarState(false);
}

// Script to highlight the active menu link
document.addEventListener('DOMContentLoaded', function () {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('#mySidebar .w3-bar-block a.w3-bar-item');

    let bestMatch = null;
    let longestMatchLength = 0;

    navLinks.forEach(link => {
        // Ensure the link has a href and it's not just '#'
        if (link.href && link.getAttribute('href') !== '#') {
            const linkPath = new URL(link.href).pathname;

            // Check if current path starts with the link's path and find the longest match
            if (currentPath.startsWith(linkPath) && linkPath.length > longestMatchLength) {
                longestMatchLength = linkPath.length;
                bestMatch = link;
            }
        }
    });

    // Add 'w3-blue' to the best matching link
    if (bestMatch) {
        bestMatch.classList.add('w3-blue');
    }

    if (isMobileSidebarViewport()) {
        setSidebarState(false);
    }
});

window.addEventListener("resize", function () {
    if (!isMobileSidebarViewport()) {
        setSidebarState(false);
    }
});
