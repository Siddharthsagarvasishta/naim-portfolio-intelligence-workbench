/**
 * GENERATED FILE — DO NOT EDIT.
 * Source: outputs/contracts/openapi.json
 * OpenAPI SHA-256: 39d1d6c9b8f271055ae7043ff49dbb51a986f702caa15df144725d371a615ec3
 * Refresh: npm run contracts:generate
 */

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | Array<JsonValue>;
export interface JsonObject { [key: string]: JsonValue | undefined }

export const OPENAPI_SHA256 = "39d1d6c9b8f271055ae7043ff49dbb51a986f702caa15df144725d371a615ec3" as const;
export const OPENAPI_PATH_COUNT = 113 as const;
export const OPENAPI_OPERATION_COUNT = 119 as const;

export interface components {
  schemas: {
    "AlertAcknowledgeRequest":
      {
        "expected_version": number;
        "note": string;
      };
    "AlertInvestigationRequest":
      {
        "expected_version": number;
        "owner"?: string | null;
        "reason": string;
      };
    "AlertTransitionRequest":
      {
        "expected_version": number;
        "owner"?: string | null;
        "reason": string;
        "related_investigation"?: string | null;
        "suppression_until_period"?: string | null;
        "target_status": "ACKNOWLEDGED" | "INVESTIGATING" | "ACTION_PROPOSED" | "MONITORING" | "RESOLVED" | "SUPPRESSED" | "CLOSED_AS_NOISE";
      };
    "AnalysisTemplateRunRequest":
      {
        "parameters"?: JsonObject;
        "template_id": string;
      };
    "ApiResponseMetadata":
      {
        [key: string]: JsonValue | undefined;
        "data_mode": components["schemas"]["DataMode"];
        "source_context": components["schemas"]["SourceContext"];
      };
    "BasketCombineRequest":
      {
        "left_members": Array<string>;
        "operation": string;
        "right_members": Array<string>;
      };
    "BasketCreate":
      {
        "basket_description"?: string;
        "basket_expression"?: string;
        "basket_name": string;
        "basket_type"?: string;
        "entity_type"?: string;
        "locked_flag"?: boolean;
        "members"?: Array<string>;
      };
    "BasketImpactRequest":
      {
        "original_members": Array<string>;
        "revised_members": Array<string>;
      };
    "BasketUpdate":
      {
        "basket_description"?: string | null;
        "basket_expression"?: string | null;
        "basket_name"?: string | null;
        "expected_version"?: number | null;
        "locked_flag"?: boolean | null;
        "members"?: Array<string> | null;
      };
    "BehaviouralRunRequest":
      {
        "account_column"?: string;
        "current_delinquency_column"?: string;
        "feature_columns"?: Array<string> | null;
        "records"?: Array<JsonObject> | null;
        "seed"?: number;
        "segment_column"?: string | null;
        "target_column"?: string;
        "time_column"?: string;
      };
    "CapacityScenarioRequest":
      {
        "capacity_multiplier"?: number;
        "handling_time_multiplier"?: number;
        "review_threshold_change"?: number;
        "volume_multiplier"?: number;
      };
    "ChangePointRunRequest":
      {
        "metric_id"?: string;
        "min_segment"?: number;
        "minimum_robust_effect"?: number;
        "seasonal_period"?: number | null;
        "series"?: Array<number> | null;
        "significance"?: number;
      };
    "CommentaryRequest":
      {
        "commentary_type"?: string;
        "period"?: string | null;
      };
    "DataMode":
      "LIVE" | "DEMO" | "OFFLINE_SNAPSHOT" | "UNAVAILABLE";
    "DifferenceInDifferencesRunRequest":
      {
        "cluster_column"?: string | null;
        "outcome_column": string;
        "policy_date": string;
        "records": Array<JsonObject>;
        "synthetic_policy_use_case"?: boolean;
        "time_column": string;
        "treatment_column": string;
      };
    "EvidenceId":
      string;
    "EvidenceReference":
      {
        "evidence_id": components["schemas"]["EvidenceId"];
        "feature_status": components["schemas"]["FeatureStatus"];
        "unit"?: components["schemas"]["MetricUnit"] | null;
      };
    "ExecutivePackGenerateRequest":
      {
        "comparison_period"?: string | null;
        "filter_scope"?: JsonObject;
        "include_pdf"?: boolean;
        "reporting_period"?: string | null;
        "workspace_id"?: string | null;
      };
    "FeatureStatus":
      "LIVE" | "INTEGRATION_ONLY" | "DOCUMENTED" | "DISABLED" | "NOT_IMPLEMENTED";
    "HTTPValidationError":
      {
        [key: string]: JsonValue | undefined;
        "detail"?: Array<components["schemas"]["ValidationError"]>;
      };
    "InvestigationCreate":
      {
        "affected_metric"?: string | null;
        "alert_id"?: string | null;
        "business_question": string;
        "hypothesis"?: string | null;
        "owner"?: string;
      };
    "InvestigationUpdate":
      {
        "action_taken"?: string | null;
        "decision"?: string | null;
        "expected_version"?: number | null;
        "hypothesis"?: string | null;
        "owner"?: string | null;
        "resolution"?: string | null;
        "reviewer"?: string | null;
        "status"?: string | null;
        "supporting_evidence"?: string | null;
      };
    "LoginRequest":
      {
        "password": string;
        "username": string;
      };
    "MarketRiskExportRequest":
      {
        "confidence"?: number;
        "end_date"?: string;
        "ewma_decay"?: number;
        "frequency"?: "daily" | "weekly" | "monthly";
        "include_excel"?: boolean;
        "include_presentation"?: boolean;
        "instrument"?: "NAIM-DEMO-INDEX" | "NAIM-DEMO-EQUITY";
        "option_inputs"?: JsonObject | null;
        "period"?: "one_year" | "three_years" | "five_years" | "custom";
        "return_type"?: "simple" | "log";
        "start_date"?: string | null;
        "windows"?: Array<number>;
      };
    "MarketRiskRunRequest":
      {
        "confidence"?: number;
        "end_date"?: string;
        "ewma_decay"?: number;
        "frequency"?: "daily" | "weekly" | "monthly";
        "instrument"?: "NAIM-DEMO-INDEX" | "NAIM-DEMO-EQUITY";
        "option_inputs"?: JsonObject | null;
        "period"?: "one_year" | "three_years" | "five_years" | "custom";
        "return_type"?: "simple" | "log";
        "start_date"?: string | null;
        "windows"?: Array<number>;
      };
    "MetricUnit":
      "count" | "currency" | "percent" | "bps" | "ratio" | "days" | "months";
    "NetworkImpactRequest":
      {
        "node_id": string;
      };
    "OnboardingApprovalRequest":
      {
        "expected_version": number;
        "rationale": string;
      };
    "OnboardingLoadRequest":
      {
        "expected_version"?: number | null;
        "profile_id": string;
        "source": components["schemas"]["OnboardingSource"];
      };
    "OnboardingMappingRequest":
      {
        "contract_id": string;
        "mapping": Record<string, string>;
        "source": components["schemas"]["OnboardingSource"];
        "transformations"?: Record<string, string>;
      };
    "OnboardingPostgresRequest":
      {
        "table": string;
        "url_env": string;
      };
    "OnboardingPreviewRequest":
      {
        "sample_rows"?: number;
        "source": components["schemas"]["OnboardingSource"];
      };
    "OnboardingProfileCreateRequest":
      {
        "contract_id": string;
        "mapping": Record<string, string>;
        "max_error_rate"?: number;
        "profile_id": string;
        "source": components["schemas"]["OnboardingSource"];
        "transformations"?: Record<string, string>;
      };
    "OnboardingSelectRequest":
      {
        "relative_path": string;
        "sheet"?: string | number | null;
        "table"?: string | null;
      };
    "OnboardingSource":
      {
        "display_name": string;
        "kind": "csv" | "xlsx" | "parquet" | "json" | "sqlite" | "duckdb" | "postgresql";
        "relative_path"?: string | null;
        "sha256"?: string | null;
        "sheet"?: string | number | null;
        "size_bytes"?: number | null;
        "source_id": string;
        "table"?: string | null;
        "url_env"?: string | null;
      };
    "OnboardingTableRequest":
      {
        "source": components["schemas"]["OnboardingSource"];
        "table": string;
      };
    "OnboardingUploadRequest":
      {
        "content_base64": string;
        "filename": string;
      };
    "OnboardingValidationRequest":
      {
        "contract_id": string;
        "mapping": Record<string, string>;
        "max_error_rate"?: number;
        "source": components["schemas"]["OnboardingSource"];
        "transformations"?: Record<string, string>;
      };
    "OptimisationConstraints":
      {
        "allocation_total"?: number;
        "concentration_limit"?: number | null;
        "fraud_bps_max"?: number | null;
        "friction_max"?: number | null;
        "loss_rate_max"?: number | null;
        "minimum_customer_coverage"?: number | null;
        "regional_service_min"?: number | null;
        "review_capacity_max"?: number | null;
        "vendor_cost_max"?: number | null;
      };
    "OptimisationItem":
      {
        "baseline": number;
        "customer_coverage"?: number;
        "customer_friction"?: number;
        "eligible"?: boolean;
        "expected_loss"?: number;
        "expected_profit"?: number;
        "fraud_bps"?: number;
        "maximum"?: number;
        "minimum"?: number;
        "name": string;
        "regional_service"?: number;
        "review_load"?: number;
        "vendor_cost"?: number;
      };
    "OptimisationRunRequest":
      {
        "constraints"?: components["schemas"]["OptimisationConstraints"];
        "decision_dimension": string;
        "items": Array<components["schemas"]["OptimisationItem"]>;
        "objective": string;
        "save_scenario"?: boolean;
        "weights"?: Record<string, number>;
      };
    "PartnerScenarioRequest":
      {
        "attrition_multiplier"?: number;
        "credit_loss_multiplier"?: number;
        "fraud_loss_multiplier"?: number;
        "partner_id": string;
        "reporting_month"?: string | null;
        "volume_multiplier"?: number;
      };
    "PeerMatchRequest":
      {
        "comparison_metric"?: string | null;
        "entity_id": string;
        "entity_type": string;
        "peer_count"?: number;
      };
    "PresentationGenerateRequest":
      {
        "basket_id"?: string | null;
        "commentary_length"?: number;
        "comparison_period"?: string | null;
        "detail_level"?: string;
        "include_appendix"?: boolean;
        "presentation_template"?: string;
        "reporting_period"?: string | null;
        "scenario_name"?: string;
        "selected_sections"?: Array<string>;
        "speaker_notes"?: boolean;
        "workspace_id"?: string | null;
      };
    "PropensityRunRequest":
      {
        "covariates": Array<string>;
        "outcome_column": string;
        "records": Array<JsonObject>;
        "seed"?: number;
        "treatment_column": string;
        "trim_quantile"?: number;
      };
    "RatingRequest":
      {
        "components": Record<string, number | null>;
        "rating_type": string;
      };
    "RatingSensitivityRequest":
      {
        "components": Record<string, number | null>;
        "rating_type": string;
        "weight_overrides"?: Record<string, number>;
      };
    "ScenarioRunRequest":
      {
        "custom_assumptions"?: Record<string, number> | null;
        "horizon_months"?: number;
        "reporting_month"?: string | null;
        "scenario_name"?: string;
      };
    "SourceContext":
      {
        "active_mode": components["schemas"]["DataMode"];
        "configuration_hash": string | null;
        "configured_mode": components["schemas"]["DataMode"];
        "dataset_hash": string | null;
        "dataset_hash_basis": string | null;
        "reason": string | null;
        "run_id": string | null;
        "snapshot_date": string | null;
        "synthetic": boolean | null;
      };
    "SurvivalRunRequest":
      {
        "confidence"?: number;
        "group_column"?: string | null;
        "outcomes"?: Record<string, Array<JsonValue>> | null;
        "records"?: Array<JsonObject> | null;
      };
    "ValidationError":
      {
        [key: string]: JsonValue | undefined;
        "ctx"?: JsonObject;
        "input"?: JsonValue;
        "loc": Array<string | number>;
        "msg": string;
        "type": string;
      };
    "VendorReallocationRequest":
      {
        "reallocation_share"?: number;
        "reporting_month"?: string | null;
        "source_vendor_id": string;
        "target_vendor_id": string;
      };
    "WorkspaceCreate":
      {
        "business_question": string;
        "commentary_configuration"?: JsonObject;
        "comparison_period"?: string | null;
        "export_configuration"?: JsonObject;
        "filter_configuration"?: JsonObject;
        "owner"?: string;
        "reporting_period"?: string | null;
        "selected_baskets"?: Array<string>;
        "selected_dimensions"?: Array<string>;
        "selected_metrics"?: Array<string>;
        "selected_scenarios"?: Array<string>;
        "selected_templates"?: Array<string>;
        "visual_configuration"?: JsonObject;
        "workspace_name": string;
        "workspace_type"?: string;
      };
    "WorkspaceUpdate":
      {
        "business_question"?: string | null;
        "commentary_configuration"?: JsonObject | null;
        "comparison_period"?: string | null;
        "expected_version"?: number | null;
        "export_configuration"?: JsonObject | null;
        "filter_configuration"?: JsonObject | null;
        "owner"?: string | null;
        "reporting_period"?: string | null;
        "selected_baskets"?: Array<string> | null;
        "selected_dimensions"?: Array<string> | null;
        "selected_metrics"?: Array<string> | null;
        "selected_scenarios"?: Array<string> | null;
        "selected_templates"?: Array<string> | null;
        "visual_configuration"?: JsonObject | null;
        "workspace_name"?: string | null;
        "workspace_type"?: string | null;
      };
  };
}

export type AlertAcknowledgeRequest = components["schemas"]["AlertAcknowledgeRequest"];
export type AlertInvestigationRequest = components["schemas"]["AlertInvestigationRequest"];
export type AlertTransitionRequest = components["schemas"]["AlertTransitionRequest"];
export type AnalysisTemplateRunRequest = components["schemas"]["AnalysisTemplateRunRequest"];
export type ApiResponseMetadata = components["schemas"]["ApiResponseMetadata"];
export type BasketCombineRequest = components["schemas"]["BasketCombineRequest"];
export type BasketCreate = components["schemas"]["BasketCreate"];
export type BasketImpactRequest = components["schemas"]["BasketImpactRequest"];
export type BasketUpdate = components["schemas"]["BasketUpdate"];
export type BehaviouralRunRequest = components["schemas"]["BehaviouralRunRequest"];
export type CapacityScenarioRequest = components["schemas"]["CapacityScenarioRequest"];
export type ChangePointRunRequest = components["schemas"]["ChangePointRunRequest"];
export type CommentaryRequest = components["schemas"]["CommentaryRequest"];
export type DataMode = components["schemas"]["DataMode"];
export type DifferenceInDifferencesRunRequest = components["schemas"]["DifferenceInDifferencesRunRequest"];
export type EvidenceId = components["schemas"]["EvidenceId"];
export type EvidenceReference = components["schemas"]["EvidenceReference"];
export type ExecutivePackGenerateRequest = components["schemas"]["ExecutivePackGenerateRequest"];
export type FeatureStatus = components["schemas"]["FeatureStatus"];
export type HTTPValidationError = components["schemas"]["HTTPValidationError"];
export type InvestigationCreate = components["schemas"]["InvestigationCreate"];
export type InvestigationUpdate = components["schemas"]["InvestigationUpdate"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type MarketRiskExportRequest = components["schemas"]["MarketRiskExportRequest"];
export type MarketRiskRunRequest = components["schemas"]["MarketRiskRunRequest"];
export type MetricUnit = components["schemas"]["MetricUnit"];
export type NetworkImpactRequest = components["schemas"]["NetworkImpactRequest"];
export type OnboardingApprovalRequest = components["schemas"]["OnboardingApprovalRequest"];
export type OnboardingLoadRequest = components["schemas"]["OnboardingLoadRequest"];
export type OnboardingMappingRequest = components["schemas"]["OnboardingMappingRequest"];
export type OnboardingPostgresRequest = components["schemas"]["OnboardingPostgresRequest"];
export type OnboardingPreviewRequest = components["schemas"]["OnboardingPreviewRequest"];
export type OnboardingProfileCreateRequest = components["schemas"]["OnboardingProfileCreateRequest"];
export type OnboardingSelectRequest = components["schemas"]["OnboardingSelectRequest"];
export type OnboardingSource = components["schemas"]["OnboardingSource"];
export type OnboardingTableRequest = components["schemas"]["OnboardingTableRequest"];
export type OnboardingUploadRequest = components["schemas"]["OnboardingUploadRequest"];
export type OnboardingValidationRequest = components["schemas"]["OnboardingValidationRequest"];
export type OptimisationConstraints = components["schemas"]["OptimisationConstraints"];
export type OptimisationItem = components["schemas"]["OptimisationItem"];
export type OptimisationRunRequest = components["schemas"]["OptimisationRunRequest"];
export type PartnerScenarioRequest = components["schemas"]["PartnerScenarioRequest"];
export type PeerMatchRequest = components["schemas"]["PeerMatchRequest"];
export type PresentationGenerateRequest = components["schemas"]["PresentationGenerateRequest"];
export type PropensityRunRequest = components["schemas"]["PropensityRunRequest"];
export type RatingRequest = components["schemas"]["RatingRequest"];
export type RatingSensitivityRequest = components["schemas"]["RatingSensitivityRequest"];
export type ScenarioRunRequest = components["schemas"]["ScenarioRunRequest"];
export type SourceContext = components["schemas"]["SourceContext"];
export type SurvivalRunRequest = components["schemas"]["SurvivalRunRequest"];
export type ValidationError = components["schemas"]["ValidationError"];
export type VendorReallocationRequest = components["schemas"]["VendorReallocationRequest"];
export type WorkspaceCreate = components["schemas"]["WorkspaceCreate"];
export type WorkspaceUpdate = components["schemas"]["WorkspaceUpdate"];

export interface operations {
  "acknowledge_alert_api_v1_alerts__alert_id__acknowledge_post":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path:
            {
              "alert_id": string;
            };
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["AlertAcknowledgeRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/alerts/{alert_id}/acknowledge";
    };
  "advanced_behavioural_api_v1_advanced_statistics_behavioural_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["BehaviouralRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/advanced-statistics/behavioural";
    };
  "advanced_change_points_api_v1_advanced_statistics_change_points_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["ChangePointRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/advanced-statistics/change-points";
    };
  "advanced_difference_in_differences_api_v1_advanced_statistics_difference_in_differences_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["DifferenceInDifferencesRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/advanced-statistics/difference-in-differences";
    };
  "advanced_propensity_api_v1_advanced_statistics_propensity_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["PropensityRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/advanced-statistics/propensity";
    };
  "advanced_statistics_status_api_v1_advanced_statistics_status_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/advanced-statistics/status";
    };
  "advanced_survival_api_v1_advanced_statistics_survival_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["SurvivalRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/advanced-statistics/survival";
    };
  "alert_audit_api_v1_alerts__alert_id__audit_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path:
            {
              "alert_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/alerts/{alert_id}/audit";
    };
  "alert_detail_api_v1_alerts__alert_id__get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path:
            {
              "alert_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/alerts/{alert_id}";
    };
  "alerts_api_v1_alerts_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "reporting_month"?: string | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/alerts";
    };
  "analysis_run_api_v1_analysis_runs__run_id__get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "run_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/analysis-runs/{run_id}";
    };
  "analysis_templates_api_v1_analysis_templates_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/analysis-templates";
    };
  "auth_me_api_v1_auth_me_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/auth/me";
    };
  "auth_status_api_v1_auth_status_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/auth/status";
    };
  "basket_detail_api_v1_baskets__basket_id__get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path:
            {
              "basket_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/baskets/{basket_id}";
    };
  "basket_impact_api_v1_baskets_compare_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["BasketImpactRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/baskets/compare";
    };
  "basket_impact_api_v1_baskets_impact_preview_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["BasketImpactRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/baskets/impact-preview";
    };
  "baskets_api_v1_baskets_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/baskets";
    };
  "benefits_api_v1_benefit_performance_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/benefit-performance";
    };
  "benefits_api_v1_benefits_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/benefits";
    };
  "capabilities_api_v1_capabilities_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/capabilities";
    };
  "capacity_api_v1_capacity_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/capacity";
    };
  "capacity_scenario_api_v1_capacity_scenario_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["CapacityScenarioRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/capacity/scenario";
    };
  "clone_basket_api_v1_baskets__basket_id__clone_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "basket_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/baskets/{basket_id}/clone";
    };
  "combine_baskets_api_v1_baskets_combine_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["BasketCombineRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/baskets/combine";
    };
  "command_centre_api_v1_command_centre_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "reporting_month"?: string | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/command-centre";
    };
  "commentary_api_v1_commentary_generate_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["CommentaryRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/commentary/generate";
    };
  "composition_scenario_api_v1_composition_scenarios_run_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OptimisationRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/composition-scenarios/run";
    };
  "create_basket_api_v1_baskets_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["BasketCreate"];
            };
        };
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/baskets";
    };
  "create_investigation_api_v1_investigations_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["InvestigationCreate"];
            };
        };
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/investigations";
    };
  "create_workspace_api_v1_workspaces_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["WorkspaceCreate"];
            };
        };
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/workspaces";
    };
  "data_quality_api_v1_data_quality_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/data-quality";
    };
  "data_source_api_v1_data_source_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/data-source";
    };
  "demo_run_api_v1_demo_run_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/demo/run";
    };
  "demo_status_api_v1_demo_status__run_id__get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "run_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/demo/status/{run_id}";
    };
  "download_export_api_v1_exports__artifact_id__download_get":
    {
      parameters:
        {
          query:
            {
              "download_token": string;
            };
          header?: never;
          path:
            {
              "artifact_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonValue & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/exports/{artifact_id}/download";
    };
  "drift_api_v1_drift_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/drift";
    };
  "executive_pack_download_api_v1_executive_packs__job_id__download_get":
    {
      parameters:
        {
          query:
            {
              "download_token": string;
            };
          header?: never;
          path:
            {
              "job_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonValue & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/executive-packs/{job_id}/download";
    };
  "executive_pack_generate_api_v1_executive_packs_generate_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["ExecutivePackGenerateRequest"];
            };
        };
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/executive-packs/generate";
    };
  "executive_pack_manifest_api_v1_executive_packs__job_id__manifest_get":
    {
      parameters:
        {
          query:
            {
              "download_token": string;
            };
          header?: never;
          path:
            {
              "job_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonValue & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/executive-packs/{job_id}/manifest";
    };
  "executive_pack_status_api_v1_executive_packs__job_id__get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "job_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/executive-packs/{job_id}";
    };
  "export_excel_api_v1_exports_excel_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/exports/excel";
    };
  "export_powerbi_api_v1_exports_powerbi_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/exports/powerbi";
    };
  "export_workspace_api_v1_workspaces__workspace_id__export_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "workspace_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/workspaces/{workspace_id}/export";
    };
  "exports_api_v1_exports_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/exports";
    };
  "filters_api_v1_filters_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/filters";
    };
  "finance_api_v1_finance_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/finance";
    };
  "health_api_v1_health_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/health";
    };
  "investigations_api_v1_investigations_get":
    {
      parameters:
        {
          query:
            {
              "page"?: number;
              "page_size"?: number;
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/investigations";
    };
  "kpis_api_v1_kpis_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "reporting_month"?: string | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/kpis";
    };
  "login_api_v1_auth_login_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["LoginRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "POST";
      path: "/api/v1/auth/login";
    };
  "logout_api_v1_auth_logout_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/auth/logout";
    };
  "market_risk_export_api_v1_market_risk_export_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["MarketRiskExportRequest"];
            };
        };
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/market-risk/export";
    };
  "market_risk_run_api_v1_market_risk_run_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["MarketRiskRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/market-risk/run";
    };
  "market_risk_status_api_v1_market_risk_status_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/market-risk/status";
    };
  "membership_transitions_api_v1_membership_transitions_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/membership-transitions";
    };
  "memberships_api_v1_membership_performance_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/membership-performance";
    };
  "memberships_api_v1_memberships_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/memberships";
    };
  "metadata_api_v1_metadata_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/metadata";
    };
  "metric_registry_api_v1_metric_registry_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/metric-registry";
    };
  "network_api_v1_network_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/network";
    };
  "network_node_impact_api_v1_network_impact_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["NetworkImpactRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/network/impact";
    };
  "onboarding_approve_profile_api_v1_data_onboarding_profiles__profile_id__approve_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "profile_id": string;
            };
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingApprovalRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/profiles/{profile_id}/approve";
    };
  "onboarding_bind_table_api_v1_data_onboarding_sources_table_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingTableRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/sources/table";
    };
  "onboarding_contracts_api_v1_data_onboarding_contracts_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/data-onboarding/contracts";
    };
  "onboarding_create_profile_api_v1_data_onboarding_profiles_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingProfileCreateRequest"];
            };
        };
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/profiles";
    };
  "onboarding_database_tables_api_v1_data_onboarding_sources_tables_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingSource"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/sources/tables";
    };
  "onboarding_load_api_v1_data_onboarding_load_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingLoadRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/load";
    };
  "onboarding_map_api_v1_data_onboarding_map_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingMappingRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/map";
    };
  "onboarding_postgresql_source_api_v1_data_onboarding_sources_postgresql_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingPostgresRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/sources/postgresql";
    };
  "onboarding_preview_api_v1_data_onboarding_preview_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingPreviewRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/preview";
    };
  "onboarding_profile_api_v1_data_onboarding_profiles__profile_id__get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "profile_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/data-onboarding/profiles/{profile_id}";
    };
  "onboarding_profiles_api_v1_data_onboarding_profiles_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/data-onboarding/profiles";
    };
  "onboarding_select_source_api_v1_data_onboarding_sources_select_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingSelectRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/sources/select";
    };
  "onboarding_upload_source_api_v1_data_onboarding_sources_upload_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingUploadRequest"];
            };
        };
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/sources/upload";
    };
  "onboarding_validate_api_v1_data_onboarding_validate_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OnboardingValidationRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/data-onboarding/validate";
    };
  "optimisation_run_api_v1_optimisation_run_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["OptimisationRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/optimisation/run";
    };
  "partner_detail_api_v1_partners__partner_id__get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path:
            {
              "partner_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/partners/{partner_id}";
    };
  "partner_ratings_api_v1_partner_ratings_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/partner-ratings";
    };
  "partner_scenario_api_v1_partner_scenarios_run_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["PartnerScenarioRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/partner-scenarios/run";
    };
  "partners_api_v1_partner_performance_get":
    {
      parameters:
        {
          query:
            {
              "page"?: number;
              "page_size"?: number;
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/partner-performance";
    };
  "partners_api_v1_partners_get":
    {
      parameters:
        {
          query:
            {
              "page"?: number;
              "page_size"?: number;
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/partners";
    };
  "peer_analogue_catalogue_api_v1_peer_analogues_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/peer-analogues";
    };
  "peer_analogue_match_api_v1_peer_analogues_match_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["PeerMatchRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/peer-analogues/match";
    };
  "presentation_download_api_v1_presentations__presentation_id__download_get":
    {
      parameters:
        {
          query:
            {
              "download_token": string;
            };
          header?: never;
          path:
            {
              "presentation_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonValue & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/presentations/{presentation_id}/download";
    };
  "presentation_generate_api_v1_presentations_generate_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["PresentationGenerateRequest"];
            };
        };
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/presentations/generate";
    };
  "presentation_manifest_api_v1_presentations__presentation_id__manifest_get":
    {
      parameters:
        {
          query:
            {
              "download_token": string;
            };
          header?: never;
          path:
            {
              "presentation_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonValue & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/presentations/{presentation_id}/manifest";
    };
  "presentation_status_api_v1_presentations__presentation_id__get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "presentation_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/presentations/{presentation_id}";
    };
  "presentations_api_v1_presentations_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/presentations";
    };
  "rating_calculate_api_v1_ratings_calculate_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["RatingRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "POST";
      path: "/api/v1/ratings/calculate";
    };
  "rating_sensitivity_api_v1_ratings_sensitivity_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["RatingSensitivityRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/ratings/sensitivity";
    };
  "ratings_api_v1_ratings_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/ratings";
    };
  "refresh_workspace_api_v1_workspaces__workspace_id__refresh_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "workspace_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/workspaces/{workspace_id}/refresh";
    };
  "roll_rates_api_v1_roll_rates_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "reporting_month"?: string | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/roll-rates";
    };
  "root__get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject;
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/";
    };
  "root_cause_api_v1_root_cause_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "reporting_month"?: string | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/root-cause";
    };
  "run_analysis_template_api_v1_analysis_templates_run_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["AnalysisTemplateRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/analysis-templates/run";
    };
  "run_workspace_api_v1_workspaces__workspace_id__run_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "workspace_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/workspaces/{workspace_id}/run";
    };
  "scenario_run_api_v1_scenarios_run_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["ScenarioRunRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/scenarios/run";
    };
  "scenarios_api_v1_scenarios_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/scenarios";
    };
  "segments_api_v1_segments_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/segments";
    };
  "start_alert_investigation_api_v1_alerts__alert_id__investigation_post":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path:
            {
              "alert_id": string;
            };
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["AlertInvestigationRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/alerts/{alert_id}/investigation";
    };
  "strategy_comparison_api_v1_strategy_comparison_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "reporting_month"?: string | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/strategy-comparison";
    };
  "tableau_extract_api_v1_tableau_extract_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "201":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/tableau/extract";
    };
  "tableau_extract_download_api_v1_tableau_extract_download_get":
    {
      parameters:
        {
          query:
            {
              "download_token": string;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonValue & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/tableau/extract/download";
    };
  "tableau_extract_manifest_api_v1_tableau_extract_manifest_get":
    {
      parameters:
        {
          query:
            {
              "download_token": string;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonValue & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "GET";
      path: "/api/v1/tableau/extract/manifest";
    };
  "transition_alert_api_v1_alerts__alert_id__transition_post":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path:
            {
              "alert_id": string;
            };
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["AlertTransitionRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/alerts/{alert_id}/transition";
    };
  "trends_api_v1_trends_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "reporting_month"?: string | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/trends";
    };
  "update_basket_api_v1_baskets__basket_id__patch":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "basket_id": string;
            };
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["BasketUpdate"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "PATCH";
      path: "/api/v1/baskets/{basket_id}";
    };
  "update_investigation_api_v1_investigations__investigation_id__patch":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "investigation_id": string;
            };
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["InvestigationUpdate"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "PATCH";
      path: "/api/v1/investigations/{investigation_id}";
    };
  "update_workspace_api_v1_workspaces__workspace_id__patch":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "workspace_id": string;
            };
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["WorkspaceUpdate"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "PATCH";
      path: "/api/v1/workspaces/{workspace_id}";
    };
  "vendor_detail_api_v1_vendors__vendor_id__get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path:
            {
              "vendor_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/vendors/{vendor_id}";
    };
  "vendor_ratings_api_v1_vendor_ratings_get":
    {
      parameters:
        {
          query:
            {
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/vendor-ratings";
    };
  "vendor_reallocation_api_v1_vendor_reallocation_run_post":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody:
        {
          content:
            {
              "application/json": components["schemas"]["VendorReallocationRequest"];
            };
        };
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: true;
      method: "POST";
      path: "/api/v1/vendor-reallocation/run";
    };
  "vendors_api_v1_vendor_performance_get":
    {
      parameters:
        {
          query:
            {
              "page"?: number;
              "page_size"?: number;
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/vendor-performance";
    };
  "vendors_api_v1_vendors_get":
    {
      parameters:
        {
          query:
            {
              "page"?: number;
              "page_size"?: number;
              "reporting_month"?: string | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/vendors";
    };
  "vintages_api_v1_vintages_get":
    {
      parameters:
        {
          query:
            {
              "acquisition_channel"?: Array<string> | null;
              "customer_segment"?: Array<string> | null;
              "geography"?: Array<string> | null;
              "membership_tier"?: Array<string> | null;
              "model_version"?: Array<string> | null;
              "page"?: number;
              "page_size"?: number;
              "partner"?: Array<string> | null;
              "product"?: Array<string> | null;
              "reporting_month"?: string | null;
              "risk_band"?: Array<string> | null;
              "strategy"?: Array<string> | null;
              "vendor"?: Array<string> | null;
            };
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/vintages";
    };
  "workspace_detail_api_v1_workspaces__workspace_id__get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path:
            {
              "workspace_id": string;
            };
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
          "422":
            {
              content:
                {
                  "application/json": components["schemas"]["HTTPValidationError"] & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/workspaces/{workspace_id}";
    };
  "workspaces_api_v1_workspaces_get":
    {
      parameters:
        {
          query?: never;
          header?: never;
          path?: never;
          cookie?: never;
        };
      requestBody?: never;
      responses:
        {
          "200":
            {
              content:
                {
                  "application/json": JsonObject & components["schemas"]["ApiResponseMetadata"];
                };
            };
        };
      authenticated: false;
      method: "GET";
      path: "/api/v1/workspaces";
    };
}

export interface paths {
  "/":
    {
      get: operations["root__get"];
    };
  "/api/v1/advanced-statistics/behavioural":
    {
      post: operations["advanced_behavioural_api_v1_advanced_statistics_behavioural_post"];
    };
  "/api/v1/advanced-statistics/change-points":
    {
      post: operations["advanced_change_points_api_v1_advanced_statistics_change_points_post"];
    };
  "/api/v1/advanced-statistics/difference-in-differences":
    {
      post: operations["advanced_difference_in_differences_api_v1_advanced_statistics_difference_in_differences_post"];
    };
  "/api/v1/advanced-statistics/propensity":
    {
      post: operations["advanced_propensity_api_v1_advanced_statistics_propensity_post"];
    };
  "/api/v1/advanced-statistics/status":
    {
      get: operations["advanced_statistics_status_api_v1_advanced_statistics_status_get"];
    };
  "/api/v1/advanced-statistics/survival":
    {
      post: operations["advanced_survival_api_v1_advanced_statistics_survival_post"];
    };
  "/api/v1/alerts":
    {
      get: operations["alerts_api_v1_alerts_get"];
    };
  "/api/v1/alerts/{alert_id}":
    {
      get: operations["alert_detail_api_v1_alerts__alert_id__get"];
    };
  "/api/v1/alerts/{alert_id}/acknowledge":
    {
      post: operations["acknowledge_alert_api_v1_alerts__alert_id__acknowledge_post"];
    };
  "/api/v1/alerts/{alert_id}/audit":
    {
      get: operations["alert_audit_api_v1_alerts__alert_id__audit_get"];
    };
  "/api/v1/alerts/{alert_id}/investigation":
    {
      post: operations["start_alert_investigation_api_v1_alerts__alert_id__investigation_post"];
    };
  "/api/v1/alerts/{alert_id}/transition":
    {
      post: operations["transition_alert_api_v1_alerts__alert_id__transition_post"];
    };
  "/api/v1/analysis-runs/{run_id}":
    {
      get: operations["analysis_run_api_v1_analysis_runs__run_id__get"];
    };
  "/api/v1/analysis-templates":
    {
      get: operations["analysis_templates_api_v1_analysis_templates_get"];
    };
  "/api/v1/analysis-templates/run":
    {
      post: operations["run_analysis_template_api_v1_analysis_templates_run_post"];
    };
  "/api/v1/auth/login":
    {
      post: operations["login_api_v1_auth_login_post"];
    };
  "/api/v1/auth/logout":
    {
      post: operations["logout_api_v1_auth_logout_post"];
    };
  "/api/v1/auth/me":
    {
      get: operations["auth_me_api_v1_auth_me_get"];
    };
  "/api/v1/auth/status":
    {
      get: operations["auth_status_api_v1_auth_status_get"];
    };
  "/api/v1/baskets":
    {
      get: operations["baskets_api_v1_baskets_get"];
      post: operations["create_basket_api_v1_baskets_post"];
    };
  "/api/v1/baskets/combine":
    {
      post: operations["combine_baskets_api_v1_baskets_combine_post"];
    };
  "/api/v1/baskets/compare":
    {
      post: operations["basket_impact_api_v1_baskets_compare_post"];
    };
  "/api/v1/baskets/impact-preview":
    {
      post: operations["basket_impact_api_v1_baskets_impact_preview_post"];
    };
  "/api/v1/baskets/{basket_id}":
    {
      get: operations["basket_detail_api_v1_baskets__basket_id__get"];
      patch: operations["update_basket_api_v1_baskets__basket_id__patch"];
    };
  "/api/v1/baskets/{basket_id}/clone":
    {
      post: operations["clone_basket_api_v1_baskets__basket_id__clone_post"];
    };
  "/api/v1/benefit-performance":
    {
      get: operations["benefits_api_v1_benefit_performance_get"];
    };
  "/api/v1/benefits":
    {
      get: operations["benefits_api_v1_benefits_get"];
    };
  "/api/v1/capabilities":
    {
      get: operations["capabilities_api_v1_capabilities_get"];
    };
  "/api/v1/capacity":
    {
      get: operations["capacity_api_v1_capacity_get"];
    };
  "/api/v1/capacity/scenario":
    {
      post: operations["capacity_scenario_api_v1_capacity_scenario_post"];
    };
  "/api/v1/command-centre":
    {
      get: operations["command_centre_api_v1_command_centre_get"];
    };
  "/api/v1/commentary/generate":
    {
      post: operations["commentary_api_v1_commentary_generate_post"];
    };
  "/api/v1/composition-scenarios/run":
    {
      post: operations["composition_scenario_api_v1_composition_scenarios_run_post"];
    };
  "/api/v1/data-onboarding/contracts":
    {
      get: operations["onboarding_contracts_api_v1_data_onboarding_contracts_get"];
    };
  "/api/v1/data-onboarding/load":
    {
      post: operations["onboarding_load_api_v1_data_onboarding_load_post"];
    };
  "/api/v1/data-onboarding/map":
    {
      post: operations["onboarding_map_api_v1_data_onboarding_map_post"];
    };
  "/api/v1/data-onboarding/preview":
    {
      post: operations["onboarding_preview_api_v1_data_onboarding_preview_post"];
    };
  "/api/v1/data-onboarding/profiles":
    {
      get: operations["onboarding_profiles_api_v1_data_onboarding_profiles_get"];
      post: operations["onboarding_create_profile_api_v1_data_onboarding_profiles_post"];
    };
  "/api/v1/data-onboarding/profiles/{profile_id}":
    {
      get: operations["onboarding_profile_api_v1_data_onboarding_profiles__profile_id__get"];
    };
  "/api/v1/data-onboarding/profiles/{profile_id}/approve":
    {
      post: operations["onboarding_approve_profile_api_v1_data_onboarding_profiles__profile_id__approve_post"];
    };
  "/api/v1/data-onboarding/sources/postgresql":
    {
      post: operations["onboarding_postgresql_source_api_v1_data_onboarding_sources_postgresql_post"];
    };
  "/api/v1/data-onboarding/sources/select":
    {
      post: operations["onboarding_select_source_api_v1_data_onboarding_sources_select_post"];
    };
  "/api/v1/data-onboarding/sources/table":
    {
      post: operations["onboarding_bind_table_api_v1_data_onboarding_sources_table_post"];
    };
  "/api/v1/data-onboarding/sources/tables":
    {
      post: operations["onboarding_database_tables_api_v1_data_onboarding_sources_tables_post"];
    };
  "/api/v1/data-onboarding/sources/upload":
    {
      post: operations["onboarding_upload_source_api_v1_data_onboarding_sources_upload_post"];
    };
  "/api/v1/data-onboarding/validate":
    {
      post: operations["onboarding_validate_api_v1_data_onboarding_validate_post"];
    };
  "/api/v1/data-quality":
    {
      get: operations["data_quality_api_v1_data_quality_get"];
    };
  "/api/v1/data-source":
    {
      get: operations["data_source_api_v1_data_source_get"];
    };
  "/api/v1/demo/run":
    {
      post: operations["demo_run_api_v1_demo_run_post"];
    };
  "/api/v1/demo/status/{run_id}":
    {
      get: operations["demo_status_api_v1_demo_status__run_id__get"];
    };
  "/api/v1/drift":
    {
      get: operations["drift_api_v1_drift_get"];
    };
  "/api/v1/executive-packs/generate":
    {
      post: operations["executive_pack_generate_api_v1_executive_packs_generate_post"];
    };
  "/api/v1/executive-packs/{job_id}":
    {
      get: operations["executive_pack_status_api_v1_executive_packs__job_id__get"];
    };
  "/api/v1/executive-packs/{job_id}/download":
    {
      get: operations["executive_pack_download_api_v1_executive_packs__job_id__download_get"];
    };
  "/api/v1/executive-packs/{job_id}/manifest":
    {
      get: operations["executive_pack_manifest_api_v1_executive_packs__job_id__manifest_get"];
    };
  "/api/v1/exports":
    {
      get: operations["exports_api_v1_exports_get"];
    };
  "/api/v1/exports/excel":
    {
      post: operations["export_excel_api_v1_exports_excel_post"];
    };
  "/api/v1/exports/powerbi":
    {
      post: operations["export_powerbi_api_v1_exports_powerbi_post"];
    };
  "/api/v1/exports/{artifact_id}/download":
    {
      get: operations["download_export_api_v1_exports__artifact_id__download_get"];
    };
  "/api/v1/filters":
    {
      get: operations["filters_api_v1_filters_get"];
    };
  "/api/v1/finance":
    {
      get: operations["finance_api_v1_finance_get"];
    };
  "/api/v1/health":
    {
      get: operations["health_api_v1_health_get"];
    };
  "/api/v1/investigations":
    {
      get: operations["investigations_api_v1_investigations_get"];
      post: operations["create_investigation_api_v1_investigations_post"];
    };
  "/api/v1/investigations/{investigation_id}":
    {
      patch: operations["update_investigation_api_v1_investigations__investigation_id__patch"];
    };
  "/api/v1/kpis":
    {
      get: operations["kpis_api_v1_kpis_get"];
    };
  "/api/v1/market-risk/export":
    {
      post: operations["market_risk_export_api_v1_market_risk_export_post"];
    };
  "/api/v1/market-risk/run":
    {
      post: operations["market_risk_run_api_v1_market_risk_run_post"];
    };
  "/api/v1/market-risk/status":
    {
      get: operations["market_risk_status_api_v1_market_risk_status_get"];
    };
  "/api/v1/membership-performance":
    {
      get: operations["memberships_api_v1_membership_performance_get"];
    };
  "/api/v1/membership-transitions":
    {
      get: operations["membership_transitions_api_v1_membership_transitions_get"];
    };
  "/api/v1/memberships":
    {
      get: operations["memberships_api_v1_memberships_get"];
    };
  "/api/v1/metadata":
    {
      get: operations["metadata_api_v1_metadata_get"];
    };
  "/api/v1/metric-registry":
    {
      get: operations["metric_registry_api_v1_metric_registry_get"];
    };
  "/api/v1/network":
    {
      get: operations["network_api_v1_network_get"];
    };
  "/api/v1/network/impact":
    {
      post: operations["network_node_impact_api_v1_network_impact_post"];
    };
  "/api/v1/optimisation/run":
    {
      post: operations["optimisation_run_api_v1_optimisation_run_post"];
    };
  "/api/v1/partner-performance":
    {
      get: operations["partners_api_v1_partner_performance_get"];
    };
  "/api/v1/partner-ratings":
    {
      get: operations["partner_ratings_api_v1_partner_ratings_get"];
    };
  "/api/v1/partner-scenarios/run":
    {
      post: operations["partner_scenario_api_v1_partner_scenarios_run_post"];
    };
  "/api/v1/partners":
    {
      get: operations["partners_api_v1_partners_get"];
    };
  "/api/v1/partners/{partner_id}":
    {
      get: operations["partner_detail_api_v1_partners__partner_id__get"];
    };
  "/api/v1/peer-analogues":
    {
      get: operations["peer_analogue_catalogue_api_v1_peer_analogues_get"];
    };
  "/api/v1/peer-analogues/match":
    {
      post: operations["peer_analogue_match_api_v1_peer_analogues_match_post"];
    };
  "/api/v1/presentations":
    {
      get: operations["presentations_api_v1_presentations_get"];
    };
  "/api/v1/presentations/generate":
    {
      post: operations["presentation_generate_api_v1_presentations_generate_post"];
    };
  "/api/v1/presentations/{presentation_id}":
    {
      get: operations["presentation_status_api_v1_presentations__presentation_id__get"];
    };
  "/api/v1/presentations/{presentation_id}/download":
    {
      get: operations["presentation_download_api_v1_presentations__presentation_id__download_get"];
    };
  "/api/v1/presentations/{presentation_id}/manifest":
    {
      get: operations["presentation_manifest_api_v1_presentations__presentation_id__manifest_get"];
    };
  "/api/v1/ratings":
    {
      get: operations["ratings_api_v1_ratings_get"];
    };
  "/api/v1/ratings/calculate":
    {
      post: operations["rating_calculate_api_v1_ratings_calculate_post"];
    };
  "/api/v1/ratings/sensitivity":
    {
      post: operations["rating_sensitivity_api_v1_ratings_sensitivity_post"];
    };
  "/api/v1/roll-rates":
    {
      get: operations["roll_rates_api_v1_roll_rates_get"];
    };
  "/api/v1/root-cause":
    {
      get: operations["root_cause_api_v1_root_cause_get"];
    };
  "/api/v1/scenarios":
    {
      get: operations["scenarios_api_v1_scenarios_get"];
    };
  "/api/v1/scenarios/run":
    {
      post: operations["scenario_run_api_v1_scenarios_run_post"];
    };
  "/api/v1/segments":
    {
      get: operations["segments_api_v1_segments_get"];
    };
  "/api/v1/strategy-comparison":
    {
      get: operations["strategy_comparison_api_v1_strategy_comparison_get"];
    };
  "/api/v1/tableau/extract":
    {
      post: operations["tableau_extract_api_v1_tableau_extract_post"];
    };
  "/api/v1/tableau/extract/download":
    {
      get: operations["tableau_extract_download_api_v1_tableau_extract_download_get"];
    };
  "/api/v1/tableau/extract/manifest":
    {
      get: operations["tableau_extract_manifest_api_v1_tableau_extract_manifest_get"];
    };
  "/api/v1/trends":
    {
      get: operations["trends_api_v1_trends_get"];
    };
  "/api/v1/vendor-performance":
    {
      get: operations["vendors_api_v1_vendor_performance_get"];
    };
  "/api/v1/vendor-ratings":
    {
      get: operations["vendor_ratings_api_v1_vendor_ratings_get"];
    };
  "/api/v1/vendor-reallocation/run":
    {
      post: operations["vendor_reallocation_api_v1_vendor_reallocation_run_post"];
    };
  "/api/v1/vendors":
    {
      get: operations["vendors_api_v1_vendors_get"];
    };
  "/api/v1/vendors/{vendor_id}":
    {
      get: operations["vendor_detail_api_v1_vendors__vendor_id__get"];
    };
  "/api/v1/vintages":
    {
      get: operations["vintages_api_v1_vintages_get"];
    };
  "/api/v1/workspaces":
    {
      get: operations["workspaces_api_v1_workspaces_get"];
      post: operations["create_workspace_api_v1_workspaces_post"];
    };
  "/api/v1/workspaces/{workspace_id}":
    {
      get: operations["workspace_detail_api_v1_workspaces__workspace_id__get"];
      patch: operations["update_workspace_api_v1_workspaces__workspace_id__patch"];
    };
  "/api/v1/workspaces/{workspace_id}/export":
    {
      post: operations["export_workspace_api_v1_workspaces__workspace_id__export_post"];
    };
  "/api/v1/workspaces/{workspace_id}/refresh":
    {
      post: operations["refresh_workspace_api_v1_workspaces__workspace_id__refresh_post"];
    };
  "/api/v1/workspaces/{workspace_id}/run":
    {
      post: operations["run_workspace_api_v1_workspaces__workspace_id__run_post"];
    };
}

export type HttpMethod =
  | "get"
  | "post"
  | "put"
  | "patch"
  | "delete"
  | "options"
  | "head"
  | "trace";
export type ApiPath = keyof paths;
export type ApiMethod<P extends ApiPath> = Extract<keyof paths[P], HttpMethod>;
export type OperationFor<
  P extends ApiPath,
  M extends ApiMethod<P>,
> = paths[P][M];

type ContentValue<C> = C extends Record<string, unknown>
  ? "application/json" extends keyof C
    ? C["application/json"]
    : C[keyof C]
  : never;
type ResponsesOf<T> = T extends { responses: infer R } ? R : never;

export type RequestBodyFor<
  P extends ApiPath,
  M extends ApiMethod<P>,
> = OperationFor<P, M> extends { requestBody?: infer B }
  ? NonNullable<B> extends { content: infer C }
    ? ContentValue<C>
    : never
  : never;

export type ResponseStatusFor<
  P extends ApiPath,
  M extends ApiMethod<P>,
> = keyof ResponsesOf<OperationFor<P, M>>;

export type ResponseBodyFor<
  P extends ApiPath,
  M extends ApiMethod<P>,
  S extends ResponseStatusFor<P, M>,
> = ResponsesOf<OperationFor<P, M>>[S] extends { content: infer C }
  ? ContentValue<C>
  : never;
