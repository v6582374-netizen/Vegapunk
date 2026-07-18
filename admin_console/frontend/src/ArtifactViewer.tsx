import { useEffect, useState } from "react";
import { Alert, Button, Empty, Spin, Typography } from "antd";
import ReactMarkdown from "react-markdown";
import { artifactFileUrl, fetchArtifactText } from "./api";

const TEXT_EXTENSIONS = new Set([
  "txt", "log", "json", "yaml", "yml", "py", "ts", "tsx", "js", "sh",
  "tex", "bib", "csv", "toml", "ini", "cfg", "html", "css",
]);
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);

function extensionOf(path: string): string {
  const dot = path.lastIndexOf(".");
  return dot === -1 ? "" : path.slice(dot + 1).toLowerCase();
}

function prettyIfJson(text: string, extension: string): string {
  if (extension !== "json") return text;
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

export default function ArtifactViewer({
  launchId,
  path,
}: {
  launchId: string;
  path: string | null;
}) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const extension = path === null ? "" : extensionOf(path);
  const isText = TEXT_EXTENSIONS.has(extension) || extension === "md";

  useEffect(() => {
    setText(null);
    setError(null);
    if (path === null || !isText) return;
    setLoading(true);
    fetchArtifactText(launchId, path)
      .then(setText)
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false));
  }, [launchId, path, isText]);

  if (path === null) {
    return <Empty description="选择左侧文件查看内容" />;
  }
  if (error !== null) {
    return <Alert type="error" message={error} />;
  }
  if (loading) {
    return <Spin />;
  }

  const url = artifactFileUrl(launchId, path);

  if (IMAGE_EXTENSIONS.has(extension)) {
    return <img src={url} alt={path} style={{ maxWidth: "100%" }} />;
  }
  if (extension === "pdf") {
    return <iframe src={url} title={path} style={{ width: "100%", height: "75vh", border: 0 }} />;
  }
  if (extension === "md" && text !== null) {
    return <ReactMarkdown>{text}</ReactMarkdown>;
  }
  if (isText && text !== null) {
    return (
      <pre style={{ whiteSpace: "pre-wrap", maxHeight: "75vh", overflow: "auto" }}>
        {prettyIfJson(text, extension)}
      </pre>
    );
  }
  return (
    <Typography.Paragraph>
      该文件类型没有内置查看器。
      <Button type="link" href={url} target="_blank">
        下载 {path}
      </Button>
    </Typography.Paragraph>
  );
}
