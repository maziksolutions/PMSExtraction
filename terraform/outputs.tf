output "backend_url" {
  description = "Public HTTPS URL of the FastAPI backend Container App"
  value       = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}

output "frontend_url" {
  description = "Default hostname of the Azure Static Web App frontend"
  value       = "https://${azurerm_static_web_app.frontend.default_host_name}"
}

output "db_connection_string" {
  description = "PostgreSQL Flexible Server connection string (asyncpg format)"
  value       = "postgresql+asyncpg://${var.db_admin_username}:${var.db_admin_password}@${azurerm_postgresql_flexible_server.db.fqdn}:5432/pms_extraction"
  sensitive   = true
}

output "registry_url" {
  description = "Azure Container Registry login server URL"
  value       = azurerm_container_registry.acr.login_server
}

output "storage_account_name" {
  description = "Azure Blob Storage account name for vessel documents"
  value       = azurerm_storage_account.docs.name
}

output "key_vault_uri" {
  description = "Azure Key Vault URI"
  value       = azurerm_key_vault.main.vault_uri
}

output "redis_hostname" {
  description = "Redis cache hostname"
  value       = azurerm_redis_cache.main.hostname
}
