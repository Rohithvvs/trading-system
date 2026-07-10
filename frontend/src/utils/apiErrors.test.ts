import { describe, expect, it, vi, afterEach } from "vitest";
import { mapHttpError, mapNetworkError, toUserFacingApiMessage, ApiClientError } from "./apiErrors";

describe("mapNetworkError", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("maps Failed to fetch to Cannot connect to server", () => {
    const err = mapNetworkError(new TypeError("Failed to fetch"), "https://api.example.com/auth/login");
    expect(err).toBeInstanceOf(ApiClientError);
    expect(err.message).toBe("Cannot connect to server.");
    expect(err.code).toBe("SERVER_UNREACHABLE");
  });

  it("maps abort to Request timed out", () => {
    const abort = new DOMException("Aborted", "AbortError");
    const err = mapNetworkError(abort, "https://api.example.com/auth/login");
    expect(err.message).toBe("Request timed out.");
    expect(err.code).toBe("TIMEOUT");
  });

  it("maps offline navigator to Network connection lost", () => {
    vi.stubGlobal("navigator", { onLine: false });
    const err = mapNetworkError(new TypeError("Failed to fetch"), "https://api.example.com/auth/login");
    expect(err.message).toBe("Network connection lost.");
    expect(err.code).toBe("NETWORK_LOST");
  });

  it("detects localhost API from remote page", () => {
    vi.stubGlobal("window", {
      location: { protocol: "https:", hostname: "my-app.vercel.app" },
    });
    const err = mapNetworkError(
      new TypeError("Failed to fetch"),
      "http://127.0.0.1:8000/auth/login",
    );
    expect(err.message).toMatch(/Backend URL is unreachable/);
    expect(err.code).toBe("LOCALHOST_IN_PROD");
  });

  it("maps CORS wording", () => {
    const err = mapNetworkError(
      new Error("Access to fetch blocked by CORS policy"),
      "https://api.example.com/auth/login",
    );
    expect(err.message).toBe("CORS blocked request.");
    expect(err.code).toBe("CORS");
  });
});

describe("mapHttpError", () => {
  it("maps 503 to Server unavailable", () => {
    const err = mapHttpError(503, "https://api.example.com/health");
    expect(err.message).toBe("Server unavailable.");
    expect(err.code).toBe("SERVER_UNAVAILABLE");
  });

  it("maps 504 to Request timed out", () => {
    const err = mapHttpError(504);
    expect(err.message).toBe("Request timed out.");
  });
});

describe("toUserFacingApiMessage", () => {
  it("never returns Failed to fetch", () => {
    const msg = toUserFacingApiMessage(new TypeError("Failed to fetch"));
    expect(msg.toLowerCase()).not.toContain("failed to fetch");
    expect(msg).toBe("Cannot connect to server.");
  });

  it("passes through ApiClientError message", () => {
    const err = new ApiClientError("Server unavailable.", { code: "SERVER_UNAVAILABLE" });
    expect(toUserFacingApiMessage(err)).toBe("Server unavailable.");
  });
});
