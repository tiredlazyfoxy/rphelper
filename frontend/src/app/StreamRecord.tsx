// The settled record (feature 013, step 004, D4, D11; extended by 014 step 005, D6, D7, D10):
// a "Settled record" list, one item per entry with its kind label, an actions group and its
// body. The actions group — "Edit entry" on every kind, "Copy as plain text" on turns only,
// and "Re-open last entry" on the last item when `showsReopen` holds — is always rendered and
// revealed by opacity while the entry is hovered, has focus within, or the device cannot
// hover. "Edit entry" swaps the body for an in-place editor that commits on blur.
//
// Feature 023, step 005 (D13, D14, D15): with an optional `TranslationState` given, a settled
// *partner* entry also offers the translate flicker inside that same actions group and shows
// its translation in place of the original; committing an edit of a partner entry drops that
// row's cached translation. Without the state nothing changes for any kind.
import { useState } from "react";
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Blockquote, Box, Group, Stack, Text, Textarea } from "@mantine/core";
import { useFocusWithin, useHover, useMediaQuery, useMergedRef } from "@mantine/hooks";
import { IconArrowBackUp, IconCopy, IconEdit, IconLanguage } from "@tabler/icons-react";

import { IconButton } from "../shared/IconButton";
import { copyAsPlainText } from "./copyOut";
import { DiscussionGroup } from "./DiscussionGroup";
import { MessageBody } from "./MessageBody";
import type { Message, MessageKind } from "./streamApi";
import { editEntry, reopenLast, showsReopen } from "./streamState";
import type { StreamState } from "./streamState";
import { flickTranslation, invalidateTranslation, translationView } from "./translationState";
import type { TranslationState } from "./translationState";

export type StreamRecordProps = {
  state: StreamState;
  /** Passed on to `reopenLast`. */
  signal?: AbortSignal;
  /**
   * The mount's flicker state (023 D13), handed to every entry. **Optional:** without it no
   * entry renders a flicker and nothing is invalidated on edit, so callers that pass none —
   * and 013 / 014's tests — are unaffected.
   */
  translations?: TranslationState;
};

const KIND_LABELS: Record<MessageKind, string> = {
  partner: "Partner",
  turn: "My turn",
  decision: "Decision",
};

/**
 * The body by kind: partner quoted and plain, turn plain, decision the card (D5). `text`
 * overrides the entry's stored text, so a shown translation renders through this very same
 * renderer (023 `005`); omitted — as 013 / 014 omit it — the entry's own text is rendered.
 */
function EntryBody(props: { entry: Message; text?: string }): React.JSX.Element {
  const { entry } = props;
  const text = props.text ?? entry.text;
  if (entry.kind === "decision") {
    return <MessageBody text={text} variant="decision" />;
  }
  if (entry.kind === "partner") {
    return (
      <Blockquote p="sm" m={0}>
        <MessageBody text={text} variant="plain" />
      </Blockquote>
    );
  }
  return <MessageBody text={text} variant="plain" />;
}

/**
 * The flicker's colour while the translation is showing (023 D15); none in the other two
 * states, so the control falls back to the theme's own. Not `blue` — that *is* the theme's
 * primary, which would make the two states indistinguishable.
 */
const TRANSLATED_COLOR = "teal";

/**
 * 023 `005` (D15): the partner flicker — one `shared/IconButton` with `IconLanguage` whose
 * label carries the state and so feeds both tooltip and `aria-label`: "Show translation" while
 * the original is showing, "Cancel translation" while a request is in flight (pressing it then
 * aborts that request), "Show original" while the translation is showing. No `aria-pressed`:
 * the name changes with the state, which the ARIA toggle pattern forbids combining with it.
 * An `observer`, because the label is derived from observable state the press itself changes.
 */
const PartnerFlicker = observer(function PartnerFlicker(props: {
  translations: TranslationState;
  entry: Message;
}): React.JSX.Element {
  const { translations, entry } = props;
  const view = translationView(translations, entry.id);
  const translated = view.status === "translated";
  const label = translated
    ? "Show original"
    : view.status === "pending"
      ? "Cancel translation"
      : "Show translation";
  return (
    <IconButton
      icon={IconLanguage}
      label={label}
      color={translated ? TRANSLATED_COLOR : undefined}
      onClick={() => {
        void flickTranslation(translations, entry.id);
      }}
    />
  );
});

/**
 * 023 `005`: the text a partner entry's body shows — the translation while it is showing, else
 * the entry's stored original, the `"pending"` case included (a translation in flight leaves the
 * original in place). The in-place editor is fed `entry.text` elsewhere, so it always edits the
 * stored original.
 */
function partnerBodyText(translations: TranslationState, entry: Message): string {
  const view = translationView(translations, entry.id);
  return view.status === "translated" ? view.text : entry.text;
}

/** Props of one settled entry (014 `005`; `translations` is 023 `005`). */
type StreamEntryProps = {
  state: StreamState;
  entry: Message;
  /** Whether this is the record's last entry (re-open candidate under `showsReopen`). */
  isLast: boolean;
  /** Passed on to `reopenLast` and `editEntry`. */
  signal?: AbortSignal;
  /** The mount's flicker state (023 D13). Absent → no flicker, no invalidation. */
  translations?: TranslationState;
};

/**
 * One settled entry (014 `005`, D6, D7, D10): kind label, the always-rendered actions group
 * (revealed by opacity, reported as `data-revealed`) and the body by kind, or the
 * "Edit entry text" editor while editing.
 */
const StreamEntry = observer(function StreamEntry(
  props: StreamEntryProps,
): React.JSX.Element {
  const { state, entry, isLast, signal, translations } = props;
  const reopenOffered = isLast && showsReopen(state);
  // 023 `005`: the flicker exists only for a settled partner entry, and only when this mount
  // handed the record its flicker state (D13, D15). Turns and decisions never get one.
  const flicker: TranslationState | undefined =
    entry.kind === "partner" ? translations : undefined;

  // Reveal (D6): hovered, focus within, or a device that cannot hover.
  const { hovered, ref: hoverRef } = useHover<HTMLLIElement>();
  const { focused, ref: focusRef } = useFocusWithin<HTMLLIElement>();
  const itemRef = useMergedRef<HTMLLIElement>(hoverRef, focusRef);
  const noHover = useMediaQuery("(hover: none)") === true;
  const revealed = hovered || focused || noHover;

  // View state (D10): whether this entry's editor is open, and its draft.
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState("");

  function openEditor(): void {
    if (editing) {
      return; // an open editor keeps its typed text (R10)
    }
    setEditDraft(entry.text);
    setEditing(true);
  }

  function commit(): void {
    const text = editDraft;
    void editEntry(state, entry.id, text, signal).then((mayClose) => {
      if (mayClose) {
        setEditing(false);
      }
      // D14: once `editEntry` has settled, a partner entry's cached translation is dropped
      // unconditionally — on success and on failure alike. `editEntry` itself is unchanged.
      if (flicker !== undefined) {
        invalidateTranslation(flicker, entry.id);
      }
    });
  }

  return (
    <Box component="li" ref={itemRef} mb="md">
      <Stack gap="xs">
        <Group gap="xs" justify="space-between" wrap="nowrap">
          <Text size="sm" fw={600} c="dimmed">
            {entry.kind === null ? "" : KIND_LABELS[entry.kind]}
          </Text>
          <Group
            gap={4}
            wrap="nowrap"
            data-revealed={revealed ? "true" : "false"}
            style={{ opacity: revealed ? 1 : 0 }}
          >
            {editing ? null : (
              <IconButton icon={IconEdit} label="Edit entry" onClick={openEditor} />
            )}
            {flicker === undefined ? null : (
              <PartnerFlicker translations={flicker} entry={entry} />
            )}
            {entry.kind === "turn" ? (
              <IconButton
                icon={IconCopy}
                label="Copy as plain text"
                onClick={() => {
                  void copyAsPlainText(entry.text);
                }}
              />
            ) : null}
            {reopenOffered ? (
              <IconButton
                icon={IconArrowBackUp}
                label="Re-open last entry"
                disabled={state.busy}
                onClick={() => {
                  void reopenLast(state, signal);
                }}
              />
            ) : null}
          </Group>
        </Group>
        {editing ? (
          <Textarea
            aria-label="Edit entry text"
            autosize
            autoFocus
            value={editDraft}
            onChange={(event) => {
              setEditDraft(event.currentTarget.value);
            }}
            onBlur={commit}
          />
        ) : (
          <EntryBody
            entry={entry}
            text={flicker === undefined ? undefined : partnerBodyText(flicker, entry)}
          />
        )}
        {entry.kind !== "partner" ? (
          <DiscussionGroup key={entry.id} entryId={entry.id} state={state} />
        ) : null}
      </Stack>
    </Box>
  );
});

/** Renders the session's settled record (D4, D11). */
export const StreamRecord = observer(function StreamRecord(
  props: StreamRecordProps,
): React.JSX.Element {
  const { state, signal, translations } = props;
  const entries = state.entries;
  const lastIndex = entries.length - 1;

  return (
    <Box
      component="ul"
      aria-label="Settled record"
      m={0}
      p={0}
      style={{ listStyle: "none" }}
    >
      {entries.length === 0 ? (
        <Text c="dimmed">No entries yet.</Text>
      ) : (
        entries.map((entry, index) => (
          <StreamEntry
            key={entry.id}
            state={state}
            entry={entry}
            isLast={index === lastIndex}
            signal={signal}
            translations={translations}
          />
        ))
      )}
    </Box>
  );
});
