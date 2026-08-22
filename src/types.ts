export interface PeerStatus {
  public_key: string;
  endpoint: string | null;
  latest_handshake: string | null;
  transfer_rx: string | null;
  transfer_tx: string | null;
}

export interface Profile {
  name: string;
  interface: string;
  active: boolean;
  status: "active" | "inactive" | "unknown";
  protocol: string;
  protocol_label: string;
  valid: boolean;
  warnings: string[];
  errors: string[];
  address: string[];
  dns: string[];
  peer_count: number;
  endpoint: string | null;
  endpoints: string[];
  allowed_ips: string[];
  full_tunnel: boolean;
  has_ipv6: boolean;
  persistent_keepalive: boolean;
  mtu: string | null;
  peers: PeerStatus[];
}

export interface RuntimeBinary {
  path: string | null;
  version: string | null;
  runtime_version: string | null;
}

export interface RuntimeHealth {
  ok: boolean;
  missing: string[];
  binaries: Record<string, RuntimeBinary>;
}

export interface Settings {
  exclusive_mode: boolean;
  auto_repair: boolean;
  last_connected: string | null;
}

export interface VPNError {
  timestamp: number;
  operation: string;
  error_type: string;
  message: string;
}

export interface Dashboard {
  success: boolean;
  profiles: Profile[];
  active_count: number;
  active_profiles: string[];
  settings: Settings;
  runtime: RuntimeHealth;
  error_count: number;
  last_error: VPNError | null;
}

export interface OperationResult {
  success: boolean;
  error?: string | null;
  interface?: string;
  stopped?: string[];
}

export interface Analysis {
  valid: boolean;
  protocol: string;
  protocol_label: string;
  errors: string[];
  warnings: string[];
  address: string[];
  dns: string[];
  peer_count: number;
  endpoints: string[];
  allowed_ips: string[];
  full_tunnel: boolean;
  has_ipv6: boolean;
  persistent_keepalive: boolean;
  mtu: string | null;
  suggested_name?: string;
}

export interface InspectResult {
  success: boolean;
  analysis: Analysis;
  error?: string | null;
}

export interface ImportResult extends OperationResult {
  exists?: boolean;
  config_name?: string;
  analysis?: Analysis;
}

export interface DiagnosticProbe {
  name: string;
  kind: string;
  target: string;
  ok: boolean;
  detail: string;
  latency_ms: number | null;
}
