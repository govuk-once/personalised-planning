import type { ActionResult, JobState } from "@/lib/types";

const CHECK_TIMEOUT_MS = 20_000;

export async function fetchJob<T>(
	sessionId: string,
	jobId: string,
): Promise<ActionResult<JobState<T>>> {
	const body = JSON.stringify({
		sessionId,
		jobId,
	});

	const response = await fetch("/api/job", {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
		},
		body,
		cache: "no-store",
		signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
	});

	if (!response.ok) {
		throw new Error(`Checking the job failed: ${response.status}`);
	}

	return (await response.json()) as ActionResult<JobState<T>>;
}
