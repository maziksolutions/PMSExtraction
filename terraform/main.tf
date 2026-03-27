terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Uncomment to use Azure Blob as remote state backend:
  # backend "azurerm" {
  #   resource_group_name  = "rg-tfstate"
  #   storage_account_name = "sttfstatemaritime"
  #   container_name       = "tfstate"
  #   key                  = "maritime-pms.terraform.tfstate"
  # }
}

provider "azurerm" {
  subscription_id = var.subscription_id
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

# ---------------------------------------------------------------------------
# Random suffix to ensure globally unique names
# ---------------------------------------------------------------------------
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  suffix = lower(random_id.suffix.hex)
  tags = {
    environment = var.environment
    project     = var.app_name
    managed_by  = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.tags
}

# ---------------------------------------------------------------------------
# Azure Container Registry
# ---------------------------------------------------------------------------
resource "azurerm_container_registry" "acr" {
  name                = "acr${replace(var.app_name, "-", "")}${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Azure Container Apps Environment
# ---------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-${var.app_name}-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${var.app_name}-${local.suffix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# ---------------------------------------------------------------------------
# Backend Container App (FastAPI)
# ---------------------------------------------------------------------------
resource "azurerm_container_app" "backend" {
  name                         = "ca-${var.app_name}-backend"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }

  secret {
    name  = "secret-key"
    value = "change-me-in-production-min-32-chars"
  }

  template {
    min_replicas = 1
    max_replicas = 5

    container {
      name   = "backend"
      image  = var.backend_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name        = "SECRET_KEY"
        secret_name = "secret-key"
      }

      env {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://${var.db_admin_username}:${var.db_admin_password}@${azurerm_postgresql_flexible_server.db.fqdn}:5432/pms_extraction"
      }

      env {
        name  = "REDIS_URL"
        value = "rediss://:${azurerm_redis_cache.main.primary_access_key}@${azurerm_redis_cache.main.hostname}:${azurerm_redis_cache.main.ssl_port}"
      }

      env {
        name  = "ALLOWED_ORIGINS"
        value = "[\"https://${azurerm_static_web_app.frontend.default_host_name}\"]"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

# ---------------------------------------------------------------------------
# Frontend — Azure Static Web App
# ---------------------------------------------------------------------------
resource "azurerm_static_web_app" "frontend" {
  name                = "swa-${var.app_name}-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = "westeurope"  # Static Web Apps have limited region availability
  sku_tier            = var.frontend_sku
  sku_size            = var.frontend_sku
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Azure Database for PostgreSQL Flexible Server
# ---------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "db" {
  name                   = "psql-${var.app_name}-${local.suffix}"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "15"
  administrator_login    = var.db_admin_username
  administrator_password = var.db_admin_password
  storage_mb             = 32768
  sku_name               = "B_Standard_B1ms"

  backup_retention_days        = 7
  geo_redundant_backup_enabled = false

  tags = local.tags
}

resource "azurerm_postgresql_flexible_server_database" "pms" {
  name      = "pms_extraction"
  server_id = azurerm_postgresql_flexible_server.db.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# Allow Container App environment to reach PostgreSQL
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.db.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# ---------------------------------------------------------------------------
# Azure Cache for Redis
# ---------------------------------------------------------------------------
resource "azurerm_redis_cache" "main" {
  name                = "redis-${var.app_name}-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  capacity            = 1
  family              = "C"
  sku_name            = "Standard"
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Azure Key Vault
# ---------------------------------------------------------------------------
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "main" {
  name                        = "kv-${replace(var.app_name, "-", "")}${local.suffix}"
  resource_group_name         = azurerm_resource_group.main.name
  location                    = azurerm_resource_group.main.location
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  sku_name                    = "standard"
  soft_delete_retention_days  = 7
  purge_protection_enabled    = false

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = [
      "Get", "List", "Set", "Delete", "Purge", "Recover"
    ]
  }

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Azure Blob Storage (for document uploads)
# ---------------------------------------------------------------------------
resource "azurerm_storage_account" "docs" {
  name                     = "st${replace(var.app_name, "-", "")}${local.suffix}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  blob_properties {
    versioning_enabled = true

    delete_retention_policy {
      days = 30
    }
  }

  tags = local.tags
}

resource "azurerm_storage_container" "vessel_docs" {
  name                  = "vessel-documents"
  storage_account_name  = azurerm_storage_account.docs.name
  container_access_type = "private"
}
