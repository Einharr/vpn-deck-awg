import { DialogBody, DialogButton, DialogFooter, DialogHeader, ModalRoot } from "@decky/ui";

export function LogModal({ log, closeModal }: { log: string; closeModal?: () => void }) {
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <DialogHeader>Лог awg-quick</DialogHeader>
      <DialogBody>
        <pre style={{ fontSize: "11px", whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: "55vh", overflow: "auto" }}>
          {log || "Лог пуст"}
        </pre>
      </DialogBody>
      <DialogFooter><DialogButton onClick={closeModal}>Закрыть</DialogButton></DialogFooter>
    </ModalRoot>
  );
}
