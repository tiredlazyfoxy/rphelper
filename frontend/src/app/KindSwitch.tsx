// The kind switch (feature 013, step 006, D8): a two-position "Entry kind" SegmentedControl,
// "Partner" / "My turn", showing `effectiveKind(state)`; choosing a segment calls
// `chooseKind`. Makes no request. Placed above the zone by `007`.
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { SegmentedControl } from "@mantine/core";

import { chooseKind, effectiveKind } from "./streamState";
import type { StreamKind, StreamState } from "./streamState";

export type KindSwitchProps = {
  state: StreamState;
};

const KIND_SEGMENTS: { label: string; value: StreamKind }[] = [
  { label: "Partner", value: "partner" },
  { label: "My turn", value: "turn" },
];

function isStreamKind(value: string): value is StreamKind {
  return value === "partner" || value === "turn";
}

/** The two-position switch showing the effective position (D8). */
export const KindSwitch = observer(function KindSwitch(
  props: KindSwitchProps,
): React.JSX.Element {
  const { state } = props;
  return (
    <SegmentedControl
      aria-label="Entry kind"
      data={KIND_SEGMENTS}
      value={effectiveKind(state)}
      onChange={(value) => {
        if (isStreamKind(value)) {
          chooseKind(state, value);
        }
      }}
    />
  );
});
