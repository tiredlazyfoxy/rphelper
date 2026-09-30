// The admin application the gate mounts: the shell state, the shell, and the flat
// route table.
import type * as React from "react";
import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { AdminShell } from "./AdminShell";
import { AdminShellState } from "./adminShellState";
import { DatabaseRoute } from "./DatabasePage";
import { LlmServersRoute } from "./LlmServersPage";
import { NotFoundPage } from "./NotFoundPage";
import { UsersPage } from "./UsersPage";

export function AdminApp(): React.JSX.Element {
  const [shell] = useState(() => new AdminShellState());

  return (
    <AdminShell shell={shell}>
      <Routes>
        <Route path="/" element={<UsersPage />} />
        <Route path="/llm-servers" element={<LlmServersRoute />} />
        <Route path="/database" element={<DatabaseRoute />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AdminShell>
  );
}
