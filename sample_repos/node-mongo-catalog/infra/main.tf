provider "azurerm" {
  features {}
}

resource "azurerm_cosmosdb_account" "catalog" {
  name                = "catalog-cosmos"
  location            = "centralindia"
  resource_group_name = "catalog-rg"
  offer_type          = "Standard"
  kind                = "MongoDB"
}
