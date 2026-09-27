import React from "react";
import { MantineProvider } from "@mantine/core";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const notificationSpies = vi.hoisted(() => ({
    show: vi.fn(),
    update: vi.fn(),
    hide: vi.fn(),
}));

vi.mock("@mantine/notifications", () => ({
    Notifications: () => null,
    notifications: notificationSpies,
}));

import { BackgroundJobNotifications } from "../src/background-job-notifications";

const activeJob = {
    id: 42,
    task_id: "task-42",
    label: "Committee hearing",
    ready: false,
    successful: false,
    failed: false,
    created_at: new Date().toISOString(),
    progress: {
        active_chunks: [2],
        started_chunks: [1, 2],
        total_chunks: 5,
    },
};

function setConfig() {
    const config = document.createElement("script");
    config.id = "background-job-notifications-config";
    config.type = "application/json";
    config.textContent = JSON.stringify({ apiUrl: "/api/background-jobs/" });
    document.body.append(config);
}

async function runNextPoll(milliseconds = 250) {
    await act(async () => {
        await vi.advanceTimersByTimeAsync(milliseconds);
    });
}

describe("BackgroundJobNotifications", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date("2026-09-26T12:00:00Z"));
        window.localStorage.clear();
        notificationSpies.show.mockClear();
        notificationSpies.update.mockClear();
        notificationSpies.hide.mockClear();
        setConfig();
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    test("shows active chunk progress and updates the existing toast", async () => {
        const changedJob = {
            ...activeJob,
            progress: { ...activeJob.progress, active_chunks: [3, 4] },
        };
        const fetchMock = vi.fn()
            .mockResolvedValueOnce({ ok: true, json: async () => [activeJob] })
            .mockResolvedValueOnce({ ok: true, json: async () => [changedJob] });
        vi.stubGlobal("fetch", fetchMock);

        render(<BackgroundJobNotifications />);
        await runNextPoll();

        expect(notificationSpies.show).toHaveBeenCalledWith(expect.objectContaining({
            id: "background-job-42-active",
            title: "Committee hearing",
            message: "Processing chunk 2 of 5.",
            loading: true,
            autoClose: false,
        }));

        await runNextPoll(3000);

        expect(notificationSpies.update).toHaveBeenCalledWith(expect.objectContaining({
            id: "background-job-42-active",
            message: "Processing chunks 3, 4 of 5.",
        }));
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    test("replaces an active toast with a linked completion toast", async () => {
        const runningJob = { ...activeJob, id: 43, task_id: "task-43" };
        const completeJob = {
            ...runningJob,
            ready: true,
            successful: true,
            transcript_url: "/transcripts/17/",
            notification_at: "2026-09-26T11:59:00Z",
        };
        vi.stubGlobal("fetch", vi.fn()
            .mockResolvedValueOnce({ ok: true, json: async () => [runningJob] })
            .mockResolvedValueOnce({ ok: true, json: async () => [completeJob] }));

        render(<BackgroundJobNotifications />);
        await runNextPoll();
        await runNextPoll(3000);

        expect(notificationSpies.hide).toHaveBeenCalledWith("background-job-43-active");
        const completion = notificationSpies.show.mock.calls[1][0];
        expect(completion).toEqual(expect.objectContaining({
            id: "background-job-43-successful",
            title: "Background job complete",
            color: "green",
            autoClose: 10000,
        }));

        render(<MantineProvider>{completion.message}</MantineProvider>);
        expect(screen.getByText("Committee hearing is complete.", { exact: false })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "View transcript" })).toHaveAttribute(
            "href",
            "http://localhost:3000/transcripts/17/",
        );
    });

    test("keeps failures open and explains a follow-up processing failure", async () => {
        const failedJob = {
            ...activeJob,
            ready: true,
            failed: true,
            transcript_delivered: true,
            transcript_url: "/transcripts/17/",
            notification_at: "2026-09-26T11:59:00Z",
        };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [failedJob] }));

        render(<BackgroundJobNotifications />);
        await runNextPoll();

        const failure = notificationSpies.show.mock.calls[0][0];
        expect(failure).toEqual(expect.objectContaining({
            id: "background-job-42-failed",
            title: "Background job failed",
            color: "red",
            autoClose: false,
        }));
        render(<MantineProvider>{failure.message}</MantineProvider>);
        expect(screen.getByText(/transcript is available, but follow-up processing failed/)).toBeInTheDocument();
    });

    test("does not replay an old completed job that was never observed as active", async () => {
        const oldJob = {
            ...activeJob,
            id: 44,
            task_id: "task-44",
            ready: true,
            successful: true,
            notification_at: "2026-09-26T11:00:00Z",
        };
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [oldJob] }));

        render(<BackgroundJobNotifications />);
        await runNextPoll();
        await runNextPoll(3000);

        expect(notificationSpies.show).not.toHaveBeenCalled();
    });
});
