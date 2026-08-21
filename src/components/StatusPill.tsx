export function StatusPill({ active }: { active: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        fontSize: "12px",
        fontWeight: 600,
        opacity: active ? 1 : 0.72,
      }}
    >
      <span
        style={{
          width: "8px",
          height: "8px",
          borderRadius: "50%",
          background: active ? "#6cc56c" : "#858b92",
          boxShadow: active ? "0 0 8px rgba(108,197,108,.45)" : "none",
        }}
      />
      {active ? "Подключено" : "Отключено"}
    </span>
  );
}
