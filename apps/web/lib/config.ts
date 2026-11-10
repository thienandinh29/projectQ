export interface WebConfig {
  mode: "mock" | "api";
  uploadMaxBytes: number | null;
  uploadField: string | null;
  answerEncoding: "index0" | "label" | null;
  hintFirstLevel: number | null;
}

// Only this allowlisted configuration is serialized to the client; never expose credentials.
export function getWebConfig(): WebConfig {
  if (
    process.env.NODETRAIL_DATA_MODE &&
    !["mock", "api"].includes(process.env.NODETRAIL_DATA_MODE)
  )
    throw new Error("NODETRAIL_DATA_MODE must be mock or api");
  const mode = process.env.NODETRAIL_DATA_MODE === "api" ? "api" : "mock";
  const uploadLimit = Number(process.env.NODETRAIL_MAX_UPLOAD_BYTES);
  const hintLevel = process.env.NODETRAIL_HINT_FIRST_LEVEL;
  const encoding = process.env.NODETRAIL_ANSWER_ENCODING;
  return {
    mode,
    uploadMaxBytes:
      mode === "mock"
        ? 10 * 1024 * 1024
        : Number.isSafeInteger(uploadLimit) && uploadLimit > 0
          ? uploadLimit
          : mode === "api"
            ? 20_000_000
            : null,
    uploadField:
      process.env.NODETRAIL_UPLOAD_FIELD || (mode === "api" ? "file" : null),
    answerEncoding:
      encoding === "index0" || encoding === "label"
        ? encoding
        : mode === "api"
          ? "index0"
          : null,
    hintFirstLevel:
      hintLevel !== undefined &&
      hintLevel.trim() !== "" &&
      Number.isSafeInteger(Number(hintLevel)) &&
      Number(hintLevel) >= 0
        ? Number(hintLevel)
        : mode === "api"
          ? 1
          : null,
  };
}
