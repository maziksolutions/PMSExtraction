variable "subscription_id" {
  description = "Azure Subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the Azure Resource Group to create"
  type        = string
  default     = "rg-maritime-pms"
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "uksouth"
}

variable "environment" {
  description = "Deployment environment (dev | staging | prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "app_name" {
  description = "Short application identifier used in resource names"
  type        = string
  default     = "maritime-pms"
}

variable "db_admin_username" {
  description = "Administrator username for PostgreSQL Flexible Server"
  type        = string
  default     = "pmsadmin"
  sensitive   = true
}

variable "db_admin_password" {
  description = "Administrator password for PostgreSQL Flexible Server"
  type        = string
  sensitive   = true
}

variable "backend_image" {
  description = "Docker image for the backend Container App (tag included)"
  type        = string
  default     = "nginx:alpine"  # placeholder; overridden in CI
}

variable "frontend_sku" {
  description = "Azure Static Web App SKU (Free | Standard)"
  type        = string
  default     = "Standard"
}
