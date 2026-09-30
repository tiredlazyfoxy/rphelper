// The LLM Servers page: the route-level mount (creates the store with a useState
// initializer), and the observer page that renders a store it receives as a prop.
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Alert, Badge, Box, Button, Center, Container, Group, Loader, Menu, Table, Text, Title } from "@mantine/core";
import { IconDots } from "@tabler/icons-react";
import { ConfirmModal } from "../shared/ConfirmModal";
import { IconButton } from "../shared/IconButton";
import { EmbeddingModal } from "./EmbeddingModal";
import { EmbeddingDraft, clearEmbeddingDesignation } from "./embeddingDraft";
import { EnabledModelsModal } from "./EnabledModelsModal";
import { EnabledModelsDraft } from "./enabledModelsDraft";
import { ModelPicker } from "./modelPicker";
import { ServerFormModal } from "./ServerFormModal";
import { ServerFormDraft } from "./serverFormDraft";
import {
  type LlmServerRow,
  LlmServersPageState,
  deleteLlmServer,
  lastTestBadgeOf,
  loadLlmServers,
  testLlmServerConnection,
} from "./llmServersPageState";

const EM_DASH = "—";

function formatInstant(value: string | null): string {
  if (value === null || value.length === 0) {
    return EM_DASH;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function ignoreRejection(): void {
  // Free functions never reject; this only keeps a surprise from going unhandled.
}

function openedByMenuTarget(): void {
  // The overflow trigger's click bubbles to the Menu.Target wrapper, which toggles the menu.
}

export type LlmServersPageProps = {
  state: LlmServersPageState;
};

export const LlmServersPage = observer(function LlmServersPage(
  props: LlmServersPageProps,
): React.JSX.Element {
  const { state } = props;
  const [deleteTarget, setDeleteTarget] = useState<LlmServerRow | null>(null);
  // The server form: open flag, target row (null = register) and the per-open draft.
  const [formOpen, setFormOpen] = useState(false);
  const [formTarget, setFormTarget] = useState<LlmServerRow | null>(null);
  const [formDraft, setFormDraft] = useState<ServerFormDraft | null>(null);
  // Select Models: open flag, target row and the per-open picker and draft.
  const [modelsOpen, setModelsOpen] = useState(false);
  const [modelsTarget, setModelsTarget] = useState<LlmServerRow | null>(null);
  const [modelsPicker, setModelsPicker] = useState<ModelPicker | null>(null);
  const [modelsDraft, setModelsDraft] = useState<EnabledModelsDraft | null>(null);
  // Set Embedding: open flag, target row and the per-open picker and draft.
  const [embeddingOpen, setEmbeddingOpen] = useState(false);
  const [embeddingTarget, setEmbeddingTarget] = useState<LlmServerRow | null>(null);
  const [embeddingPicker, setEmbeddingPicker] = useState<ModelPicker | null>(null);
  const [embeddingDraft, setEmbeddingDraft] = useState<EmbeddingDraft | null>(null);
  // Clear Embedding: the row awaiting confirmation.
  const [clearTarget, setClearTarget] = useState<LlmServerRow | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadLlmServers(state, controller.signal).catch(ignoreRejection);
    return () => {
      controller.abort();
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    };
  }, [state]);

  const currentSignal = (): AbortSignal | undefined => controllerRef.current?.signal;

  const cancelDelete = (): void => {
    setDeleteTarget(null);
  };

  const confirmDelete = (): void => {
    const target = deleteTarget;
    setDeleteTarget(null);
    if (target === null) {
      return;
    }
    void deleteLlmServer(state, target.id, currentSignal()).catch(ignoreRejection);
  };

  const testConnection = (row: LlmServerRow): void => {
    void testLlmServerConnection(state, row.id, currentSignal()).catch(ignoreRejection);
  };

  const openForm = (row: LlmServerRow | null): void => {
    setFormTarget(row);
    setFormDraft(new ServerFormDraft(row ?? undefined));
    setFormOpen(true);
  };

  const closeForm = (): void => {
    setFormOpen(false);
    setFormTarget(null);
    setFormDraft(null);
  };

  const onFormSaved = (): void => {
    closeForm();
    void loadLlmServers(state, currentSignal()).catch(ignoreRejection);
  };

  const openModels = (row: LlmServerRow): void => {
    setModelsTarget(row);
    setModelsPicker(new ModelPicker());
    setModelsDraft(new EnabledModelsDraft(row.enabled_model_names));
    setModelsOpen(true);
  };

  const closeModels = (): void => {
    setModelsOpen(false);
    setModelsTarget(null);
    setModelsPicker(null);
    setModelsDraft(null);
  };

  const onModelsSaved = (): void => {
    closeModels();
    void loadLlmServers(state, currentSignal()).catch(ignoreRejection);
  };

  const openEmbedding = (row: LlmServerRow): void => {
    setEmbeddingTarget(row);
    setEmbeddingPicker(new ModelPicker());
    setEmbeddingDraft(new EmbeddingDraft(row.embedding_model_name));
    setEmbeddingOpen(true);
  };

  const closeEmbedding = (): void => {
    setEmbeddingOpen(false);
    setEmbeddingTarget(null);
    setEmbeddingPicker(null);
    setEmbeddingDraft(null);
  };

  const onEmbeddingSaved = (): void => {
    closeEmbedding();
    void loadLlmServers(state, currentSignal()).catch(ignoreRejection);
  };

  const cancelClear = (): void => {
    setClearTarget(null);
  };

  const confirmClear = (): void => {
    const target = clearTarget;
    setClearTarget(null);
    if (target === null) {
      return;
    }
    void clearEmbeddingDesignation(state, target.id, currentSignal()).catch(ignoreRejection);
  };

  return (
    <Container size="lg" py="md">
      <Group justify="space-between" mb="md">
        <Title order={2}>LLM Servers</Title>
        <Button onClick={() => openForm(null)}>Register server</Button>
      </Group>

      {state.errorMessage !== null && (
        <Alert color="red" mb="md">
          {state.errorMessage}
        </Alert>
      )}

      {state.status !== "ready" ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Kind</Table.Th>
              <Table.Th>Base URL</Table.Th>
              <Table.Th>API key</Table.Th>
              <Table.Th>Enabled models</Table.Th>
              <Table.Th>Embedding model</Table.Th>
              <Table.Th>Last test</Table.Th>
              <Table.Th w={60} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {state.rows.map((row) => {
              const badge = lastTestBadgeOf(row);
              const testing = state.testingId === row.id;
              return (
                <Table.Tr key={row.id}>
                  <Table.Td>{row.name}</Table.Td>
                  <Table.Td>
                    <Badge variant="light" color={row.kind === "openai" ? "teal" : "blue"}>
                      {row.kind}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{row.base_url}</Table.Td>
                  <Table.Td>{row.has_api_key ? "Yes" : "No"}</Table.Td>
                  <Table.Td>{row.enabled_model_names.length}</Table.Td>
                  <Table.Td>
                    {row.embedding_model_name !== null ? (
                      <Group gap="xs" wrap="nowrap">
                        <Text size="sm">{row.embedding_model_name}</Text>
                        {row.embedding_dim !== null && (
                          <Text size="xs" c="dimmed">
                            {`${row.embedding_dim} dimensions`}
                          </Text>
                        )}
                      </Group>
                    ) : (
                      EM_DASH
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs" wrap="nowrap">
                      <Badge variant="light" color={badge.color}>
                        {badge.label}
                      </Badge>
                      <Text size="xs" c="dimmed">
                        {formatInstant(row.last_test_at)}
                      </Text>
                    </Group>
                  </Table.Td>
                  <Table.Td w={60}>
                    <Menu position="bottom-end" withinPortal>
                      <Menu.Target>
                        <Box component="span" display="inline-block">
                          <IconButton
                            icon={IconDots}
                            label={`Actions for ${row.name}`}
                            onClick={openedByMenuTarget}
                          />
                        </Box>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item onClick={() => openForm(row)}>Edit</Menu.Item>
                        <Menu.Item onClick={() => openModels(row)}>Select Models</Menu.Item>
                        <Menu.Item onClick={() => openEmbedding(row)}>Set Embedding</Menu.Item>
                        {row.embedding_model_name !== null && (
                          <Menu.Item onClick={() => setClearTarget(row)}>Clear Embedding</Menu.Item>
                        )}
                        <Menu.Item disabled={testing} onClick={() => testConnection(row)}>
                          {testing ? "Testing…" : "Test connection"}
                        </Menu.Item>
                        <Menu.Item color="red" onClick={() => setDeleteTarget(row)}>
                          Delete
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      )}

      <ConfirmModal
        opened={deleteTarget !== null}
        title={deleteTarget !== null ? `Delete ${deleteTarget.name}?` : "Delete LLM server?"}
        consequence="The registration and its enabled-model set are removed and cannot be restored."
        confirmLabel="Delete"
        confirmColor="red"
        onCancel={cancelDelete}
        onConfirm={confirmDelete}
      />

      <ConfirmModal
        opened={clearTarget !== null}
        title="Clear the embedding model?"
        consequence="With no embedding model designated, every semantic feature stops working until one is designated again."
        confirmLabel="Clear"
        confirmColor="red"
        onCancel={cancelClear}
        onConfirm={confirmClear}
      />

      {formOpen && formDraft !== null && (
        <ServerFormModal
          key={formTarget?.id ?? "register"}
          draft={formDraft}
          onClose={closeForm}
          onSaved={onFormSaved}
        />
      )}

      {modelsOpen && modelsTarget !== null && modelsPicker !== null && modelsDraft !== null && (
        <EnabledModelsModal
          key={modelsTarget.id}
          picker={modelsPicker}
          draft={modelsDraft}
          serverId={modelsTarget.id}
          serverName={modelsTarget.name}
          onClose={closeModels}
          onSaved={onModelsSaved}
        />
      )}

      {embeddingOpen &&
        embeddingTarget !== null &&
        embeddingPicker !== null &&
        embeddingDraft !== null && (
          <EmbeddingModal
            key={embeddingTarget.id}
            picker={embeddingPicker}
            draft={embeddingDraft}
            serverId={embeddingTarget.id}
            serverName={embeddingTarget.name}
            onClose={closeEmbedding}
            onSaved={onEmbeddingSaved}
          />
        )}
    </Container>
  );
});

/** The `/llm-servers` route element: owns the page store, never via `useMemo`. */
export function LlmServersRoute(): React.JSX.Element {
  const [state] = useState(() => new LlmServersPageState());
  return <LlmServersPage state={state} />;
}
