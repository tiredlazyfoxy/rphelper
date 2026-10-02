// The one TipTap wrapper (009 context.md D3): `@mantine/tiptap` + `tiptap-markdown` behind
// a plain label / markdown value / onChange(markdown) / readOnly interface. Domain-free UI
// infrastructure — it names no route and no entity. It imports `@mantine/tiptap`'s package
// stylesheet itself, so only the entries that bundle the editor pay for it.
import "@mantine/tiptap/styles.css";
import type * as React from "react";
import { useEffect, useRef } from "react";
import { RichTextEditor } from "@mantine/tiptap";
import { useEditor } from "@tiptap/react";
import type { Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import { Markdown } from "tiptap-markdown";
import type { MarkdownStorage } from "tiptap-markdown";

export type MarkdownEditorProps = {
  /** The accessible name of the editable surface. */
  label: string;
  /** The markdown the editor shows. */
  value: string;
  /** Called with the editor's content serialised as markdown, for user edits only. */
  onChange: (markdown: string) => void;
  /** When true: no toolbar and the surface is not editable. Defaults to false. */
  readOnly?: boolean;
};

/** The editor's current content, serialised back to markdown. */
function toMarkdown(editor: Editor): string {
  return (editor.storage.markdown as MarkdownStorage).getMarkdown();
}

export function MarkdownEditor(props: MarkdownEditorProps): React.JSX.Element {
  const { label, value, onChange, readOnly = false } = props;

  // The editor is created once; `onChange` is reached through a ref so a new callback
  // identity neither recreates it nor leaves `onUpdate` calling a stale function.
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  const editor = useEditor({
    extensions: [StarterKit, Link, Markdown],
    // The Markdown extension parses a markdown string given as content.
    content: value,
    editable: !readOnly,
    // Role, accessible name and multi-line semantics land on the ProseMirror
    // contenteditable element itself.
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-label": label,
        "aria-multiline": "true",
      },
    },
    // Never echo: this is the only path to `onChange`, and nothing but a user edit
    // emits an update — applying an external value and toggling editability both
    // pass `emitUpdate` false.
    onUpdate: ({ editor: edited }) => {
      onChangeRef.current(toMarkdown(edited));
    },
  });

  // A value from the parent (a load or a save response) replaces the content without
  // emitting an update, and only when it differs from what the editor already holds —
  // otherwise every keystroke's re-render would reset the cursor.
  useEffect(() => {
    if (editor === null) {
      return;
    }
    if (toMarkdown(editor) === value) {
      return;
    }
    editor.commands.setContent(value, false);
  }, [editor, value]);

  // `readOnly` after mount, too. The `emitUpdate` flag is false for the same reason.
  useEffect(() => {
    if (editor === null) {
      return;
    }
    editor.setEditable(!readOnly, false);
  }, [editor, readOnly]);

  return (
    <RichTextEditor editor={editor}>
      {readOnly ? null : (
        <RichTextEditor.Toolbar>
          <RichTextEditor.ControlsGroup>
            <RichTextEditor.Bold />
            <RichTextEditor.Italic />
          </RichTextEditor.ControlsGroup>
          <RichTextEditor.ControlsGroup>
            <RichTextEditor.H2 />
            <RichTextEditor.H3 />
          </RichTextEditor.ControlsGroup>
          <RichTextEditor.ControlsGroup>
            <RichTextEditor.BulletList />
            <RichTextEditor.OrderedList />
          </RichTextEditor.ControlsGroup>
          <RichTextEditor.ControlsGroup>
            <RichTextEditor.Link />
            <RichTextEditor.Unlink />
          </RichTextEditor.ControlsGroup>
        </RichTextEditor.Toolbar>
      )}
      <RichTextEditor.Content />
    </RichTextEditor>
  );
}
