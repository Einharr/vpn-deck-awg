import { DialogBody, DialogButton, DialogFooter, DialogHeader, ModalRoot } from "@decky/ui";
import { useState } from "react";
import { FaTrash } from "react-icons/fa";
import type { Profile } from "../types";
import { cardStyle, mutedStyle } from "../styles";
import { StatusPill } from "./StatusPill";

export function ProfileDetailsModal({
  profile,
  closeModal,
  onDelete,
}: {
  profile: Profile;
  closeModal?: () => void;
  onDelete: (name: string) => Promise<void>;
}) {
  const [deleting, setDeleting] = useState(false);
  const peer = profile.peers[0];

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await onDelete(profile.name);
      closeModal?.();
    } finally {
      setDeleting(false);
    }
  };

  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <DialogHeader>{profile.name}</DialogHeader>
      <DialogBody>
        <div style={{ ...cardStyle, marginBottom: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "8px" }}>
            <strong>{profile.protocol_label}</strong>
            <StatusPill active={profile.active} />
          </div>
          <div style={{ ...mutedStyle, marginTop: "8px" }}>{profile.interface}</div>
        </div>

        <div style={{ display: "grid", gap: "10px", fontSize: "13px" }}>
          <div><strong>Endpoint</strong><div style={mutedStyle}>{profile.endpoint ?? "—"}</div></div>
          <div><strong>Адрес</strong><div style={mutedStyle}>{profile.address.join(", ") || "—"}</div></div>
          <div><strong>DNS</strong><div style={mutedStyle}>{profile.dns.join(", ") || "Системный"}</div></div>
          <div><strong>Маршрутизация</strong><div style={mutedStyle}>{profile.full_tunnel ? "Весь трафик через VPN" : "Split tunnel"}</div></div>
          {peer && (
            <>
              <div><strong>Последний handshake</strong><div style={mutedStyle}>{peer.latest_handshake ?? "—"}</div></div>
              <div><strong>Трафик</strong><div style={mutedStyle}>↓ {peer.transfer_rx ?? "—"} · ↑ {peer.transfer_tx ?? "—"}</div></div>
            </>
          )}
          {profile.warnings.length > 0 && (
            <div>
              <strong>Предупреждения</strong>
              {profile.warnings.map((warning) => <div key={warning} style={mutedStyle}>{warning}</div>)}
            </div>
          )}
        </div>
      </DialogBody>
      <DialogFooter>
        <DialogButton onClick={handleDelete} disabled={deleting}>
          <FaTrash /> {deleting ? "Удаление…" : "Удалить профиль"}
        </DialogButton>
        <DialogButton onClick={closeModal}>Закрыть</DialogButton>
      </DialogFooter>
    </ModalRoot>
  );
}
