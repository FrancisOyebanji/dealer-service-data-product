# Terraform — GCP data platform infrastructure for the reference architecture.
# Provisions the BigQuery datasets, Cloud Storage landing, Pub/Sub streaming
# ingestion, a policy tag for column-level security, and least-privilege IAM.

terraform {
  required_providers { google = { source = "hashicorp/google" } }
}
variable "project_id" { type = string }
variable "region"     { type = string, default = "us-central1" }

# --- Storage: landing / bronze ---
resource "google_storage_bucket" "landing" {
  name                        = "${var.project_id}-dealer-landing"
  location                    = var.region
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition { age = 7 }            # purge raw after the reprocessing window
    action { type = "Delete" }
  }
}

# --- BigQuery: curated + gold datasets ---
resource "google_bigquery_dataset" "curated" {
  dataset_id                 = "dealer_service"
  location                   = "US"
  default_partition_expiration_ms = 220752000000   # ~7 years
  description                = "Curated dealer-service analytics warehouse"
}
resource "google_bigquery_dataset" "gold" {
  dataset_id  = "dealer_service_gold"
  location    = "US"
  description = "Curated marts for BI consumption"
}

# --- Streaming ingestion ---
resource "google_pubsub_topic" "service_events" { name = "service-events" }
resource "google_pubsub_subscription" "service_events" {
  name  = "service-events-sub"
  topic = google_pubsub_topic.service_events.name
  ack_deadline_seconds = 60
}

# --- Column-level security: policy tag taxonomy for PII ---
resource "google_data_catalog_taxonomy" "pii" {
  display_name = "dealer-pii"
  region       = var.region
  activated_policy_types = ["FINE_GRAINED_ACCESS_CONTROL"]
}
resource "google_data_catalog_policy_tag" "customer_pii" {
  taxonomy     = google_data_catalog_taxonomy.pii.id
  display_name = "customer_pii"
}

# --- Least-privilege IAM: analysts read gold only ---
resource "google_bigquery_dataset_iam_member" "analyst_gold_read" {
  dataset_id = google_bigquery_dataset.gold.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "group:analysts@example.com"
}
