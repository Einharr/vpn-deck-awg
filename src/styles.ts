import type { CSSProperties } from "react";

export const CONFIG_NAME_MAX_LEN = 12;
const CONFIG_NAME_REGEX = /^[a-zA-Z0-9_=+.-]+$/;

export const cardStyle: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  borderRadius: "8px",
  padding: "12px",
  background: "rgba(255, 255, 255, 0.045)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
};

export const activeCardStyle: CSSProperties = {
  ...cardStyle,
  border: "1px solid rgba(102, 192, 244, 0.6)",
  background: "rgba(102, 192, 244, 0.08)",
};

export const mutedStyle: CSSProperties = {
  opacity: 0.68,
  fontSize: "12px",
  lineHeight: 1.35,
};

export function protocolTone(protocol?: string | null): string {
  if (!protocol) return "#b8b8b8";
  if (protocol === "awg-3.1" || protocol === "awg-3.0") return "#66c0f4";
  if (protocol === "awg-2.0") return "#86b342";
  if (protocol.startsWith("awg-")) return "#c7a96b";
  return "#b8b8b8";
}

export function shortEndpoint(endpoint: string | null): string {
  if (!endpoint) return "Endpoint не указан";
  return endpoint.length > 42 ? `${endpoint.slice(0, 39)}…` : endpoint;
}

export function validateName(name: string): string | null {
  const trimmed = name.trim();
  if (!trimmed) return "Укажите имя профиля";
  if (trimmed.length > CONFIG_NAME_MAX_LEN) return `Максимум ${CONFIG_NAME_MAX_LEN} символов`;
  if (!CONFIG_NAME_REGEX.test(trimmed)) return "Допустимы a-z, 0-9 и _ = + . -";
  return null;
}