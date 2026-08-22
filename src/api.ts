import { callable } from "@decky/api";
import type { Dashboard, OperationResult, InspectResult, ImportResult, Settings, DiagnosticProbe } from "./types";

export const getDashboard = callable<[], Dashboard>("get_dashboard");
export const activateConfig = callable<[{ config_name: string }], OperationResult>("vpn_activate_config");
export const stopConfig = callable<[{ config_name: string }], OperationResult>("vpn_stop_config");
export const stopAll = callable<[{ only_managed: boolean }], OperationResult>("vpn_stop_all");
export const inspectConfig = callable<[{ path: string }], InspectResult>("inspect_vpn_config");
export const importConfig = callable<[
  { name: string; path: string; overwrite: boolean },
], ImportResult>("import_vpn_config");
export const deleteConfig = callable<[{ name: string }], OperationResult>("delete_vpn_config");
export const repairSymlinks = callable<[], { total: number; repaired: number }>("repair_symlinks");
export const updateSettings = callable<[
  Record<string, boolean | string | null>,
], { success: boolean; settings: Settings }>("update_settings");
export const diagnoseConnectivity = callable<[], DiagnosticProbe[]>("diagnose_connectivity");
export const getServiceLogTail = callable<[{ lines: number }], { success: boolean; log: string }>("get_service_log_tail");
export const clearErrors = callable<[], boolean>("clear_errors");
