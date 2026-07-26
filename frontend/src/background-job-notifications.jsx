import React, { useEffect, useMemo, useRef } from "react";
import ReactDOM from "react-dom/client";
import { Anchor, MantineProvider } from "@mantine/core";
import { Notifications, notifications } from "@mantine/notifications";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";

const POLL_INTERVAL_MS = 3000;
const STORAGE_PREFIX = "missourai.backgroundJobNotification";

function getConfig() {
    const el = document.getElementById("background-job-notifications-config");
    return el ? JSON.parse(el.textContent) : {};
}

function notificationKey(job, state) {
    return `${STORAGE_PREFIX}.${job.id}.${state}`;
}

function wasShown(job, state) {
    return window.localStorage.getItem(notificationKey(job, state)) === "1";
}

function markShown(job, state) {
    window.localStorage.setItem(notificationKey(job, state), "1");
}

function jobHref(job) {
    if (!job.transcript_url) {
        return null;
    }
    return new URL(job.transcript_url, window.location.origin).toString();
}

function showJobNotification(job) {
    const isActive = !job.ready;
    const state = isActive ? "active" : job.successful ? "successful" : "failed";
    if (wasShown(job, state)) {
        return;
    }

    if (isActive) {
        notifications.show({
            id: `background-job-${job.id}-active`,
            title: "Background job queued",
            message: `${job.label} is running.`,
            color: "blue",
            autoClose: 5000,
        });
        markShown(job, state);
        return;
    }

    const href = jobHref(job);
    const message = job.failed
        ? `${job.label} failed. ${job.error_message || "Please contact support with this job id."} Job #${job.id}`
        : `${job.label} is complete.`;

    notifications.show({
        id: `background-job-${job.id}-${state}`,
        title: job.failed ? "Background job failed" : "Background job complete",
        message: (
            <span>
                {message}
                {href && (
                    <>
                        {" "}
                        <Anchor href={href}>View transcript</Anchor>
                    </>
                )}
            </span>
        ),
        color: job.failed ? "red" : "green",
        autoClose: job.failed ? false : 10000,
    });
    markShown(job, state);
}

function BackgroundJobNotifications() {
    const config = useMemo(getConfig, []);
    const isPolling = useRef(false);

    useEffect(() => {
        let cancelled = false;
        let timeoutId;

        async function poll() {
            if (!config.apiUrl || isPolling.current) {
                timeoutId = window.setTimeout(poll, POLL_INTERVAL_MS);
                return;
            }

            isPolling.current = true;
            try {
                const response = await fetch(config.apiUrl, {
                    headers: {
                        "Accept": "application/json",
                    },
                    credentials: "include",
                });
                if (!response.ok) {
                    return;
                }

                const jobs = await response.json();
                if (!cancelled) {
                    jobs.forEach((job) => {
                        try {
                            showJobNotification(job);
                        } catch (error) {
                            console.error("Could not show background job notification", error, job);
                        }
                    });
                }
            } finally {
                isPolling.current = false;
                if (!cancelled) {
                    timeoutId = window.setTimeout(poll, POLL_INTERVAL_MS);
                }
            }
        }

        timeoutId = window.setTimeout(poll, 250);

        return () => {
            cancelled = true;
            window.clearTimeout(timeoutId);
        };
    }, [config.apiUrl]);

    return (
        <MantineProvider>
            <Notifications position="top-right" mt={80} />
        </MantineProvider>
    );
}

const mount = document.getElementById("background-job-notifications-root");
if (mount) {
    ReactDOM.createRoot(mount).render(<BackgroundJobNotifications />);
}
