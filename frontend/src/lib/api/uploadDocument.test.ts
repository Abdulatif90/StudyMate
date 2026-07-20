import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Client } from "openapi-fetch";
import type { paths } from "./schema";
import { UploadError, uploadDocument } from "./uploadDocument";

/**
 * A minimal controllable XMLHttpRequest stand-in — jsdom's real one can't reach the
 * network. `putBehavior` decides how the simulated direct-to-R2 PUT resolves.
 */
let putBehavior: "success" | "error" = "success";

class FakeXHR {
  status = 0;
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  open = vi.fn();
  setRequestHeader = vi.fn();
  abort = vi.fn();

  send() {
    // Fire a progress event, then resolve/reject on the next microtask.
    this.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 });
    queueMicrotask(() => {
      if (putBehavior === "success") {
        this.status = 200;
        this.onload?.();
      } else {
        this.onerror?.();
      }
    });
  }
}

const DOCUMENT_ID = "11111111-1111-1111-1111-111111111111";

/** Build a fake typed api client whose two POST calls (presign, confirm) return the
 * given results in order. */
function makeApi(results: Array<{ data?: unknown; error?: unknown; status: number }>): Client<paths> {
  let call = 0;
  const POST = vi.fn(async () => {
    const r = results[call++];
    return { data: r.data, error: r.error, response: { status: r.status } as Response };
  });
  return { POST } as unknown as Client<paths>;
}

const FILE = { name: "notes.txt", type: "text/plain" } as File;

beforeEach(() => {
  putBehavior = "success";
  vi.stubGlobal("XMLHttpRequest", FakeXHR);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("uploadDocument", () => {
  it("runs presign → PUT → confirm and returns the confirmed document", async () => {
    const api = makeApi([
      {
        data: { document_id: DOCUMENT_ID, object_key: "u/1/notes.txt", upload_url: "https://r2/put" },
        status: 200,
      },
      { data: { id: DOCUMENT_ID, filename: "notes.txt", status: "pending" }, status: 201 },
    ]);
    const onProgress = vi.fn();

    const result = await uploadDocument(api, { subjectId: "s1", file: FILE, language: "en" }, onProgress);

    expect(result).toMatchObject({ id: DOCUMENT_ID, status: "pending" });
    expect(onProgress).toHaveBeenCalledWith(50); // 5/10
    // presign then confirm, in that order
    expect((api.POST as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe(
      "/subjects/{subject_id}/documents/presign",
    );
    expect((api.POST as ReturnType<typeof vi.fn>).mock.calls[1][0]).toBe(
      "/subjects/{subject_id}/documents/{document_id}/confirm",
    );
  });

  it("throws an UploadError at the presign step (never PUTs) on a presign error", async () => {
    const api = makeApi([{ error: { detail: "over cap" }, status: 402 }]);

    await expect(
      uploadDocument(api, { subjectId: "s1", file: FILE, language: "en" }, vi.fn()),
    ).rejects.toMatchObject({ status: 402, kind: "presign", body: { detail: "over cap" } });
    // confirm was never attempted
    expect((api.POST as ReturnType<typeof vi.fn>)).toHaveBeenCalledTimes(1);
  });

  it("throws an UploadError with status 0 when the direct R2 PUT fails", async () => {
    putBehavior = "error";
    const api = makeApi([
      {
        data: { document_id: DOCUMENT_ID, object_key: "u/1/notes.txt", upload_url: "https://r2/put" },
        status: 200,
      },
    ]);

    const err = await uploadDocument(
      api,
      { subjectId: "s1", file: FILE, language: "en" },
      vi.fn(),
    ).catch((e) => e);

    expect(err).toBeInstanceOf(UploadError);
    expect(err).toMatchObject({ status: 0, kind: "put" });
    // confirm was never attempted after the PUT failed
    expect((api.POST as ReturnType<typeof vi.fn>)).toHaveBeenCalledTimes(1);
  });

  it("throws an UploadError at the confirm step on a confirm error (e.g. 413)", async () => {
    const api = makeApi([
      {
        data: { document_id: DOCUMENT_ID, object_key: "u/1/notes.txt", upload_url: "https://r2/put" },
        status: 200,
      },
      { error: { detail: "too large" }, status: 413 },
    ]);

    await expect(
      uploadDocument(api, { subjectId: "s1", file: FILE, language: "en" }, vi.fn()),
    ).rejects.toMatchObject({ status: 413, kind: "confirm" });
  });
});
