# Installation, Updates And Removal

**UniFi Drive / UNAS** is an unofficial community integration. The repository is
`memphi2/ha-unifi-drive`; its Home Assistant domain and installed folder are
`unifi_unas`. Marketplace changes the installation UI, not this identity.

## Requirements

- Home Assistant `2024.8.0` or newer is the advertised minimum for this line.
  The tested versions and outstanding compatibility work are in [lts.md](lts.md).
- A compatible UniFi Drive / UNAS system reachable from Home Assistant.
- Local credentials with the permissions needed for the enabled features.
  Start with monitoring; optional controls remain experimental.

Use a published release for normal operation. A development checkout or a copied
test build is not a published Marketplace release. The instructions for HA
`2026.11` describe Marketplace, not a claim of completed November runtime tests.

## Home Assistant Marketplace

For Home Assistant `2026.11` and newer:

1. Open `Settings` -> `Marketplace`.
2. Search for `UniFi Drive` and select **UniFi Drive / UNAS** by **memphi2**.
3. Install the integration and confirm the community-integration notice.
4. Open `Settings` -> `Devices & services` -> `Add integration` and select
   **UniFi Drive / UNAS**.
5. Select a discovered device or enter its host manually, then configure
   credentials and optional features.

The repository is in the shared catalog; adding a custom repository is not
needed. A first install can load immediately when the integration has not
already been loaded. Follow any restart request after an update or removal.
Copying new files alone does not replace code already running in Home Assistant.

Marketplace uses the same `hacs.json` metadata and catalog as HACS. Do not rename
that file or the integration folder. See the official
[Marketplace guide](https://contributors.home-assistant.io/marketplace/how-it-works/).

## Home Assistant Before 2026.11

1. Open HACS and search for **UniFi Drive / UNAS**.
2. Download the integration and restart Home Assistant.
3. Add it under `Settings` -> `Devices & services`.

HACS uses the same catalog, so no custom repository is required. Existing
`hacs_repository` links continue to work with HACS and with Marketplace.

## Existing Installations

For integration `0.8.0` and newer, keep existing config entries and user-assigned
names. Upgrading Home Assistant from HACS to Marketplace does not require
reinstalling this integration or changing its domain. Do not install a duplicate
copy or delete a working entry just to change the installation method.

For a changed device address, use `Reconfigure` on the existing entry. For
authentication problems, follow the reauthentication flow. An intentionally
powered-off NAS does not need a reinstall; use Wake-on-LAN when configured.

Versions before `0.8.0` used the old domain and need the separate procedure below.

## Updates

1. Back up Home Assistant and read the integration's release notes.
2. In Marketplace, use the update offered under `Settings` -> `Updates`.
   On older Home Assistant versions, use HACS.
3. Install the update and complete the requested Home Assistant restart.
4. Check that the existing entry loads and monitoring recovers when the NAS is
   online. After connection failures, monitoring retains last-known readings
   where available; these are not live measurements. Check Device online before
   relying on them. Controls remain unavailable offline except configured WOL.

Each release's `hacs.json` declares its minimum HA version. An incompatible
release may not be offered. Catalog refreshes can also delay a newly published
version by several hours; reinstalling is not a way to force an update.
See the official [release guide](https://contributors.home-assistant.io/marketplace/guides/releases/).

## Upgrading From Before 0.8.0

This is the old integration-domain change, not a Marketplace migration.

1. Back up Home Assistant. Record the integration options and any entity
   references used in dashboards, automations and scripts.
2. Delete the old UniFi Drive config entries under `Settings` ->
   `Devices & services`.
3. Uninstall the old integration repository through HACS or Marketplace. This
   removes its managed files; deleting only the device/config entry does not.
4. For a manual installation, or if the old folder remains after uninstalling,
   remove only `/config/custom_components/unifi_drive/`. Do not edit `.storage`.
5. Restart Home Assistant, then install the current release using the appropriate
   instructions above and add **UniFi Drive / UNAS** again.
6. Verify the new entities and update dashboard/automation references as needed.

The new installation belongs in `/config/custom_components/unifi_unas/`.
Do not keep both integration domains installed for the same NAS.

## Manual Installation

Download the selected release and copy the contents of its
`custom_components/unifi_unas/` folder to:

```text
/config/custom_components/unifi_unas/
```

The attached `unifi_unas.zip` also contains that integration folder. Keep all its
files, including `translations/`. Do not copy the whole repository, tests or
`hacs.json` into the integration directory.

For a manual update, back up the old integration folder outside
`custom_components`, then replace it with one complete copy from the new version
so obsolete files are not left behind. Leave Home Assistant's `.storage` and
existing config entries alone. Restart Home Assistant and add an entry only when
one does not already exist.

## Removal

1. Delete the desired UniFi Drive / UNAS config entries under `Settings` ->
   `Devices & services`. Their entities are removed, which affects references
   in dashboards, automations and scripts.
2. To uninstall the code as well, delete all entries of this integration, then
   remove its repository through Marketplace or HACS.
3. For a manual installation, remove only
   `/config/custom_components/unifi_unas/` after its entries have been removed.
4. Complete the requested Home Assistant restart.

Removing the integration does not delete NAS data or revoke device-side API
keys/accounts. Revoke exposed credentials through the device's supported account
controls, not by editing Home Assistant storage.
