export type PreviewAttachment = { kind: "image" | "audio" | "file" | "video"; name: string; mime: string; base64: string };

export async function readPreviewAttachment(file: File): Promise<PreviewAttachment> {
  if (file.size > 50 * 1024 * 1024) throw new Error("Use files up to 50 MB");
  const mime = file.type || ({ txt: "text/plain", md: "text/markdown", csv: "text/csv", json: "application/json", pdf: "application/pdf" }[file.name.split(".").at(-1)?.toLowerCase() ?? ""]);
  if (!mime) throw new Error("Unsupported file type");
  const kind = mime.startsWith("image/") ? "image" : mime.startsWith("audio/") ? "audio" : mime.startsWith("video/") ? "video" : "file";
  if (kind === "image" && (!["image/jpeg", "image/png"].includes(mime) || file.size > 10 * 1024 * 1024)) throw new Error("Use JPG/PNG up to 10 MB");
  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader(); reader.onerror = () => reject(new Error("Could not read file"));
    reader.onload = () => typeof reader.result === "string" ? resolve(reader.result) : reject(new Error("Could not read file"));
    reader.readAsDataURL(file);
  });
  return { kind, name: file.name, mime, base64: data.slice(data.indexOf(",") + 1) };
}
