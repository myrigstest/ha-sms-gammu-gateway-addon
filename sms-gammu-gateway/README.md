# SMS Gammu Gateway Add-on

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]
![Supports armhf Architecture][armhf-shield]
![Supports armv7 Architecture][armv7-shield]
![Supports i386 Architecture][i386-shield]

REST API SMS Gateway using python-gammu for USB GSM modems (SIM800L, Huawei, etc.)

## About

This add-on provides a complete SMS gateway solution for Home Assistant, replacing the deprecated "SMS notifications via GSM-modem" integration. It offers both REST API and MQTT interfaces for sending and receiving SMS messages through USB GSM modems.

**Maintained by** [dima11235](https://github.com/dima11235).

**Based on** [pajikos/sms-gammu-gateway](https://github.com/pajikos/sms-gammu-gateway) (Apache License 2.0) and the original Home Assistant add-on by [PavelVe](https://github.com/PavelVe).

## 🌟 Key Features

### 📱 SMS Management
- **Send SMS** via REST API, MQTT, or Home Assistant UI
- **Receive SMS** with automatic MQTT notifications
- **Text Input Fields** directly in Home Assistant device
- **Smart Button** for easy SMS sending from UI
- **Phone Number Persistence** - keeps number for multiple messages
- **Automatic Unicode Detection** - Cyrillic and other non-ASCII texts are handled without extra flags

### 📊 Device Monitoring
- **Signal Strength** sensor with percentage display
- **Network Info** showing operator name and status
- **Last SMS Received** sensor with full message details
- **SMS Send Status** tracking success/error states
- **Real-time Updates** via MQTT with auto-discovery

### 🔧 Integration Options
- **REST API** with Swagger documentation at `/docs/`
- **MQTT Integration** with Home Assistant auto-discovery
- **Native HA Service** `send_sms` for automations
- **Notify Platform** support for alerts
- **Web UI** accessible through Ingress

## Prerequisites

- USB GSM modem supporting AT commands (SIM800L, Huawei E1750, etc.)
- Modem must appear as `/dev/ttyUSB*` device
- SIM card with SMS capability
- Optional: MQTT broker for full integration

## Installation

1. Add repository to your Home Assistant:
   ```
   https://github.com/dima11235/ha-sms-gammu-gateway-addon
   ```
2. Find **SMS Gammu Gateway** in add-on store
3. Click Install
4. Configure the add-on (see below)
5. Start the add-on

## Configuration

### Basic Settings

| Option | Default | Description |
|--------|---------|-------------|
| `device_path` | `/dev/ttyUSB0` | Path to your GSM modem device |
| `pin` | `""` | SIM card PIN (leave empty if no PIN) |
| `port` | `5000` | API port |
| `ssl` | `false` | Enable HTTPS |
| `username` | `!secret gammu_username` | API username (stored in `secrets.yaml`) |
| `password` | `!secret gammu_password` | API password (stored in `secrets.yaml`) |
| `debug` | `false` | Enable verbose logging and create `/data/gammu-debug.log` |

### MQTT Settings (Optional)

| Option | Default | Description |
|--------|---------|-------------|
| `mqtt_enabled` | `false` | Enable MQTT integration |
| `mqtt_host` | `core-mosquitto` | MQTT broker hostname |
| `mqtt_port` | `1883` | MQTT broker port |
| `mqtt_username` | `!secret mqtt_username` | MQTT username (stored in `secrets.yaml`) |
| `mqtt_password` | `!secret mqtt_password` | MQTT password (stored in `secrets.yaml`) |
| `mqtt_topic_prefix` | `homeassistant/sensor/sms_gateway` | Topic prefix |
| `sms_monitoring_enabled` | `true` | Auto-detect incoming SMS |
| `sms_check_interval` | `60` | SMS check interval (seconds) |

> ℹ️ Все значения с `!secret` подставляются автоматически из `/config/secrets.yaml` (или `/data/secrets.yaml`) при запуске аддона.

### Example Configuration

```yaml
device_path: "/dev/ttyUSB0"
pin: ""
port: 5000
ssl: false
username: "!secret gammu_username"
password: "!secret gammu_password"
mqtt_enabled: true
mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_username: "!secret mqtt_username"
mqtt_password: "!secret mqtt_password"
sms_monitoring_enabled: true
sms_check_interval: 60
debug: false
```

## 🏠 Home Assistant Integration

### Method 1: MQTT with Auto-Discovery (Recommended)

Enable MQTT in configuration and the add-on will automatically create:
- 📊 **GSM Signal Strength** sensor
- 🌐 **GSM Network** sensor  
- 💬 **Last SMS Received** sensor
- ✅ **SMS Send Status** sensor
- 📱 **Phone Number** text input
- 💬 **Message Text** text input
- 🔘 **Send SMS** button

All entities appear under device **"SMS Gateway"** in Home Assistant.

![MQTT Device Overview](https://raw.githubusercontent.com/dima11235/ha-sms-gammu-gateway-addon/main/sms-gammu-gateway/images/mqtt-device.png)

### Method 2: RESTful Notify

Add to your `configuration.yaml`:

```yaml
notify:
  - name: SMS Gateway
    platform: rest
    resource: http://192.168.1.x:5000/sms
    method: POST_JSON
    authentication: basic
    username: admin
    password: your_password
    target_param_name: number
    message_param_name: message
```

![Actions Notify Example](https://raw.githubusercontent.com/dima11235/ha-sms-gammu-gateway-addon/main/sms-gammu-gateway/images/actions-notify.png)

### Method 3: Direct Service Calls

Use in automations:

```yaml
service: mqtt.publish
data:
  topic: "homeassistant/sensor/sms_gateway/send"
  payload: '{"number": "+420123456789", "text": "Alert!"}'
```

## 📝 Usage Examples

### Send SMS via Button
1. Go to **SMS Gateway** device in Home Assistant
2. Fill **Phone Number** field (e.g., +420123456789)
3. Fill **Message Text** field
4. Click **Send SMS** button
5. Message field auto-clears, number stays for next message

### Automation Example

```yaml
automation:
  - alias: Door Alert SMS
    trigger:
      platform: state
      entity_id: binary_sensor.door
      to: 'on'
    action:
      service: notify.sms_gateway
      data:
        message: 'Door opened!'
        target: '+420123456789'
```

### REST API Example

```bash
curl -X POST http://192.168.1.x:5000/sms \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{"text": "Test SMS", "number": "+420123456789"}'
```

## 🔧 API Documentation

### Swagger UI
Access full API documentation at: `http://your-ha-ip:5000/docs/`

![Swagger UI Documentation](https://raw.githubusercontent.com/dima11235/ha-sms-gammu-gateway-addon/main/sms-gammu-gateway/images/swagger-ui.png)

### Main Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/sms` | Send SMS | Yes |
| GET | `/sms` | Get all SMS | Yes |
| GET | `/sms/{id}` | Get specific SMS | Yes |
| DELETE | `/sms/{id}` | Delete SMS | Yes |
| GET | `/status/signal` | Signal strength | No |
| GET | `/status/network` | Network info | No |
| GET | `/status/reset` | Reset modem | No |

## 🚨 Troubleshooting

### Device Not Found
- Check USB connection: `ls /dev/ttyUSB*`
- Verify device permissions
- Try different USB ports
- Check `dmesg | grep tty` for device detection

### SMS Not Sending
- Check signal strength (should be > 20%)
- Verify SIM card has credit
- Ensure PIN is correct or disabled
- Check network registration status

### Enable Debug Logs
- Set `debug: true` in the add-on configuration
- Restart the add-on to regenerate verbose logs
- Review the supervisor log and the `/data/gammu-debug.log` file for modem communication traces
- Turn debug back off once finished to avoid large log files

### MQTT Not Working
- Verify MQTT broker is running
- Check MQTT credentials
- Look for connection errors in add-on logs
- Ensure topic prefix doesn't conflict

### Code 69 Error
- This is SMSC (SMS Center) issue
- Add-on automatically uses Location 1 fallback
- Works same as REST API

## 📋 Version History

See [CHANGELOG.md](./CHANGELOG.md) for detailed version history.

## 🤝 Support & Acknowledgements

- **Issues**: [GitHub Issues](https://github.com/dima11235/ha-sms-gammu-gateway-addon/issues)
- **Documentation**: This page and Swagger UI at `/docs/`
- **Source**: Based on [sms-gammu-gateway](https://github.com/pajikos/sms-gammu-gateway)
- **Huge thanks** to [PavelVe](https://github.com/PavelVe) for the original Home Assistant add-on that inspired and powered this fork.

## 📜 License

Based on pajikos/sms-gammu-gateway, licensed under Apache License 2.0.

---

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg
