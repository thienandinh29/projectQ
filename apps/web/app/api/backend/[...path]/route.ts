import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const allowed =
  /^(learners|topics|topics\/[^/]+|graph|graph\/review|graph\/confirm|placement\/next|attempts|tutor\/hint|uploads|reviews\/due)$/;
// The English pack (specs/web-english): ids are UUIDs, slugs are lowercase with hyphens.
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const SLUG = "[a-z0-9]+(?:-[a-z0-9]+)*";
const allowedEnglish = new RegExp(
  `^(level-tests|level-tests/${UUID}/answers|roadmap|milestones/${SLUG}/tests|` +
    `nodes/${SLUG}/practice|grammar-runs/${UUID}/answers|vocab/session|vocab/answers|` +
    `writing/prompts|essays|essays/${UUID})$`,
);
// The only path a learner may DELETE: their own essay (specs/writing/step-2.1.md).
const deletable = new RegExp(`^essays/${UUID}$`);
const forwardedParams = [
  "learner_id",
  "subject",
  "course",
  "list",
  "limit",
  "new_limit",
  "max_level",
];
const learnerCookie = "nodetrail_learner";
const sessionToken = /^[A-Za-z0-9_-]{43}$/;

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const segments = (await context.params).path;
  if (
    segments.some(
      (segment) => [".", ".."].includes(segment) || /[%/\\?#]/.test(segment),
    )
  )
    return new Response(null, { status: 404 });
  const path = segments.join("/");
  if (!allowed.test(path) && !allowedEnglish.test(path))
    return new Response(null, { status: 404 });
  if (request.method === "DELETE" && !deletable.test(path))
    return new Response(null, { status: 405 });
  if (
    (request.method === "POST" || request.method === "DELETE") &&
    request.headers.get("origin") !== request.nextUrl.origin
  )
    return new Response(null, { status: 403 });
  const origin = process.env.NODETRAIL_API_URL;
  const key = process.env.NODETRAIL_API_KEY;
  const keyHeader = process.env.NODETRAIL_API_KEY_HEADER;
  if (
    process.env.NODETRAIL_DATA_MODE !== "api" ||
    !origin ||
    !key ||
    !keyHeader ||
    !/^[A-Za-z0-9-]+$/.test(keyHeader) ||
    ["host", "content-type", "content-length", "cookie", "origin"].includes(
      keyHeader.toLowerCase(),
    )
  )
    return new Response(null, { status: 503 });
  try {
    const base = new URL(origin);
    if (
      !["http:", "https:"].includes(base.protocol) ||
      base.username ||
      base.password ||
      base.search ||
      base.hash
    )
      return new Response(null, { status: 503 });
    const target = new URL(
      `${base.pathname.replace(/\/$/, "")}/${path}`,
      base.origin,
    );
    for (const name of forwardedParams) {
      const value = request.nextUrl.searchParams.get(name);
      if (value) target.searchParams.set(name, value);
    }
    const headers = new Headers({ [keyHeader]: key });
    const token = request.cookies.get(learnerCookie)?.value;
    if (token && sessionToken.test(token))
      headers.set("Cookie", `${learnerCookie}=${token}`);
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    if (
      path === "uploads" &&
      request.headers.get("x-demo-upload-consent") === "demo-v1"
    )
      headers.set("X-Demo-Upload-Consent", "demo-v1");
    const signals = AbortSignal.any([
      request.signal,
      AbortSignal.timeout(25000),
    ]);
    let body: Uint8Array | undefined;
    if (request.method === "POST") {
      const limit =
        path === "uploads"
          ? Number(process.env.NODETRAIL_MAX_UPLOAD_BYTES) + 64 * 1024
          : 64 * 1024;
      if (
        !Number.isSafeInteger(limit) ||
        (limit <= 64 * 1024 && path === "uploads")
      )
        return new Response(null, { status: 503 });
      const reader = request.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader) {
        while (true) {
          const next = await reader.read();
          if (next.done) break;
          size += next.value.byteLength;
          if (size > limit) {
            await reader.cancel();
            return new Response(null, { status: 413 });
          }
          chunks.push(next.value);
        }
      }
      body = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        body.set(chunk, offset);
        offset += chunk.byteLength;
      }
    }
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: body as BodyInit | undefined,
      cache: "no-store",
      signal: signals,
      redirect: "error",
    });
    const responseHeaders = new Headers({
      "Content-Type":
        response.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-store",
    });
    // Scope the backend credential to this origin; never forward arbitrary cookies.
    if (path === "learners" && response.ok && request.method === "POST") {
      const issued = response.headers
        .get("set-cookie")
        ?.match(/(?:^|,\s*)nodetrail_learner=([A-Za-z0-9_-]{43})(?:;|$)/)?.[1];
      if (issued)
        responseHeaders.set(
          "Set-Cookie",
          `${learnerCookie}=${issued}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax${request.nextUrl.protocol === "https:" ? "; Secure" : ""}`,
        );
    }
    return new Response(response.status === 204 ? null : response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch {
    return new Response(null, { status: 502 });
  }
}
export { proxy as DELETE, proxy as GET, proxy as POST };
