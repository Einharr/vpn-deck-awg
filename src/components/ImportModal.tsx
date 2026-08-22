import { DialogBody, DialogButton, DialogFooter, DialogHeader, ModalRoot, TextField } from "@decky/ui";
import { FileSelectionType, openFilePicker, toaster } from "@decky/api";
import { useState } from "react";
import type { Analysis } from "../types";
import { importConfig, inspectConfig } from "../api";
import { CONFIG_NAME_MAX_LEN, cardStyle, mutedStyle, protocolTone, validateName } from "../styles";

export function ImportModal({ closeModal, onImported }: { closeModal?: () => void; onImported: () => Promise<void> }) {
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [inspectError, setInspectError] = useState<string | null>(null);

  const pickFile = async () => {
    try {
      const selected = await openFilePicker(
        FileSelectionType.FILE,
        "/home/deck/Downloads",
        true,
        true,
        undefined,
        ["conf"],
      );
      setPath(selected.realpath);
      setAnalysis(null);
      setInspectError(null);
      setBusy(true);
      const inspected = await inspectConfig({ path: selected.realpath });
      if (inspected.analysis) {
        setAnalysis(inspected.analysis);
        const filename = selected.realpath.split("/").pop()?.replace(/\.conf$/i, "") ?? "vpn";
        setName((inspected.analysis.suggested_name || filename).slice(0, CONFIG_NAME_MAX_LEN));
      }
      if (!inspected.success) setInspectError(inspected.error ?? "Конфиг не прошёл проверку");
    } catch (error) {
      console.error(error);
    } finally {
      setBusy(false);
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
      <DialogHeader>Добавить VPN-профиль</DialogHeader>
      <DialogBody>
        <DialogButton onClick={pickFile} disabled={busy}>
          {path ? "Выбрать другой .conf" : "Выбрать .conf"}
        </DialogButton>

        {path && <div style={{ ...mutedStyle, marginTop: "8px", wordBreak: "break-all" }}>{path}</div>}

        {analysis && (
          <div style={{ ...cardStyle, marginTop: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
              <strong style={{ color: protocolTone(analysis.protocol) }}>{analysis.protocol_label}</strong>
              <span style={mutedStyle}>{analysis.peer_count} peer</span>
            </div>
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

        {inspectError && (
          <div style={{ ...cardStyle, marginTop: "12px", borderColor: "rgba(220,90,90,.55)" }}>
            <strong>Конфиг не принят</strong>
            <div style={{ ...mutedStyle, marginTop: "6px" }}>{inspectError}</div>
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
        <DialogButton onClick={doImport} disabled={busy || !analysis?.valid || !!validateName(name)}>
          {busy ? "Обработка…" : "Добавить"}
        </DialogButton>
        <DialogButton onClick={closeModal}>Отмена</DialogButton>
      </DialogFooter>
    </ModalRoot>
  );
}
