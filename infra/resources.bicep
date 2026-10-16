param location string
param tags object
param resourceToken string
param modelName string
param modelVersion string
param modelCapacity int
param m365HostImage string
param principalId string

var roles = {
  azureAiUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
  cognitiveServicesOpenAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
}

// ---------- Identity: one user-assigned identity per agent (least privilege) ----------
resource agentIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-kyc-agent-${resourceToken}'
  location: location
  tags: tags
}

// ---------- Observability ----------
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// ---------- Microsoft Foundry (AI Services account + project + model) ----------
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'aif-${resourceToken}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'aif-${resourceToken}'
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'kyc-aml'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'FSI KYC/AML agents'
    description: 'Workshop project: build, manage and govern agents'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: modelName
  sku: {
    name: 'GlobalStandard'
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  parent: foundry
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: { key: appInsights.properties.ConnectionString }
    metadata: { ApiType: 'Azure', ResourceId: appInsights.id }
  }
}

// ---------- Secrets ----------
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${resourceToken}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// ---------- Container hosting for the M365 Agents SDK host ----------
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cr${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource m365Host 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-m365-host-${resourceToken}'
  location: location
  tags: union(tags, { 'azd-service-name': 'm365-host' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${agentIdentity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 3978
        transport: 'auto'
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: agentIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'm365-host'
          image: empty(m365HostImage) ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' : m365HostImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'DEMO_MODE', value: 'live' }
            { name: 'PORT', value: '3978' }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProject.properties.endpoints['AI Foundry API'] }
            { name: 'FOUNDRY_MODEL_DEPLOYMENT', value: modelName }
            { name: 'FOUNDRY_AGENT_NAME', value: 'kyc-aml-agent' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'AZURE_CLIENT_ID', value: agentIdentity.properties.clientId }
            { name: 'KYC_DATA_DIR', value: '/app/.data' }
            { name: 'SAR_AUTO_APPROVE', value: 'false' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [ acrPull ]
}

// ---------- RBAC: least privilege for the agent identity (+ optional developer) ----------
resource agentFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, agentIdentity.id, roles.azureAiUser)
  scope: foundry
  properties: {
    principalId: agentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.azureAiUser)
  }
}

resource agentOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, agentIdentity.id, roles.cognitiveServicesOpenAiUser)
  scope: foundry
  properties: {
    principalId: agentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAiUser)
  }
}

resource agentKvSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, agentIdentity.id, roles.keyVaultSecretsUser)
  scope: keyVault
  properties: {
    principalId: agentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
  }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, agentIdentity.id, roles.acrPull)
  scope: registry
  properties: {
    principalId: agentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

resource devFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(foundry.id, principalId, roles.azureAiUser)
  scope: foundry
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.azureAiUser)
  }
}

resource devOpenAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(foundry.id, principalId, roles.cognitiveServicesOpenAiUser)
  scope: foundry
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAiUser)
  }
}

output registryLoginServer string = registry.properties.loginServer
output foundryProjectEndpoint string = foundryProject.properties.endpoints['AI Foundry API']
output openAiEndpoint string = 'https://${foundry.properties.customSubDomainName}.openai.azure.com/'
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output keyVaultName string = keyVault.name
output identityClientId string = agentIdentity.properties.clientId
output m365HostName string = m365Host.name
output m365HostFqdn string = m365Host.properties.configuration.ingress.fqdn
