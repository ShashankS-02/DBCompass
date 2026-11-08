terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
}

variable "location" {
  default = "westeurope"
}

resource "azurerm_resource_group" "claims" {
  name     = "rg-claims-hub-prod"
  location = var.location
}

resource "azurerm_virtual_network" "claims" {
  name                = "vnet-claims-hub"
  location            = azurerm_resource_group.claims.location
  resource_group_name = azurerm_resource_group.claims.name
  address_space       = ["10.40.0.0/16"]
}

resource "azurerm_subnet" "data" {
  name                 = "snet-data"
  resource_group_name  = azurerm_resource_group.claims.name
  virtual_network_name = azurerm_virtual_network.claims.name
  address_prefixes     = ["10.40.1.0/24"]
}

# The database target is decided by the platform team (DBCompass assessment pending).
