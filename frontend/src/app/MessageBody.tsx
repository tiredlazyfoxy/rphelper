// One message renderer with three variants (feature 013, step 004, D5): "plain" renders the
// text as markdown; "decision" renders the out-of-character card; "painted" renders the card
// for a wholly parenthesised text, otherwise prose as markdown with each `((...))` fragment
// as an inline chip. Not an observer — callers pass plain values.
import type * as React from "react";
import { Box, Paper, Text } from "@mantine/core";
import Markdown from "react-markdown";
import type { Components, ExtraProps } from "react-markdown";

import { isWhollyParenthesised, splitParenSegments } from "./parens";

/** How `MessageBody` renders its text (D5). */
export type MessageBodyVariant = "painted" | "decision" | "plain";

export type MessageBodyProps = {
  /** The message text, rendered verbatim (never altered). */
  text: string;
  variant: MessageBodyVariant;
};

const ACCENT = "var(--mantine-primary-color-filled)";

/** A gap holding a blank line: a real paragraph break, so the paragraph stays a block. */
const BLANK_LINE = /\n[ \t]*\n/;

/** The out-of-character card: dashed accent border, its label, the text as markdown. */
function OutOfCharacterCard(props: { text: string }): React.JSX.Element {
  return (
    <Paper
      data-paren="ooc"
      withBorder
      radius="sm"
      p="sm"
      style={{ borderStyle: "dashed", borderColor: ACCENT }}
    >
      <Text size="xs" fw={600} c={ACCENT}>
        Out of character
      </Text>
      <Markdown>{props.text}</Markdown>
    </Paper>
  );
}

/**
 * Markdown components for one prose segment sitting between fragments: a paragraph that
 * touches the segment's start or end (with no blank line in between) flows inline, so the
 * neighbouring chip stays on its line; every other paragraph remains a block.
 */
function inlineEdgeComponents(source: string): Components {
  function isInlineEdge(node: ExtraProps["node"]): boolean {
    const start = node?.position?.start.offset;
    const end = node?.position?.end.offset;
    if (start === undefined || end === undefined) {
      return false;
    }
    const before = source.slice(0, start);
    const after = source.slice(end);
    const opensSegment = before.trim() === "" && !BLANK_LINE.test(before);
    const closesSegment = after.trim() === "" && !BLANK_LINE.test(after);
    return opensSegment || closesSegment;
  }
  return {
    p(paragraphProps) {
      const { node, children } = paragraphProps;
      if (isInlineEdge(node)) {
        return <span>{children}</span>;
      }
      return <p>{children}</p>;
    },
  };
}

/** Prose and fragment chips in order (a text that is not wholly parenthesised). */
function PaintedSegments(props: { text: string }): React.JSX.Element {
  const segments = splitParenSegments(props.text);
  return (
    <Box>
      {segments.map((segment, index) =>
        segment.kind === "fragment" ? (
          <Text
            key={index}
            span
            data-paren="fragment"
            bg="var(--mantine-primary-color-light)"
            c="var(--mantine-primary-color-light-color)"
            px={4}
            mx={2}
            style={{ borderRadius: "var(--mantine-radius-sm)" }}
          >
            {segment.text}
          </Text>
        ) : (
          <Markdown key={index} components={inlineEdgeComponents(segment.text)}>
            {segment.text}
          </Markdown>
        ),
      )}
    </Box>
  );
}

/** Renders one message body in the given variant (D5). */
export function MessageBody(props: MessageBodyProps): React.JSX.Element {
  const { text, variant } = props;
  if (variant === "decision") {
    return <OutOfCharacterCard text={text} />;
  }
  if (variant === "painted") {
    if (isWhollyParenthesised(text)) {
      return <OutOfCharacterCard text={text} />;
    }
    if (splitParenSegments(text).some((segment) => segment.kind === "fragment")) {
      return <PaintedSegments text={text} />;
    }
  }
  return (
    <Box>
      <Markdown>{text}</Markdown>
    </Box>
  );
}
