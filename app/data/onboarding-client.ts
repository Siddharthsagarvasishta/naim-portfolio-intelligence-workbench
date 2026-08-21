import { publicApiUrl } from "./api-environment";
import { normalizeApiOrigin } from "./api-origin.mjs";

const API_BASE = normalizeApiOrigin(publicApiUrl());

export interface OnboardingSourceDescriptor {
  source_id: string;
  kind: "csv" | "xlsx" | "parquet" | "json" | "sqlite" | "duckdb" | "postgresql";
  display_name: string;
  relative_path?: string;
  size_bytes?: number;
  sha256?: string;
  table?: string;
  sheet?: string | number;
  url_env?: string;
}

export interface OnboardingContractField {
  name: string;
  data_type: string;
  required: boolean;
  non_negative: boolean;
  allowed_values: string[];
  description: string;
}

export interface OnboardingContract {
  contract_id: string;
  version: string;
  description: string;
  unique_key: string[];
  fields: OnboardingContractField[];
}

export interface OnboardingPreview {
  source: OnboardingSourceDescriptor;
  sample_row_count: number;
  sample_limit: number;
  columns: Array<{
    name: string;
    inferred_type: string;
    confidence: number;
    null_count_in_sample: number;
    distinct_count_in_sample: number;
  }>;
  rows: Array<Record<string, unknown>>;
  suggested_mappings: Record<string, Record<string, string>>;
}

export interface OnboardingValidation {
  source: OnboardingSourceDescriptor;
  validation: {
    contract_id: string;
    contract_version: string;
    source_rows: number;
    valid_rows: number;
    invalid_rows: number;
    validation_error_count: number;
    error_preview_count: number;
    error_preview_truncated: boolean;
    error_rate: number;
    max_error_rate: number;
    passed: boolean;
  };
  error_preview: Array<Record<string, unknown>>;
  valid_row_preview: Array<Record<string, unknown>>;
  invalid_row_preview: Array<Record<string, unknown>>;
}

export interface OnboardingProfile {
  profile_id: string;
  version: number;
  approval_state: string;
  active: boolean;
  contract_id: string;
  contract_version: string;
  draft_validation?: OnboardingValidation["validation"];
  last_run?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface OnboardingRun {
  run_id: string;
  profile_id: string;
  profile_version: number;
  profile_approval_state: string;
  profile_active: boolean;
  loaded_to_active_analytics: boolean;
  validation: OnboardingValidation["validation"];
  reconciliation: {
    source_rows: number;
    loaded_rows: number;
    quarantined_rows: number;
    row_balance_delta: number;
    balanced: boolean;
    numeric_totals?: Array<Record<string, unknown>>;
  };
  outputs: Record<string, string>;
  output_hashes: Record<string, string>;
  [key: string]: unknown;
}

export class OnboardingClientError extends Error {
  requestId: string;
  stage: string;

  constructor(message: string, stage: string, requestId: string) {
    super(message);
    this.name = "OnboardingClientError";
    this.stage = stage;
    this.requestId = requestId;
  }
}

function requestId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `NAIM-ONBOARD-${globalThis.crypto.randomUUID()}`;
  }
  return `NAIM-ONBOARD-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function errorDetail(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (!isRecord(value)) return null;
  const detail = value.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (isRecord(detail)) {
    const nested = detail.message ?? detail.error;
    return typeof nested === "string" && nested.trim() ? nested.trim() : null;
  }
  return null;
}

async function onboardingJson<T>(
  endpoint: string,
  stage: string,
  init: RequestInit = {},
): Promise<T> {
  const clientRequestId = requestId();
  const response = await fetch(`${API_BASE}/api/v1/${endpoint}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "X-Request-ID": clientRequestId,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
    cache: "no-store",
    signal: AbortSignal.timeout(60000),
  });
  const serverRequestId = response.headers.get("X-Request-ID") ?? clientRequestId;
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // The status code remains a truthful fallback when no JSON body is returned.
  }
  if (!response.ok) {
    throw new OnboardingClientError(
      errorDetail(payload) ?? `${endpoint} returned ${response.status}`,
      stage,
      serverRequestId,
    );
  }
  if (payload === null) {
    throw new OnboardingClientError(
      `${endpoint} returned no JSON payload`,
      stage,
      serverRequestId,
    );
  }
  return payload as T;
}

function base64Bytes(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

export async function loadOnboardingContracts(): Promise<OnboardingContract[]> {
  const payload = await onboardingJson<{ data?: unknown }>(
    "data-onboarding/contracts",
    "loading_contracts",
  );
  if (!Array.isArray(payload.data) || payload.data.length === 0) {
    throw new OnboardingClientError(
      "The onboarding service returned no governed data contracts.",
      "loading_contracts",
      "not-returned",
    );
  }
  return payload.data as OnboardingContract[];
}

export async function uploadOnboardingSource(
  file: File,
): Promise<OnboardingSourceDescriptor> {
  if (file.size === 0) {
    throw new OnboardingClientError("The selected file is empty.", "uploading_source", "client-validation");
  }
  if (file.size > 50 * 1024 * 1024) {
    throw new OnboardingClientError(
      "The selected file exceeds the 50 MB local onboarding limit.",
      "uploading_source",
      "client-validation",
    );
  }
  const content = base64Bytes(new Uint8Array(await file.arrayBuffer()));
  return onboardingJson<OnboardingSourceDescriptor>(
    "data-onboarding/sources/upload",
    "uploading_source",
    {
      method: "POST",
      body: JSON.stringify({ filename: file.name, content_base64: content }),
    },
  );
}

export async function previewOnboardingSource(
  source: OnboardingSourceDescriptor,
): Promise<OnboardingPreview> {
  return onboardingJson<OnboardingPreview>(
    "data-onboarding/preview",
    "previewing_source",
    {
      method: "POST",
      body: JSON.stringify({ source, sample_rows: 50 }),
    },
  );
}

export async function validateOnboardingSource(
  source: OnboardingSourceDescriptor,
  contractId: string,
  mapping: Record<string, string>,
): Promise<OnboardingValidation> {
  await onboardingJson<Record<string, unknown>>(
    "data-onboarding/map",
    "validating_mapping",
    {
      method: "POST",
      body: JSON.stringify({
        source,
        contract_id: contractId,
        mapping,
        transformations: {},
      }),
    },
  );
  return onboardingJson<OnboardingValidation>(
    "data-onboarding/validate",
    "validating_source",
    {
      method: "POST",
      body: JSON.stringify({
        source,
        contract_id: contractId,
        mapping,
        transformations: {},
        max_error_rate: 0,
      }),
    },
  );
}

export async function createOnboardingProfile(
  profileId: string,
  source: OnboardingSourceDescriptor,
  contractId: string,
  mapping: Record<string, string>,
): Promise<OnboardingProfile> {
  return onboardingJson<OnboardingProfile>(
    "data-onboarding/profiles",
    "saving_profile",
    {
      method: "POST",
      body: JSON.stringify({
        profile_id: profileId,
        source,
        contract_id: contractId,
        mapping,
        transformations: {},
        max_error_rate: 0,
      }),
    },
  );
}

export async function runOnboardingProfile(
  profileId: string,
  source: OnboardingSourceDescriptor,
  expectedVersion: number,
): Promise<OnboardingRun> {
  return onboardingJson<OnboardingRun>(
    "data-onboarding/load",
    "creating_governed_namespace",
    {
      method: "POST",
      body: JSON.stringify({
        profile_id: profileId,
        source,
        expected_version: expectedVersion,
      }),
    },
  );
}

export async function approveOnboardingProfile(
  profileId: string,
  expectedVersion: number,
  rationale: string,
): Promise<OnboardingProfile> {
  return onboardingJson<OnboardingProfile>(
    `data-onboarding/profiles/${encodeURIComponent(profileId)}/approve`,
    "approving_profile",
    {
      method: "POST",
      body: JSON.stringify({
        expected_version: expectedVersion,
        rationale,
      }),
    },
  );
}
