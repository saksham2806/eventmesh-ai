
export async function waitForBackend(
  signal?: AbortSignal
): Promise<void> {
  const maxAttempts = 18;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (signal?.aborted) {
      throw new Error("Request cancelled");
    }

    try {
      const response = await fetch("/api/backend-ready", {
        cache: "no-store",
        signal,
      });

      if (response.ok) {
        return;
      }
    } catch {
      if (signal?.aborted) {
        throw new Error("Request cancelled");
      }
    }

    if (attempt < maxAttempts - 1) {
      await new Promise<void>((resolve) =>
        setTimeout(resolve, 5000)
      );
    }
  }

  throw new Error(
    "Server is taking longer than expected. Please try again."
  );
}
