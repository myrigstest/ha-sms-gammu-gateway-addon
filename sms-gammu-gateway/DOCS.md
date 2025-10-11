# SMS Gammu Gateway - Documentation

## 🚀 Quick Start

### Step 1: Connect GSM Modem
- Connect your USB GSM modem (SIM800L, Huawei, etc.)
- Verify detection: Settings → System → Hardware → Search for "ttyUSB"

### Step 2: Basic Configuration
```yaml
device_path: "/dev/ttyUSB0"  # Path to modem
username: "admin"             # Change this!
password: "strong_password"   # Change this!
```

### Step 3: Enable MQTT (Recommended)
```yaml
mqtt_enabled: true
mqtt_host: "core-mosquitto"
```

### Step 4: Start the Add-on
- Click **START**
- Check the log for successful startup
- New device **SMS Gateway** will appear in HA

## 📱 How to Send SMS

### Method 1: UI Button (Easiest)
1. Go to **Devices** → **SMS Gateway**
2. Fill **Phone Number** (e.g., +420123456789)
3. Fill **Message Text**
4. Click **Send SMS**

### Method 2: Notify Service
```yaml
service: notify.sms_gateway
data:
  message: "Test message"
  target: "+420123456789"
```

### Method 3: MQTT
```yaml
service: mqtt.publish
data:
  topic: "homeassistant/sensor/sms_gateway/send"
  payload: '{"number": "+420123456789", "text": "Alert!"}'
```

### Method 4: REST API
```bash
curl -X POST http://192.168.1.x:5000/sms \
  -u admin:password \
  -d '{"text": "Test", "number": "+420123456789"}'
```

## 🔧 Configuration

### Basic Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `device_path` | `/dev/ttyUSB0` | Path to GSM modem |
| `pin` | `""` | SIM card PIN (empty = no PIN) |
| `port` | `5000` | API port |
| `username` | `admin` | API username |
| `password` | `password` | **⚠️ CHANGE THIS!** |

### MQTT Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `mqtt_enabled` | `false` | Enable MQTT integration |
| `mqtt_host` | `core-mosquitto` | MQTT broker |
| `mqtt_port` | `1883` | MQTT port |
| `mqtt_username` | `""` | MQTT username |
| `mqtt_password` | `""` | MQTT password |
| `sms_monitoring_enabled` | `true` | Detect incoming SMS |
| `sms_check_interval` | `60` | SMS check interval (seconds) |

## 📊 MQTT Sensors

After enabling MQTT, these entities are automatically created:

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.gsm_signal_strength` | Sensor | Signal strength in % |
| `sensor.gsm_network` | Sensor | Network operator name |
| `sensor.last_sms_received` | Sensor | Last received SMS |
| `sensor.sms_send_status` | Sensor | SMS send status |
| `text.sms_gateway_phone_number` | Text input | Phone number field |
| `text.sms_gateway_message_text` | Text input | Message text field |
| `button.send_sms` | Button | Send SMS button |

## 🎯 Automation Examples

### SMS on Door Open
```yaml
automation:
  - alias: "Security - Door Opened"
    trigger:
      platform: state
      entity_id: binary_sensor.front_door
      to: "on"
    action:
      service: notify.sms_gateway
      data:
        message: "ALERT: Front door opened!"
        target: "+420123456789"
```

### SMS on Low Temperature
```yaml
automation:
  - alias: "Freeze Alert"
    trigger:
      platform: numeric_state
      entity_id: sensor.outside_temperature
      below: 0
    action:
      service: notify.sms_gateway
      data:
        message: "Warning: Freezing temperature! Current: {{ states('sensor.outside_temperature') }}°C"
        target: "+420123456789"
```

### SMS on Power Failure (UPS)
```yaml
automation:
  - alias: "Power Failure Alert"
    trigger:
      platform: state
      entity_id: sensor.ups_status
      to: "on_battery"
    action:
      service: notify.sms_gateway
      data:
        message: "Power failure detected! UPS on battery."
        target: "+420123456789"
```

## 📡 REST API

### Swagger Documentation
Full API documentation: `http://your-ha-ip:5000/docs/`

### Main Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sms` | Send SMS |
| GET | `/sms` | Get all SMS |
| GET | `/sms/{id}` | Get specific SMS |
| DELETE | `/sms/{id}` | Delete SMS |
| GET | `/status/signal` | Signal strength |
| GET | `/status/network` | Network info |
| GET | `/status/reset` | Reset modem |

### API Example (Python)
```python
import requests
from requests.auth import HTTPBasicAuth

response = requests.post(
    'http://192.168.1.x:5000/sms',
    auth=HTTPBasicAuth('admin', 'password'),
    json={
        'text': 'Test message from Python',
        'number': '+420123456789'
    }
)
print(response.json())
```

## 🔴 Troubleshooting

### Modem Not Detected
```bash
# Check USB devices
ls -la /dev/ttyUSB*

# Check kernel messages
dmesg | grep ttyUSB

# Restart add-on after connecting modem
```

### SMS Not Sending
1. **Check signal**: Should be > 20%
2. **Verify credit**: SIM card must have credit
3. **PIN code**: Either correct or disabled
4. **Network**: Check registration status

### Code 69 Error (SMSC)
- Add-on automatically uses Location 1 fallback
- Works the same as REST API
- No SMSC configuration needed

### MQTT Not Working
1. Verify MQTT broker is running
2. Check credentials
3. Look for connection errors in log
4. Ensure topic prefix doesn't conflict

### Text Fields Not Synchronized
- Add-on uses `retain=True` for synchronization
- Wait 2 seconds after restart for sync
- Phone number persists, message clears

## 💡 Tips & Tricks

### Multiple Recipients
```json
{
  "number": "+420111111111,+420222222222",
  "text": "Broadcast message"
}
```

### Unicode Support (Special Characters)
```json
{
  "number": "+420123456789",
  "text": "Příliš žluťoučký kůň",
  "unicode": true
}
```

### Custom Notify Name
```yaml
notify:
  - name: Security_SMS
    platform: rest
    resource: http://192.168.1.x:5000/sms
    method: POST_JSON
    authentication: basic
    username: admin
    password: your_password
    target_param_name: number
    message_param_name: message
```

## 📝 Version History

See [CHANGELOG.md](./CHANGELOG.md) for complete version history and detailed changes.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/dima11235/ha-sms-gammu-gateway-addon/issues)
- **Swagger UI**: http://your-ha-ip:5000/docs/
- **Original Project**: [sms-gammu-gateway](https://github.com/pajikos/sms-gammu-gateway)
