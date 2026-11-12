
export async function waitForBackend(
  signal?: AbortSignal
): Promise<void> {
  const maxWaitMs = 180000;
  const retryDelayMs = 5000;
  const startedAt = Date.now();

  while (Date.now() - startedAt < maxWaitMs) {
    if (signal?.aborted) {
      throw new Error("Request cancelled");
    }

    try {
      const response = await fetch("/api/backend-ready", {
        cache: "no-store",
        signal,
      });

      if (response.ok) {
        const data = await response.json();

        // Continue only after FastAPI is verified healthy.
        if (data?.ready === true) {
          return;
        }
      }
    } catch {
      if (signal?.aborted) {
        throw new Error("Request cancelled");
      }
    }

    if (Date.now() - startedAt >= maxWaitMs) {
      break;
    }

    await new Promise<void>((resolve) => {
      setTimeout(resolve, retryDelayMs);
    });
  }

  throw new Error(
    "The server could not start. Please try again."
  );
}
