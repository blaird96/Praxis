/** Map repository filenames to Monaco language ids. */
export function languageFromPath(path: string): string {
  const name = path.split("/").pop()?.toLowerCase() ?? "";
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot + 1) : "";
  switch (ext) {
    case "ts":
    case "tsx":
      return "typescript";
    case "js":
    case "jsx":
    case "mjs":
    case "cjs":
      return "javascript";
    case "json":
      return "json";
    case "md":
    case "markdown":
      return "markdown";
    case "py":
      return "python";
    case "yml":
    case "yaml":
      return "yaml";
    case "toml":
      return "ini";
    case "css":
      return "css";
    case "html":
    case "htm":
      return "html";
    case "sh":
    case "bash":
      return "shell";
    case "xml":
      return "xml";
    case "rs":
      return "rust";
    case "go":
      return "go";
    case "txt":
    case "gitignore":
    case "env":
    case "example":
      return "plaintext";
    default:
      if (name === "dockerfile") return "dockerfile";
      if (name.startsWith(".env")) return "plaintext";
      return "plaintext";
  }
}
