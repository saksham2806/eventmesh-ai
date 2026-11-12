
import { NextResponse } from "next/server";

export async function GET() {
  const backendUrl = process.env.EVENTMESH_BACKEND_URL;

  if (!backendUrl) {
    return NextResponse.json(
      { ready: false },
      { status: 503 }
    );
  }

  try {
    const response = await fetch(
      `${backendUrl.replace(/\/$/, "")}/health`,
      {
        cache: "no-store",
        signal: AbortSignal.timeout(12000),
      }
    );

    return NextResponse.json(
      { ready: response.ok },
      {
        status: response.ok ? 200 : 503,
        headers: {
          "Cache-Control": "no-store",
        },
      }
    );
  } catch {
    return NextResponse.json(
      { ready: false },
      { status: 503 }
    );
  }
}
