targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('azd environment name; used to name the resource group and resources')
param environmentName string

@minLength(1)
@description('Primary location for all resources (must offer the chosen model)')
param location string

@description('Model deployed in Foundry and used by the KYC agent')
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'
param modelCapacity int = 30

@description('Set by azd after the first deploy; placeholder image until then')
param m365HostImage string = ''

@description('Object id of the developer running azd, granted Azure AI User for local runs and evals')
param principalId string = ''

var tags = { 'azd-env-name': environmentName, workload: 'fsi-kyc-agents', 'data-classification': 'synthetic' }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    tags: tags
    resourceToken: toLower(uniqueString(subscription().id, environmentName, location))
    modelName: modelName
    modelVersion: modelVersion
    modelCapacity: modelCapacity
    m365HostImage: m365HostImage
    principalId: principalId
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryLoginServer
output FOUNDRY_PROJECT_ENDPOINT string = resources.outputs.foundryProjectEndpoint
output FOUNDRY_MODEL_DEPLOYMENT string = modelName
output AZURE_OPENAI_ENDPOINT string = resources.outputs.openAiEndpoint
output APPLICATIONINSIGHTS_CONNECTION_STRING string = resources.outputs.appInsightsConnectionString
output AZURE_KEY_VAULT_NAME string = resources.outputs.keyVaultName
output AGENT_MANAGED_IDENTITY_CLIENT_ID string = resources.outputs.identityClientId
output SERVICE_M365_HOST_NAME string = resources.outputs.m365HostName
output BOT_MESSAGES_ENDPOINT string = 'https://${resources.outputs.m365HostFqdn}/api/messages'
