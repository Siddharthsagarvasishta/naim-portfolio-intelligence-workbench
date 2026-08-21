# Optional VBScript Legacy Bridge

These minimal Windows scripts copy an approved export to a reporting folder, write a timestamped run log and optionally open a workbook. They do not calculate metrics.

Edit `naim_refresh.example.ini`, rename it for local use and keep it outside source control if it contains environment-specific locations. Both source and destination must sit under the configured approved roots. No credentials are supported.

VBScript is a legacy compatibility bridge. Prefer Python, PowerShell or an enterprise scheduler for new automation. Review and sign scripts where organizational policy requires it.

