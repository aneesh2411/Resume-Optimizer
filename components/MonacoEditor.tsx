"use client";

/**
 * MonacoEditor — lightweight wrapper around @monaco-editor/react.
 * Supports read-only mode (syntax-highlighted view) and editable mode (HITL editing).
 */

import Editor from "@monaco-editor/react";

interface MonacoEditorProps {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  height?: string;
}

export function MonacoEditor({
  value,
  onChange,
  readOnly = false,
  height = "500px",
}: MonacoEditorProps) {
  return (
    <div className="border rounded-lg overflow-hidden">
      <Editor
        height={height}
        defaultLanguage="latex"
        value={value}
        onChange={(v) => onChange?.(v ?? "")}
        options={{
          readOnly,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 13,
          lineNumbers: "on",
          wordWrap: "on",
          theme: "vs",
        }}
        loading={
          <div className="flex items-center justify-center h-full bg-muted/20 text-sm text-muted-foreground">
            Loading editor…
          </div>
        }
      />
    </div>
  );
}
