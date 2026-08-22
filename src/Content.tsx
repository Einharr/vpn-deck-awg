import { ButtonItem, PanelSection, PanelSectionRow, showModal, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FaBug, FaChevronRight, FaNetworkWired, FaPlus, FaPowerOff, FaShieldAlt, FaSyncAlt, FaWrench } from "react-icons/fa";
import type { Dashboard, DiagnosticProbe, Profile, Settings } from "./types";
import { activateConfig, clearErrors, deleteConfig, diagnoseConnectivity, getDashboard, getServiceLogTail, repairSymlinks, stopAll, stopConfig, updateSettings } from "./api";
import { activeCardStyle, cardStyle, mutedStyle, protocolTone, shortEndpoint } from "./styles";
import { StatusPill } from "./components/StatusPill";
import { ImportModal } from "./components/ImportModal";
import { LogModal } from "./components/LogModal";
import { ProfileDetailsModal } from "./components/ProfileDetailsModal";

export function Content() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [busyProfile, setBusyProfile] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DiagnosticProbe[] | null>(null);
  const [diagnosticsBusy, setDiagnosticsBusy] = useState(false);

  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    try {
      const data = await getDashboard();
      if (data.success) setDashboard(data);
    } catch (error) {
      if (showSpinner) toaster.toast({ title: "Не удалось обновить состояние", body: String(error) });
    } finally {
      if (showSpinner) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh(true);
    const timer = window.setInterval(() => {
      if (!busyProfile) void refresh(false);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh, busyProfile]);

  const profiles = useMemo(() => {
    const items = dashboard?.profiles ?? [];
    return [...items].sort((a, b) => Number(b.active) - Number(a.active) || a.name.localeCompare(b.name));
  }, [dashboard]);

  const toggleProfile = useCallback(async (profile: Profile, enabled: boolean) => {
    setBusyProfile(profile.name);
    try {
      const result = enabled
        ? await activateConfig({ config_name: profile.name })
        : await stopConfig({ config_name: profile.name });
      if (!result.success) {
        toaster.toast({ title: enabled ? "VPN не подключён" : "VPN не отключён", body: result.error ?? "Неизвестная ошибка" });
      } else {
        toaster.toast({ title: enabled ? "VPN подключён" : "VPN отключён", body: profile.name });
      }
    } catch (error) {
      toaster.toast({ title: "Ошибка VPN", body: String(error) });
    } finally {
      setBusyProfile(null);
      await refresh(false);
    }
  }, [refresh]);

  const removeProfile = useCallback(async (name: string) => {
    const result = await deleteConfig({ name });
    if (!result.success) {
      toaster.toast({ title: "Не удалось удалить профиль", body: result.error ?? "Неизвестная ошибка" });
      return;
    }
    toaster.toast({ title: "Профиль удалён", body: name });
    await refresh(false);
  }, [refresh]);

  const changeSetting = useCallback(async (key: keyof Settings, value: boolean) => {
    try {
      await updateSettings({ [key]: value });
      await refresh(false);
    } catch (error) {
      toaster.toast({ title: "Не удалось сохранить настройку", body: String(error) });
    }
  }, [refresh]);

  const runDiagnostics = useCallback(async () => {
    setDiagnosticsBusy(true);
    try {
      const result = await diagnoseConnectivity();
      setDiagnostics(result);
      const ok = result.filter((item) => item.ok).length;
      toaster.toast({ title: "Диагностика завершена", body: `${ok}/${result.length} проверок успешно` });
    } catch (error) {
      toaster.toast({ title: "Ошибка диагностики", body: String(error) });
    } finally {
      setDiagnosticsBusy(false);
    }
  }, []);

  const showLog = useCallback(async () => {
    try {
      const result = await getServiceLogTail({ lines: 100 });
      showModal(<LogModal log={result.log} />);
    } catch (error) {
      toaster.toast({ title: "Не удалось прочитать лог", body: String(error) });
    }
  }, []);

  const activeProfile = profiles.find((profile) => profile.active);
  const runtimeOk = dashboard?.runtime.ok ?? true;

  return (
    <>
      <PanelSection title="VPN Deck AWG">
        <PanelSectionRow>
          <div style={{ ...cardStyle, padding: "14px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px" }}>
              <div>
                <div style={{ fontSize: "17px", fontWeight: 700 }}>
                  {activeProfile ? activeProfile.name : "VPN отключён"}
                </div>
                <div style={{ ...mutedStyle, marginTop: "3px" }}>
                  {activeProfile
                    ? `${activeProfile.protocol_label} · ${shortEndpoint(activeProfile.endpoint)}`
                    : `${profiles.length} профил${profiles.length === 1 ? "ь" : "ей"} доступно`}
                </div>
              </div>
              <StatusPill active={!!activeProfile} />
            </div>
            {!runtimeOk && (
              <div style={{ marginTop: "10px", fontSize: "12px", color: "#e6a15c" }}>
                Runtime неполный: {dashboard?.runtime.missing.join(", ")}
              </div>
            )}
          </div>
        </PanelSectionRow>

        {dashboard && dashboard.active_count > 0 && (
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={async () => {
                await stopAll({ only_managed: true });
                await refresh(false);
              }}
            >
              <FaPowerOff /> Отключить все VPN
            </ButtonItem>
          </PanelSectionRow>
        )}
      </PanelSection>

      <PanelSection title="Профили">
        {profiles.length === 0 && (
          <PanelSectionRow>
            <div style={{ ...cardStyle, textAlign: "center", padding: "18px" }}>
              <FaShieldAlt style={{ opacity: 0.5, marginBottom: "8px" }} />
              <div style={{ fontWeight: 600 }}>Профилей пока нет</div>
              <div style={{ ...mutedStyle, marginTop: "5px" }}>Импортируйте WireGuard или AmneziaWG .conf</div>
            </div>
          </PanelSectionRow>
        )}

        {profiles.map((profile) => (
          <PanelSectionRow key={profile.interface}>
            <div style={profile.active ? activeCardStyle : cardStyle}>
              <ToggleField
                label={profile.name}
                description={`${profile.protocol_label} · ${shortEndpoint(profile.endpoint)}`}
                checked={profile.active}
                disabled={busyProfile !== null || !profile.valid || !runtimeOk}
                onChange={(enabled: boolean) => void toggleProfile(profile, enabled)}
              />
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "7px", alignItems: "center" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, color: protocolTone(profile.protocol) }}>
                  {profile.protocol_label}
                </span>
                <span style={mutedStyle}>{profile.full_tunnel ? "Full tunnel" : "Split tunnel"}</span>
                {profile.address[0] && <span style={mutedStyle}>{profile.address[0]}</span>}
              </div>
              {!profile.valid && (
                <div style={{ marginTop: "7px", color: "#df7777", fontSize: "12px" }}>
                  Конфиг повреждён: {profile.errors[0] ?? "ошибка формата"}
                </div>
              )}
              <ButtonItem
                layout="below"
                onClick={() => showModal(<ProfileDetailsModal profile={profile} onDelete={removeProfile} />)}
              >
                Подробнее <FaChevronRight />
              </ButtonItem>
            </div>
          </PanelSectionRow>
        ))}

        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => showModal(<ImportModal onImported={() => refresh(false)} />)}>
            <FaPlus /> Добавить профиль
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={refreshing} onClick={() => void refresh(true)}>
            <FaSyncAlt /> {refreshing ? "Обновление…" : "Обновить состояние"}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Поведение">
        <PanelSectionRow>
          <ToggleField
            label="Один VPN одновременно"
            description="При подключении нового профиля безопасно отключать предыдущий managed VPN"
            checked={dashboard?.settings.exclusive_mode ?? true}
            onChange={(value: boolean) => void changeSetting("exclusive_mode", value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Автовосстановление после обновления SteamOS"
            description="Восстанавливать системные ссылки на профили при запуске Decky"
            checked={dashboard?.settings.auto_repair ?? true}
            onChange={(value: boolean) => void changeSetting("auto_repair", value)}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Диагностика и обслуживание">
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={diagnosticsBusy} onClick={() => void runDiagnostics()}>
            <FaNetworkWired /> {diagnosticsBusy ? "Проверка…" : "Проверить соединение"}
          </ButtonItem>
        </PanelSectionRow>

        {diagnostics?.map((probe) => (
          <PanelSectionRow key={`${probe.kind}-${probe.target}`}>
            <div style={{ ...cardStyle, borderLeft: `3px solid ${probe.ok ? "#6cc56c" : "#df7777"}` }}>
              <strong>{probe.name}</strong>
              <div style={{ ...mutedStyle, marginTop: "3px" }}>{probe.detail}</div>
            </div>
          </PanelSectionRow>
        ))}

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={async () => {
              const result = await repairSymlinks();
              toaster.toast({ title: "Профили проверены", body: `Восстановлено: ${result.repaired}/${result.total}` });
              await refresh(false);
            }}
          >
            <FaWrench /> Восстановить профили
          </ButtonItem>
        </PanelSectionRow>

        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => void showLog()}>
            <FaBug /> Лог подключения
          </ButtonItem>
        </PanelSectionRow>

        {(dashboard?.error_count ?? 0) > 0 && (
          <PanelSectionRow>
            <div style={{ ...cardStyle, borderColor: "rgba(223,119,119,.45)" }}>
              <strong>Последняя ошибка</strong>
              <div style={{ ...mutedStyle, marginTop: "5px" }}>{dashboard?.last_error?.message}</div>
              <ButtonItem
                layout="below"
                onClick={async () => {
                  await clearErrors();
                  await refresh(false);
                }}
              >
                Очистить историю ошибок
              </ButtonItem>
            </div>
          </PanelSectionRow>
        )}

        <PanelSectionRow>
          <div style={mutedStyle}>
            Runtime: {dashboard?.runtime.binaries["amneziawg-go"]?.version ?? "—"} · tools {dashboard?.runtime.binaries.awg?.version ?? "—"}
          </div>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}
