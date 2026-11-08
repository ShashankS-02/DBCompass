terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = "asia-south1"
}

variable "project_id" {
  type = string
}

resource "google_compute_network" "docs" {
  name                    = "docs-assistant-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "docs" {
  name          = "docs-assistant-subnet"
  ip_cidr_range = "10.60.0.0/20"
  region        = "asia-south1"
  network       = google_compute_network.docs.id
}

resource "google_cloud_run_v2_service" "api" {
  name     = "docs-assistant-api"
  location = "asia-south1"

  template {
    containers {
      image = "asia-south1-docker.pkg.dev/${var.project_id}/docs/api:latest"
    }
  }
}

# Database target to be chosen with DBCompass.
