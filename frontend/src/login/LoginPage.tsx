// The `login` entry's one screen: the sign-in form. Draft passed as a prop.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Container, Group, Stack, TextInput, Title } from "@mantine/core";
import { runInAction } from "mobx";
import { observer } from "mobx-react-lite";
import { documentNavigation } from "../shared/api";
import {
  canSubmitLogin,
  loginClientErrors,
  submitLogin,
  type LoginDraft,
  type LoginField,
} from "./loginDraft";
import { LoginGate, probeLoginGate } from "./loginGate";

export type LoginPageProps = {
  draft: LoginDraft;
  /** Cross-entry hand-off after "signedIn", called once with "/". Defaults to a document navigation. */
  handOff?: (url: string) => void;
};

/** Default hand-off: the document navigation through the `shared/api.ts` seam. */
function assignDocument(url: string): void {
  documentNavigation.assign(url);
}

export const LoginPage = observer(function LoginPage(props: LoginPageProps): React.JSX.Element {
  const { draft } = props;
  const handOff = props.handOff ?? assignDocument;
  const [touched, setTouched] = useState<Partial<Record<LoginField, true>>>({});
  const controllerRef = useRef<AbortController | null>(null);
  const [gate] = useState(() => new LoginGate());

  // The mount probe (fast/010): runs once per mount; a changed `handOff` does not re-probe.
  useEffect(() => {
    const controller = new AbortController();
    void probeLoginGate(gate, controller.signal, handOff);
    return () => {
      controller.abort();
    };
  }, [gate]);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, []);

  const clientErrors = loginClientErrors(draft);
  const canSubmit = canSubmitLogin(draft);

  // A client error shows once its field holds something or has been left; an untouched
  // empty form is not shouted at.
  const shownClientError = (field: LoginField): string | undefined =>
    draft[field] !== "" || touched[field] === true ? clientErrors[field] : undefined;

  const markTouched = (field: LoginField): void => {
    setTouched((current) => (current[field] === true ? current : { ...current, [field]: true }));
  };

  const onSubmit = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!canSubmitLogin(draft)) {
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    void submitLogin(draft, controller.signal).then((outcome) => {
      if (controller.signal.aborted) {
        return;
      }
      // Everyone lands on `/`, whatever the role; the response is never read (D12).
      if (outcome === "signedIn") {
        handOff("/");
      }
    });
  };

  return (
    <div data-entry="login">
      {gate.phase === "form" && (
        <Container size="xs" py="xl">
          <form onSubmit={onSubmit} noValidate>
            <Stack gap="sm">
              <Title order={1}>Welcome back</Title>
              {draft.serverErrors.general !== undefined && (
                <Alert color="red" title="Could not sign in">
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
                autoComplete="current-password"
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
              <Group>
                <Button type="submit" disabled={!canSubmit} loading={draft.submitting}>
                  Sign in
                </Button>
              </Group>
            </Stack>
          </form>
        </Container>
      )}
    </div>
  );
});
