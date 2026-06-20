(function () {
    function renderCompletionMessage(container, data) {
        const messageList = document.createElement("ul");
        const messageItem = document.createElement("li");
        const reloadButton = document.createElement("button");

        messageList.className = "messages";
        messageItem.className = data.successful ? "success" : "error";
        messageItem.textContent = data.successful
            ? container.dataset.successMessage
            : container.dataset.failureMessage;

        reloadButton.type = "button";
        reloadButton.textContent = "Reload";
        reloadButton.addEventListener("click", function () {
            window.location.reload();
        });

        messageItem.appendChild(document.createTextNode(" "));
        messageItem.appendChild(reloadButton);
        messageList.appendChild(messageItem);
        container.replaceChildren(messageList);
    }

    function pollTaskStatus(container) {
        const statusUrl = container.dataset.statusUrl;
        const pollInterval = Number(container.dataset.pollInterval || 1000);

        if (!statusUrl) {
            return;
        }

        fetch(statusUrl, {
            headers: {
                "Accept": "application/json",
            },
            credentials: "same-origin",
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Could not load task status.");
                }
                return response.json();
            })
            .then(function (data) {
                if (data.ready) {
                    renderCompletionMessage(container, data);
                    return;
                }

                window.setTimeout(function () {
                    pollTaskStatus(container);
                }, pollInterval);
            })
            .catch(function () {
                container.textContent = "Could not check task status. Reload the page to try again.";
            });
    }

    function startPolling() {
        document.querySelectorAll("[data-celery-task-status]").forEach(pollTaskStatus);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", startPolling);
    } else {
        startPolling();
    }
})();
