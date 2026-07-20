import { describe, expect, it } from "vitest";
import { inferContentType } from "./inferContentType";

describe("inferContentType", () => {
  it("prefers the browser-provided file.type when present", () => {
    expect(inferContentType({ name: "notes.txt", type: "application/pdf" })).toBe("application/pdf");
  });

  it("falls back to the extension when file.type is empty", () => {
    expect(inferContentType({ name: "notes.txt", type: "" })).toBe("text/plain");
    expect(inferContentType({ name: "paper.pdf", type: "" })).toBe("application/pdf");
    expect(inferContentType({ name: "essay.docx", type: "" })).toBe(
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    );
    expect(inferContentType({ name: "photo.JPG", type: "" })).toBe("image/jpeg");
    expect(inferContentType({ name: "scan.png", type: "" })).toBe("image/png");
    expect(inferContentType({ name: "shot.webp", type: "" })).toBe("image/webp");
  });

  it("returns octet-stream for an unknown extension with no type", () => {
    expect(inferContentType({ name: "archive.zip", type: "" })).toBe("application/octet-stream");
    expect(inferContentType({ name: "noextension", type: "" })).toBe("application/octet-stream");
  });
});
