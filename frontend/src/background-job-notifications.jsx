import React, { useEffect, useMemo, useRef } from "react";
import ReactDOM from "react-dom/client";
import { Anchor, MantineProvider } from "@mantine/core";
import { Notifications, notifications } from "@mantine/notifications";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";

const POLL_INTERVAL_MS = 3000;
const STORAGE_PREFIX = "missourai.backgroundJobNotification";
const RECENT_COMPLETION_MS = 15 * 60 * 1000;
const shownInMemory = new Set();
const scheduled = new Set();
const activeMessages = new Map();

function getConfig() {
    const el = document.getElementById("background-job-notifications-config");
    return el ? JSON.parse(el.textContent) : {};
}

function notificationKey(job, state) {
    return `${STORAGE_PREFIX}.${job.task_id || `${job.id}.${job.created_at}`}.${state}`;
}

function wasShown(job, state) {
    const key = notificationKey(job, state);
    try {
        return shownInMemory.has(key) || window.localStorage.getItem(key) === "1";
    } catch {
        return shownInMemory.has(key);
    }
}

function markShown(job, state) {
    const key = notificationKey(job, state);
    shownInMemory.add(key);
    try {
        window.localStorage.setItem(key, "1");
    } catch {
        // Restricted browser storage must not prevent a notification.
    }
}

function jobHref(job) {
    if (!job.transcript_url) {
        return null;
    }
    return new URL(job.transcript_url, window.location.origin).toString();
}

function JobNotificationMessage({ job, state, message, href }) {
    // Mark as seen only when the queued notification actually mounts.
    useEffect(() => { markShown(job, state); }, [job, state]);
    return <span>{message}{href && <> <Anchor href={href}>View transcript</Anchor></>}</span>;
}

function showJobNotification(job) {
    const isActive = !job.ready;
    const state = isActive ? "active" : job.successful ? "successful" : "failed";
    const activeId = `background-job-${job.id}-active`;

    if (isActive) {
        const progress = job.progress;
        const indices = progress?.active_chunks || [];
        const message = indices.length
            ? `Processing ${indices.length === 1 ? "chunk" : "chunks"} ${indices.join(", ")} of ${progress.total_chunks}.`
            : progress?.started_chunks?.length
                ? "Finishing transcription processing..."
                : "Waiting for the worker or preparing audio...";
        if (activeMessages.get(activeId) === message) return;
        const data = {
            id: activeId,
            title: job.label,
            message,
            color: "blue",
            loading: true,
            withCloseButton: false,
            autoClose: false,
        };
        if (activeMessages.has(activeId)) notifications.update(data);
        else notifications.show(data);
        activeMessages.set(activeId, message);
        markShown(job, state);
        return;
    }

    notifications.hide(activeId);
    activeMessages.delete(activeId);
    const key = notificationKey(job, state);
    if (wasShown(job, state) || scheduled.has(key)) return;
    const timestamp = Date.parse(job.notification_at || job.created_at);
    // Do not flood the queue with historical jobs on every new browser/session.
    if (!wasShown(job, "active") && Number.isFinite(timestamp) && Date.now() - timestamp > RECENT_COMPLETION_MS) return;

    const href = jobHref(job);
    const message = job.failed && job.transcript_delivered
        ? `${job.label}: the transcript is available, but follow-up processing failed. Job #${job.id}`
        : job.failed
        ? `${job.label} failed. ${job.error_message || "Please contact support with this job id."} Job #${job.id}`
        : `${job.label} is complete.`;

    scheduled.add(key);
    notifications.show({
        id: `background-job-${job.id}-${state}`,
        title: job.failed ? "Background job failed" : "Background job complete",
        message: <JobNotificationMessage job={job} state={state} message={message} href={href} />,
        color: job.failed ? "red" : "green",
        autoClose: job.failed ? false : 10000,
    });
}

export function BackgroundJobNotifications() {
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
            } catch (error) {
                if (!cancelled) console.error("Could not poll background jobs; retrying", error);
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
