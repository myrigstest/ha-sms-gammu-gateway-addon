# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] - 2025-10-11

### Highlights
- Incoming SMS are now removed from the SIM immediately after being published to Home Assistant to avoid duplicates.
- MQTT password field in the add-on configuration is now masked (`password?`) to keep credentials obscured in the UI.
- Documentation refreshed to point to the new repository location.

### Migration Notes
- After upgrading, restart the add-on so the updated configuration schema takes effect.

## [2.0.0] - 2025-10-11

### Highlights
- First standalone release with full Unicode (Cyrillic) support enabled by default for REST, MQTT and UI sending flows.
- Credentials now sourced through Home Assistant `!secret` references, keeping sensitive data out of `options.json`.
- Debug mode delivers verbose logs plus Gammu traces for easier modem diagnostics.
- Incoming SMS are now removed from the SIM immediately after being published to Home Assistant to avoid duplicates.
- Project moved under the new repository https://github.com/dima11235/ha-sms-gammu-gateway-addon with refreshed documentation and credits.

### Migration Notes
- Ensure `secrets.yaml` contains `gammu_username`, `gammu_password`, `mqtt_username`, `mqtt_password`.
- Restart the add-on after upgrading so the new configuration scheme takes effect.
