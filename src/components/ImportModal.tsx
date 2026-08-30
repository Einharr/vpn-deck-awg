import { DialogBody, DialogButton, DialogFooter, DialogHeader, ModalRoot, TextField, showModal } from "@decky/ui";
import { FileSelectionType, openFilePicker, toaster } from "@decky/api";
import { useState } from "react";
import type { Analysis } from "../types";
import { importConfig, inspectConfig } from "../api";
import { CONFIG_NAME_MAX_LEN, cardStyle, mutedStyle, protocolTone, validateName } from "../styles";

interface ImportModalProps {
  closeModal?: () => void;
  onImported: () => Promise<void>;
  initialPath?: string;
  initialAnalysis?: Analysis | null;
  initialError?: string | null;
}

function nameFromPath(path: string, analysis?: Analysis | null) {
  const filename = path.split("/").pop()?.replace(/\.conf$/i, "") ?? "vpn";
  return (analysis?.suggested_name || filename).slice(0, CONFIG_NAME_MAX_LEN);
}

export function ImportModal({
  closeModal,
  onImported,
  initialPath = "",
  initialAnalysis = null,
  initialError = null,
}: ImportModalProps) {
  const [path] = useState(initialPath);
  const [name, setName] = useState(() => nameFromPath(initialPath, initialAnalysis));
  const [analysis] = useState<Analysis | null>(initialAnalysis);
  const [busy, setBusy] = useState(false);
  const [inspectError] = useState<string | null>(initialError);

  const pickFile = async () => {
    // Decky's picker is itself a ModalRoot. Keeping this modal alive while
    // opening it creates a nested modal that is dimmed and loses controller
    // focus in Game Mode. Close first, then open the system picker.
    closeModal?.();
    await new Promise((resolve) => window.setTimeout(resolve, 80));

    try {
      const selected = await openFilePicker(
        FileSelectionType.FILE,
        "/home/deck/Downloads",
        true,
        true,
        undefined,
        ["conf"],
      );
      const inspected = await inspectConfig({ path: selected.realpath });
      showModal(
        <ImportModal
          onImported={onImported}
          initialPath={selected.realpath}
          initialAnalysis={inspected.analysis ?? null}
          initialError={inspected.success ? null : inspected.error ?? "Конфиг не прошёл проверку"}
        />,
      );
    } catch (error) {
      const message = String(error);
      // Canceling Decky's picker is normal navigation, not an import error.
      if (!message.toLowerCase().includes("cancel")) {
        toaster.toast({ title: "Не удалось открыть файл", body: message });
      }
    }
  };

  const doImport = async () => {
    const nameError = validateName(name);
    if (nameError) {
      toaster.toast({ title: "Имя профиля", body: nameError });
      return;
    }
    if (!path || !analysis?.valid) return;

    setBusy(true);
    try {
      const result = await importConfig({ name: name.trim(), path, overwrite: false });
      if (!result.success) {
        toaster.toast({
          title: result.exists ? "Такой профиль уже есть" : "Не удалось импортировать",
          body: result.error ?? "Неизвестная ошибка",
        });
        return;
      }
      toaster.toast({ title: "Профиль добавлен", body: analysis.protocol_label });
      await onImported();
      closeModal?.();
    } catch (error) {
      toaster.toast({ title: "Ошибка импорта", body: String(error) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <DialogHeader>{path ? "Проверка VPN-профиля" : "Добавить VPN-профиль"}</DialogHeader>
      <DialogBody>
        {!path && (
          <div style={{ ...mutedStyle, marginBottom: "10px" }}>
            Поддерживаются WireGuard, AmneziaWG 1.x/2/3 и Amnezia vpn:// / JSON, сохранённые в файл.
          </div>
        )}

        <DialogButton onClick={pickFile} disabled={busy}>
          {path ? "Выбрать другой файл" : "Выбрать .conf"}
        </DialogButton>

        {path && <div style={{ ...mutedStyle, marginTop: "8px", wordBreak: "break-all" }}>{path}</div>}

        {analysis && (
          <div style={{ ...cardStyle, marginTop: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
              <strong style={{ color: protocolTone(analysis.protocol) }}>{analysis.protocol_label}</strong>
              <span style={mutedStyle}>{analysis.peer_count} peer</span>
            </div>
            {analysis.source_format && (
              <div style={{ ...mutedStyle, marginTop: "4px" }}>Источник: {analysis.source_format}</div>
            )}
            <div style={{ ...mutedStyle, marginTop: "7px" }}>
              {analysis.endpoints[0] ?? "Endpoint не указан"}
            </div>
            <div style={{ ...mutedStyle, marginTop: "3px" }}>
              {analysis.full_tunnel ? "Полный туннель" : "Split tunnel"}
              {analysis.has_ipv6 ? " · IPv6" : ""}
              {analysis.persistent_keepalive ? " · Keepalive" : ""}
            </div>
            {analysis.warnings.map((warning) => (
              <div key={warning} style={{ ...mutedStyle, marginTop: "5px" }}>⚠ {warning}</div>
            ))}
          </div>
        )}

        {(inspectError || (analysis && !analysis.valid)) && (
          <div style={{ ...cardStyle, marginTop: "12px", borderColor: "rgba(220,90,90,.55)" }}>
            <strong>Конфиг не принят</strong>
            {inspectError && <div style={{ ...mutedStyle, marginTop: "6px" }}>{inspectError}</div>}
            {analysis?.errors.map((error) => (
              <div key={error} style={{ ...mutedStyle, marginTop: "5px" }}>{error}</div>
            ))}
          </div>
        )}

        {analysis?.valid && (
          <div style={{ marginTop: "12px" }}>
            <TextField
              label="Имя профиля"
              value={name}
              onChange={(event: { target: { value: string } }) => setName(event.target.value)}
              description="До 12 символов; имя интерфейса создаётся автоматически"
            />
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        {analysis?.valid && (
          <DialogButton onClick={doImport} disabled={busy || !!validateName(name)}>
            {busy ? "Обработка…" : "Добавить"}
          </DialogButton>
        )}
        <DialogButton onClick={closeModal}>Отмена</DialogButton>
      </DialogFooter>
    </ModalRoot>
  );
}
