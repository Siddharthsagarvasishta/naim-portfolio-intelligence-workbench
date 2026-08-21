import type {
  ApiResponseMetadata,
  DataMode,
  EvidenceReference,
  FeatureStatus,
  MetricUnit,
  RequestBodyFor,
  ResponseBodyFor,
  SourceContext,
} from "../app/generated-api-types";

type Assert<T extends true> = T;
type Extends<Actual, Expected> = Actual extends Expected ? true : false;

export type StrictDataModes = Assert<
  Extends<
    DataMode,
    "LIVE" | "DEMO" | "OFFLINE_SNAPSHOT" | "UNAVAILABLE"
  >
>;

export type StrictFeatureStatuses = Assert<
  Extends<
    FeatureStatus,
    | "LIVE"
    | "INTEGRATION_ONLY"
    | "DOCUMENTED"
    | "DISABLED"
    | "NOT_IMPLEMENTED"
  >
>;

export const STRICT_SOURCE_CONTEXT_FIXTURE: SourceContext = {
  active_mode: "OFFLINE_SNAPSHOT",
  configured_mode: "OFFLINE_SNAPSHOT",
  snapshot_date: null,
  configuration_hash: null,
  dataset_hash: null,
  dataset_hash_basis: null,
  run_id: null,
  synthetic: null,
  reason: null,
};

export const GOVERNED_EVIDENCE_FIXTURE: EvidenceReference = {
  evidence_id: "EVIDENCE-CONTRACT-001",
  feature_status: "LIVE",
  unit: "bps" satisfies MetricUnit,
};

export const LOGIN_REQUEST_FIXTURE: RequestBodyFor<
  "/api/v1/auth/login",
  "post"
> = {
  username: "contract-user",
  password: "contract-password",
};

export type DataSourceResponseIncludesMetadata = Assert<
  Extends<
    ResponseBodyFor<"/api/v1/data-source", "get", "200">,
    ApiResponseMetadata
  >
>;
