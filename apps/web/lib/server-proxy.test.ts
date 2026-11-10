import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "@/app/api/backend/[...path]/route";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
function configure() {
  vi.stubEnv("NODETRAIL_DATA_MODE", "api");
  vi.stubEnv("NODETRAIL_API_URL", "https://backend.example/v1");
  vi.stubEnv("NODETRAIL_API_KEY", "test-only-key");
  vi.stubEnv("NODETRAIL_API_KEY_HEADER", "X-Test-Api-Key");
}
const context = (path: string[]) => ({ params: Promise.resolve({ path }) });
describe("same-origin API proxy", () => {
  it.each([null, "other", "demo-v1"])(
    "preserves only explicit upload consent %s",
    async (consent) => {
      configure();
      vi.stubEnv("NODETRAIL_MAX_UPLOAD_BYTES", "1000000");
      const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
      vi.stubGlobal("fetch", fetchMock);
      const headers = new Headers({
        origin: "http://localhost:3000",
        "content-type": "application/json",
      });
      if (consent) headers.set("X-Demo-Upload-Consent", consent);
      const response = await POST(
        new NextRequest("http://localhost:3000/api/backend/uploads", {
          method: "POST",
          headers,
          body: "{}",
        }),
        context(["uploads"]),
      );
      expect(response.status).toBe(200);
      expect(
        new Headers(fetchMock.mock.calls[0][1].headers).get(
          "X-Demo-Upload-Consent",
        ),
      ).toBe(consent === "demo-v1" ? consent : null);
    },
  );
  it("fails closed with missing configuration and rejects noncontract routes", async () => {
    vi.stubEnv("NODETRAIL_DATA_MODE", "mock");
    expect(
      (
        await GET(
          new NextRequest("http://localhost:3000/api/backend/graph"),
          context(["graph"]),
        )
      ).status,
    ).toBe(503);
    expect(
      (
        await GET(
          new NextRequest("http://localhost:3000/api/backend/secrets"),
          context(["secrets"]),
        )
      ).status,
    ).toBe(404);
    expect(
      (
        await GET(
          new NextRequest("http://localhost:3000/api/backend/topics/x"),
          context(["topics", ".."]),
        )
      ).status,
    ).toBe(404);
  });
  it("blocks cross-origin submissions before contacting the upstream", async () => {
    configure();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const response = await POST(
      new NextRequest("http://localhost:3000/api/backend/topics", {
        method: "POST",
        headers: { origin: "https://other.example" },
        body: "{}",
      }),
      context(["topics"]),
    );
    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("adds a server-only key and forwards only documented query parameters", async () => {
    configure();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('{"nodes":[],"edges":[]}', {
        headers: {
          "Content-Type": "application/json",
          "X-Test-Api-Key": "must-not-forward",
          "Set-Cookie": "must-not-forward",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const response = await GET(
      new NextRequest(
        "http://localhost:3000/api/backend/graph?learner_id=a&subject=b&token=should-drop",
      ),
      context(["graph"]),
    );
    const [url, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(url.href).toBe(
      "https://backend.example/v1/graph?learner_id=a&subject=b",
    );
    expect(new Headers(init.headers).get("X-Test-Api-Key")).toBe(
      "test-only-key",
    );
    expect(init.redirect).toBe("error");
    expect(response.headers.get("X-Test-Api-Key")).toBeNull();
    expect(response.headers.get("Set-Cookie")).toBeNull();
    expect(await response.json()).toEqual({ nodes: [], edges: [] });
  });
});

describe("graph confirmation session proxy", () => {
  const token = "a".repeat(43);
  it("issues only the learner cookie at the public origin", async () => {
    configure();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("{}", {
          headers: {
            "Set-Cookie": `nodetrail_learner=${token}; Path=/; Domain=backend.example; HttpOnly`,
          },
        }),
      ),
    );
    const response = await POST(
      new NextRequest("https://demo.example/api/backend/learners", {
        method: "POST",
        headers: { origin: "https://demo.example" },
        body: "{}",
      }),
      context(["learners"]),
    );
    expect(response.headers.get("set-cookie")).toBe(
      `nodetrail_learner=${token}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax; Secure`,
    );
  });
  it.each(["review", "confirm"])(
    "forwards only the session for graph %s",
    async (action) => {
      configure();
      const fetchMock = vi.fn().mockResolvedValue(
        new Response("{}", {
          headers: { "Set-Cookie": "unrelated=secret" },
        }),
      );
      vi.stubGlobal("fetch", fetchMock);
      const url = `http://localhost:3000/api/backend/graph/${action}?subject=python`;
      const headers = {
        origin: "http://localhost:3000",
        cookie: `other=secret; nodetrail_learner=${token}`,
      };
      const response =
        action === "review"
          ? await GET(
              new NextRequest(url, { headers }),
              context(["graph", action]),
            )
          : await POST(
              new NextRequest(url, { method: "POST", headers, body: "{}" }),
              context(["graph", action]),
            );
      expect(response.status).toBe(200);
      expect(
        new Headers(fetchMock.mock.calls[0][1].headers).get("cookie"),
      ).toBe(`nodetrail_learner=${token}`);
      expect(response.headers.get("set-cookie")).toBeNull();
    },
  );
  it("drops malformed session cookies", async () => {
    configure();
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    await GET(
      new NextRequest("http://localhost:3000/api/backend/graph/review", {
        headers: { cookie: "nodetrail_learner=forged; other=secret" },
      }),
      context(["graph", "review"]),
    );
    expect(
      new Headers(fetchMock.mock.calls[0][1].headers).get("cookie"),
    ).toBeNull();
  });
});
