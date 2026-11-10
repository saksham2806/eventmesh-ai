export async function POST(request: Request) {
  const body = await request.text();

  if (body.length > 4096) {
    return Response.json(
      { detail: "Registration request too large" },
      { status: 413 }
    );
  }

  const backend =
    process.env.EVENTMESH_BACKEND_URL ||
    "http://127.0.0.1:8000";

  try {
    const upstream = await fetch(
      new URL("/auth/organizer/register", backend),
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body,
        cache: "no-store",
      }
    );

    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") ||
          "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return Response.json(
      {
        detail: "Registration server unavailable",
      },
      { status: 502 }
    );
  }
}
