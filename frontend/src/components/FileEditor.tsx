import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import { languageFromPath } from "../api/language";

loader.config({ monaco });

type Props = {
  path: string;
  content: string;
  onChange: (value: string) => void;
  onSave: () => void;
  readOnly?: boolean;
};

export function FileEditor({ path, content, onChange, onSave, readOnly }: Props) {
  return (
    <div
      className="monaco-wrap"
      data-testid="file-editor"
      onKeyDown={(event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          onSave();
        }
      }}
    >
      <Editor
        height="100%"
        path={path}
        language={languageFromPath(path)}
        value={content}
        onChange={(value) => onChange(value ?? "")}
        options={{
          readOnly: Boolean(readOnly),
          minimap: { enabled: false },
          fontSize: 14,
          wordWrap: "on",
          automaticLayout: true,
          scrollBeyondLastLine: false,
        }}
      />
    </div>
  );
}
