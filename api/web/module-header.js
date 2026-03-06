        (function () {
            const headerBar = document.getElementById("moduleHeaderBar");
            if (!headerBar) return;

            const sectionTitles = new Map();
            document.querySelectorAll(".content-area > .section").forEach((section) => {
                const title = section.querySelector(":scope > .section-title");
                if (title) sectionTitles.set(section.id, title);
            });

            let currentTitle = null;

            function moveActiveTitleToHeader() {
                const activeSection = document.querySelector(".content-area > .section.active");
                if (!activeSection) return;
                const nextTitle = sectionTitles.get(activeSection.id);
                if (!nextTitle || nextTitle === currentTitle) return;

                if (currentTitle) {
                    const prevSection = document.getElementById(currentTitle.dataset.originalSection);
                    if (prevSection && !prevSection.contains(currentTitle)) {
                        prevSection.insertAdjacentElement("afterbegin", currentTitle);
                    }
                }

                if (!nextTitle.dataset.originalSection) {
                    nextTitle.dataset.originalSection = activeSection.id;
                }

                headerBar.appendChild(nextTitle);
                currentTitle = nextTitle;
            }

            const originalTabHandler = document.querySelectorAll(".nav-tab[data-section]");
            originalTabHandler.forEach((tab) => {
                tab.addEventListener("click", () => {
                    window.requestAnimationFrame(moveActiveTitleToHeader);
                });
            });

            moveActiveTitleToHeader();
        })();
