// The one TipTap wrapper (009 context.md D3): `@mantine/tiptap` + `tiptap-markdown` behind
// a plain label / markdown value / onChange(markdown) / readOnly interface. Domain-free UI
// infrastructure — it names no route and no entity. It imports `@mantine/tiptap`'s package
// stylesheet itself, so only the entries that bundle the editor pay for it.
import "@mantine/tiptap/styles.css";
import type * as React from "react";
import { useEffect, useId, useRef } from "react";
import { Box, Input } from "@mantine/core";
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
  /** When true: focus moves into the editable body once the editor is ready after mounting. Defaults to false. */
  autoFocus?: boolean;
  /**
   * 033 001: the minimum height of the editable content area, in pixels. Omitted, the
   * editor renders exactly as before (no minimum height applied).
   */
  contentMinHeight?: number;
  /**
   * Fast 012: extra content rendered as one trailing controls group at the right end of the
   * toolbar. Omitted, the toolbar is exactly as before; with `readOnly` (no toolbar) it does
   * not render.
   */
  toolbarActions?: React.ReactNode;
};

/** The editor's current content, serialised back to markdown. */
function toMarkdown(editor: Editor): string {
  return (editor.storage.markdown as MarkdownStorage).getMarkdown();
}

export function MarkdownEditor(props: MarkdownEditorProps): React.JSX.Element {
  const {
    label,
    value,
    onChange,
    readOnly = false,
    autoFocus = false,
    contentMinHeight,
    toolbarActions,
  } = props;

  // The editor is created once; `onChange` is reached through a ref so a new callback
  // identity neither recreates it nor leaves `onUpdate` calling a stale function.
  const onChangeRef = useRef(onChange);
  // The visible label's id: the editable surface is named by it (`aria-labelledby`).
  const labelId = useId();
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  const editor = useEditor({
    extensions: [StarterKit, Link, Markdown],
    // The Markdown extension parses a markdown string given as content.
    content: value,
    editable: !readOnly,
    // Focus moves into the body once the editor is created; false leaves focus alone.
    autofocus: autoFocus ? "end" : false,
    // Role, accessible name and multi-line semantics land on the ProseMirror
    // contenteditable element itself.
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-label": label,
        "aria-labelledby": labelId,
        "aria-multiline": "true",
        // 033 001: an inline minimum height on the editable surface itself, so the whole
        // tall area is clickable; omitted, no style attribute is added at all.
        ...(contentMinHeight === undefined ? {} : { style: `min-height: ${contentMinHeight}px` }),
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

  // The label is visible text tied to the surface by id. A `div`, not a `<label>`: a
  // contenteditable is not a labelable element, so the name travels by `aria-labelledby`.
  return (
    <Box>
      <Input.Label labelElement="div" id={labelId}>
        {label}
      </Input.Label>
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
            {toolbarActions === undefined || toolbarActions === null ? null : (
              <RichTextEditor.ControlsGroup ml="auto">{toolbarActions}</RichTextEditor.ControlsGroup>
            )}
          </RichTextEditor.Toolbar>
        )}
        <RichTextEditor.Content />
      </RichTextEditor>
    </Box>
  );
}
