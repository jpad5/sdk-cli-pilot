# Lab 10 - Teardown

```powershell
azd down --purge --force                         # deletes the resource group; purges Foundry and Key Vault soft-deletes
cd src\atk-app; atk uninstall --env dev -i false  # removes the Teams app / bot registration (if provisioned)
a365 --help                                      # use the cleanup command for your CLI version to remove the blueprint
gh repo delete <you>/<fork> --yes                # optional: your workshop fork
Remove-Item -Recurse -Force .data, .env.azd -ErrorAction SilentlyContinue
```

For the Copilot Studio intake agent, delete it in the Copilot Studio portal and remove its app registration in Entra.
