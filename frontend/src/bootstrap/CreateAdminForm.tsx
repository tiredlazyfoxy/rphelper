// The offer state's create-administrator form. Store and draft passed as props.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Group, Stack, TextInput } from "@mantine/core";
import { runInAction } from "mobx";
import { observer } from "mobx-react-lite";
import { documentNavigation } from "../shared/api";
import type { BootstrapState } from "./bootstrapState";
import {
  canSubmitCreateAdmin,
  createAdminClientErrors,
  submitCreateAdmin,
  type CreateAdminDraft,
  type CreateAdminField,
} from "./createAdminDraft";

export type CreateAdminFormProps = {
  state: BootstrapState;
  draft: CreateAdminDraft;
  /** Cross-entry hand-off after "created", called once with "/". Defaults to a document navigation. */
  handOff?: (url: string) => void;
};

/** Default hand-off: the document navigation through the `shared/api.ts` seam. */
function assignDocument(url: string): void {
  documentNavigation.assign(url);
}

export const CreateAdminForm = observer(function CreateAdminForm(
  props: CreateAdminFormProps,
): React.JSX.Element {
  const { state, draft } = props;
  const handOff = props.handOff ?? assignDocument;
  const [touched, setTouched] = useState<Partial<Record<CreateAdminField, true>>>({});
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const clientErrors = createAdminClientErrors(draft);
  const canSubmit = canSubmitCreateAdmin(draft);

  // A client error shows once its field holds something or has been left; an untouched
  // empty form is not shouted at.
  const shownClientError = (field: CreateAdminField): string | undefined =>
    draft[field] !== "" || touched[field] === true ? clientErrors[field] : undefined;

  const markTouched = (field: CreateAdminField): void => {
    setTouched((current) => (current[field] === true ? current : { ...current, [field]: true }));
  };

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmitCreateAdmin(draft)) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    void submitCreateAdmin(draft, controller.signal).then((outcome) => {
      if (controller.signal.aborted) {
        return;
      }
      if (outcome === "created") {
        handOff("/");
      } else if (outcome === "refused") {
        runInAction(() => {
          state.phase = "refusal";
        });
      }
    });
  };

  return (
    <form onSubmit={onSubmit} noValidate>
      <Stack gap="sm">
        {draft.serverErrors.general !== undefined && (
          <Alert color="red" title="The administrator was not created">
            {draft.serverErrors.general}
          </Alert>
        )}
        <TextInput
          label="Username"
          autoComplete="username"
          value={draft.username}
          error={shownClientError("username") ?? draft.serverErrors.username}
          onChange={(event) => {
            const value = event.currentTarget.value;
            runInAction(() => {
              draft.username = value;
            });
          }}
          onBlur={() => markTouched("username")}
        />
        <TextInput
          type="password"
          label="Password"
          autoComplete="new-password"
          value={draft.password}
          error={shownClientError("password") ?? draft.serverErrors.password}
          onChange={(event) => {
            const value = event.currentTarget.value;
            runInAction(() => {
              draft.password = value;
            });
          }}
          onBlur={() => markTouched("password")}
        />
        <TextInput
          type="password"
          label="Confirm password"
          autoComplete="new-password"
          value={draft.confirmation}
          error={shownClientError("confirmation")}
          onChange={(event) => {
            const value = event.currentTarget.value;
            runInAction(() => {
              draft.confirmation = value;
            });
          }}
          onBlur={() => markTouched("confirmation")}
        />
        <Group>
          <Button type="submit" disabled={!canSubmit} loading={draft.submitting}>
            Create administrator
          </Button>
        </Group>
      </Stack>
    </form>
  );
});
