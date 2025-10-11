"""
MQTT Publisher for SMS Gammu Gateway
Publishes SMS and device status to MQTT broker with Home Assistant auto-discovery
"""

import json
import time
import logging
import threading
from typing import Optional, Dict, Any
import paho.mqtt.client as mqtt
from support import encodeSms, message_requires_unicode

logger = logging.getLogger(__name__)

class DeviceConnectivityTracker:
    """Tracks USB GSM device connectivity status based on gammu communication"""
    
    def __init__(self, offline_timeout_seconds=600):  # 10 minutes default
        self.last_success_time = None
        self.consecutive_failures = 0
        self.last_error = None
        self.offline_timeout = offline_timeout_seconds
        self.total_operations = 0
        self.successful_operations = 0
        
    def record_success(self):
        """Record successful gammu operation"""
        self.last_success_time = time.time()
        self.consecutive_failures = 0
        self.last_error = None
        self.total_operations += 1
        self.successful_operations += 1
        
    def record_failure(self, error_message=None):
        """Record failed gammu operation"""
        self.consecutive_failures += 1
        self.last_error = str(error_message) if error_message else "Communication failed"
        self.total_operations += 1
        
    def get_status(self):
        """Get current device connectivity status"""
        if self.last_success_time is None:
            return "unknown"
            
        time_since_last_success = time.time() - self.last_success_time
        if time_since_last_success > self.offline_timeout:
            return "offline"
        else:
            return "online"
            
    def get_status_data(self):
        """Get detailed status information"""
        status = self.get_status()
        
        data = {
            "status": status,
            "consecutive_failures": self.consecutive_failures,
            "total_operations": self.total_operations,
            "successful_operations": self.successful_operations,
            "last_error": self.last_error
        }
        
        if self.last_success_time:
            data["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.last_success_time))
            data["seconds_since_last_success"] = int(time.time() - self.last_success_time)
        else:
            data["last_seen"] = None
            data["seconds_since_last_success"] = None
            
        return data

class MQTTPublisher:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.topic_prefix = config.get('mqtt_topic_prefix', 'homeassistant/sensor/sms_gateway')
        self.gammu_machine = None  # Will be set externally
        self.current_phone_number = ""  # Current phone number from text input
        self.current_message_text = ""  # Current message text from text input
        self.device_tracker = DeviceConnectivityTracker()  # USB device connectivity tracking
        
        if config.get('mqtt_enabled', False):
            self._setup_client()
    
    def set_gammu_machine(self, machine):
        """Set gammu machine for SMS sending"""
        self.gammu_machine = machine
        logger.info("Gammu machine set for MQTT SMS sending")
    
    def _setup_client(self):
        """Setup MQTT client with configuration"""
        try:
            self.client = mqtt.Client()
            
            # Set credentials if provided
            username = self.config.get('mqtt_username')
            password = self.config.get('mqtt_password')
            if username:
                self.client.username_pw_set(username, password)
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_publish = self._on_publish
            self.client.on_message = self._on_message
            
            # Connect to broker
            host = self.config.get('mqtt_host', 'core-mosquitto')
            port = self.config.get('mqtt_port', 1883)
            
            logger.info(f"Connecting to MQTT broker: {host}:{port}")
            self.client.connect(host, port, 60)
            self.client.loop_start()
            
        except Exception as e:
            logger.error(f"Failed to setup MQTT client: {e}")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection"""
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker")
            self._publish_discovery_configs()
            # Subscribe to SMS send command topic
            send_topic = f"{self.topic_prefix}/send"
            client.subscribe(send_topic)
            logger.info(f"Subscribed to SMS send topic: {send_topic}")
            
            # Subscribe to SMS button topic
            button_topic = f"{self.topic_prefix}/send_button"
            client.subscribe(button_topic)
            logger.info(f"Subscribed to SMS button topic: {button_topic}")
            
            # Subscribe to text input topics
            phone_topic = f"{self.topic_prefix}/phone_number/set"
            message_topic = f"{self.topic_prefix}/message_text/set"
            phone_state_topic = f"{self.topic_prefix}/phone_number/state"
            message_state_topic = f"{self.topic_prefix}/message_text/state"
            
            client.subscribe(phone_topic)
            client.subscribe(message_topic)
            client.subscribe(phone_state_topic)  # Subscribe to state topics too
            client.subscribe(message_state_topic)
            logger.info(f"Subscribed to text input topics: {phone_topic}, {message_topic}, {phone_state_topic}, {message_state_topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker: {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection"""
        self.connected = False
        logger.warning("Disconnected from MQTT broker")
    
    def _on_publish(self, client, userdata, mid):
        """Callback for published messages"""
        pass
    
    def _on_message(self, client, userdata, msg):
        """Callback for received MQTT messages"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            logger.info(f"Received MQTT message on topic {topic}: {payload}")
            
            # Check message topic and handle accordingly
            send_topic = f"{self.topic_prefix}/send"
            button_topic = f"{self.topic_prefix}/send_button"
            phone_topic = f"{self.topic_prefix}/phone_number/set"
            message_topic = f"{self.topic_prefix}/message_text/set"
            phone_state_topic = f"{self.topic_prefix}/phone_number/state"
            message_state_topic = f"{self.topic_prefix}/message_text/state"
            
            if topic == send_topic:
                self._handle_sms_send_command(payload)
            elif topic == button_topic and payload == "PRESS":
                # Button pressed - send SMS using current text inputs
                self._handle_button_sms_send()
            elif topic == phone_topic:
                # Phone number updated via command topic
                self.current_phone_number = payload
                self._publish_phone_state(payload)
                logger.info(f"Phone number updated via command: {payload}")
            elif topic == message_topic:
                # Message text updated via command topic
                self.current_message_text = payload
                self._publish_message_state(payload)
                logger.info(f"Message text updated via command: {payload}")
            elif topic == phone_state_topic:
                # Phone number state received (sync with HA)
                self.current_phone_number = payload
                logger.info(f"Phone number synced from HA state: {payload}")
            elif topic == message_state_topic:
                # Message text state received (sync with HA)
                self.current_message_text = payload
                logger.info(f"Message text synced from HA state: {payload}")
                
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def _determine_unicode_mode(self, text, explicit_flag=None):
        """Decide whether message should be sent using Unicode encoding."""
        text_requires_unicode = message_requires_unicode(text)

        if explicit_flag is None:
            if text_requires_unicode:
                logger.info("Detected non-ASCII characters in MQTT SMS payload, enabling Unicode encoding automatically")
            return text_requires_unicode

        if isinstance(explicit_flag, bool):
            user_choice = explicit_flag
        elif isinstance(explicit_flag, (int, float)):
            user_choice = bool(explicit_flag)
        else:
            user_choice = str(explicit_flag).lower() in ('1', 'true', 'yes', 'on')

        if text_requires_unicode and not user_choice:
            logger.info("Detected non-ASCII characters in MQTT SMS payload, overriding unicode flag to True")
            return True

        return user_choice
    
    def _handle_sms_send_command(self, payload):
        """Handle SMS send command from MQTT"""
        try:
            # Parse JSON payload
            data = json.loads(payload)
            number = data.get('number')
            text = data.get('text')
            unicode_flag = data.get('unicode')
            unicode_mode = self._determine_unicode_mode(text, unicode_flag)
            
            if not number or not text:
                logger.error("SMS send command missing required fields: number or text")
                return
            
            logger.info(f"Processing SMS send command: {number} -> {text} (unicode: {unicode_mode})")
            
            # Send SMS via gammu machine (will be set externally)
            if hasattr(self, 'gammu_machine') and self.gammu_machine:
                self._send_sms_via_gammu(number, text, unicode_mode)
            else:
                logger.error("Gammu machine not available for SMS sending")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in SMS send command: {e}")
        except Exception as e:
            logger.error(f"Error handling SMS send command: {e}")
    
    def _send_sms_via_gammu(self, number, text, unicode_mode=False):
        """Send SMS using gammu machine"""
        try:
            unicode_enabled = self._determine_unicode_mode(text, unicode_mode)
            # Prepare SMS info
            smsinfo = {
                "Class": -1,
                "Unicode": unicode_enabled,
                "Entries": [
                    {
                        "ID": "ConcatenatedTextLong",
                        "Buffer": text,
                    }
                ],
            }
            if unicode_enabled:
                smsinfo["Coding"] = "Unicode"
            
            # Encode and send SMS
            messages = encodeSms(smsinfo)
            for message in messages:
                # Use same SMSC logic as REST API
                config_smsc = self.config.get('smsc_number', '').strip()
                if config_smsc:
                    message["SMSC"] = {'Number': config_smsc}
                    logger.info(f"Using configured SMSC: {config_smsc}")
                else:
                    # Use Location 1 (same as REST API when no SMSC provided)
                    message["SMSC"] = {'Location': 1}
                    logger.info("Using SMSC from Location 1 (same as REST API)")
                
                message["Number"] = number
                result = self.track_gammu_operation("SendSMS", self.gammu_machine.SendSMS, message)
                logger.info(f"SMS sent successfully: {result}")
                
            # Publish confirmation
            if self.connected:
                status_topic = f"{self.topic_prefix}/send_status"
                status_data = {
                    "status": "success",
                    "number": number,
                    "text": text,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                self.client.publish(status_topic, json.dumps(status_data, ensure_ascii=False), retain=False)
                
        except Exception as e:
            error_msg = str(e)
            # Try to extract useful error message from gammu error
            if "Code': 27" in error_msg:
                user_error = "SMS sending failed - check SIM card, network signal or device connection"
            elif "Code': 38" in error_msg:
                user_error = "Network registration failed - check SIM card and signal"
            elif "Code': 69" in error_msg:
                user_error = "SMSC number not found - configure SMS center number in SIM settings"
            else:
                user_error = f"SMS sending error: {error_msg}"
            
            logger.error(f"Failed to send SMS via gammu: {error_msg}")
            # Publish error status with user-friendly message
            if self.connected:
                status_topic = f"{self.topic_prefix}/send_status"
                status_data = {
                    "status": "error",
                    "error": user_error,
                    "number": number,
                    "text": text,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                self.client.publish(status_topic, json.dumps(status_data, ensure_ascii=False), retain=False)
    
    def _handle_button_sms_send(self):
        """Handle SMS send when button is pressed using current text inputs"""
        # Log current state for debugging
        logger.info(f"Button pressed - current state: phone='{self.current_phone_number}', message='{self.current_message_text}'")
        
        if not self.current_phone_number.strip() or not self.current_message_text.strip():
            # If fields are empty, show instruction
            if self.connected:
                status_topic = f"{self.topic_prefix}/send_status"
                status_data = {
                    "status": "missing_fields", 
                    "message": f"Please fill in phone number and message text first. Current: phone='{self.current_phone_number}', message='{self.current_message_text}'",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                self.client.publish(status_topic, json.dumps(status_data, ensure_ascii=False), retain=False)
            logger.warning(f"Button pressed but fields empty: phone='{self.current_phone_number}', message='{self.current_message_text}'")
            return
        
        # Send SMS using current values
        unicode_mode = self._determine_unicode_mode(self.current_message_text, None)
        logger.info(f"Button SMS send: {self.current_phone_number} -> {self.current_message_text} (unicode: {unicode_mode})")
        if hasattr(self, 'gammu_machine') and self.gammu_machine:
            self._send_sms_via_gammu(self.current_phone_number, self.current_message_text, unicode_mode=unicode_mode)
            # Always clear fields after send attempt (success or failure)
            self._clear_text_fields()
        else:
            logger.error("Gammu machine not available for SMS sending")
            # Clear fields even if gammu not available
            self._clear_text_fields()
    
    def _clear_text_fields(self):
        """Clear only message field after sending, keep phone number for convenience"""
        # Clear only message text, keep phone number
        self.current_message_text = ""
        
        # Try to clear only message in UI if connected
        if self.connected and self.client:
            try:
                message_state_topic = f"{self.topic_prefix}/message_text/state"
                # Clear only message field with retain=True
                self.client.publish(message_state_topic, "", retain=True)
                logger.info("🧹 Cleared message text field (keeping phone number for convenience)")
            except Exception as e:
                logger.warning(f"Could not clear message field in UI: {e}")
        else:
            logger.info("🧹 Cleared message text field (internal state only)")
    
    def _publish_phone_state(self, value):
        """Publish phone number state"""
        if self.connected:
            state_topic = f"{self.topic_prefix}/phone_number/state"
            self.client.publish(state_topic, value, retain=False)
    
    def _publish_message_state(self, value):
        """Publish message text state"""
        if self.connected:
            state_topic = f"{self.topic_prefix}/message_text/state"
            self.client.publish(state_topic, value, retain=False)
    
    def _publish_empty_text_fields(self):
        """Initialize message field to empty on startup, let phone number persist"""
        if self.connected:
            message_state_topic = f"{self.topic_prefix}/message_text/state"
            
            # Force only message to empty state with retain=True
            self.client.publish(message_state_topic, "", retain=True)
            
            # Clear only message internally, phone number will sync from HA
            self.current_message_text = ""
            
            logger.info("🔄 Initialized message field to empty (phone number persists from last session)")
    
    def _publish_discovery_configs(self):
        """Publish Home Assistant auto-discovery configurations"""
        if not self.connected:
            return
            
        # Signal strength sensor
        signal_config = {
            "name": "GSM Signal Strength",
            "unique_id": "sms_gateway_signal",
            "state_topic": f"{self.topic_prefix}/signal/state",
            "value_template": "{{ value_json.SignalPercent }}",
            "unit_of_measurement": "%",
            "icon": "mdi:signal-cellular-3",
            "device": {
                "identifiers": ["sms_gateway"],
                "name": "SMS Gateway",
                "model": "GSM Modem",
                "manufacturer": "Gammu Gateway"
            }
        }
        
        # Network info sensor
        network_config = {
            "name": "GSM Network",
            "unique_id": "sms_gateway_network",
            "state_topic": f"{self.topic_prefix}/network/state",
            "value_template": "{{ value_json.NetworkName }}",
            "icon": "mdi:network",
            "device": {
                "identifiers": ["sms_gateway"],
                "name": "SMS Gateway",
                "model": "GSM Modem", 
                "manufacturer": "Gammu Gateway"
            }
        }
        
        # Last SMS sensor
        sms_config = {
            "name": "Last SMS Received",
            "unique_id": "sms_gateway_last_sms",
            "state_topic": f"{self.topic_prefix}/sms/state",
            "value_template": "{{ value_json.Text }}",
            "json_attributes_topic": f"{self.topic_prefix}/sms/state",
            "icon": "mdi:message-text",
            "device": {
                "identifiers": ["sms_gateway"],
                "name": "SMS Gateway",
                "model": "GSM Modem",
                "manufacturer": "Gammu Gateway"
            }
        }
        
        # SMS send status sensor
        send_status_config = {
            "name": "SMS Send Status",
            "unique_id": "sms_gateway_send_status",
            "state_topic": f"{self.topic_prefix}/send_status",
            "value_template": "{{ value_json.status }}",
            "json_attributes_topic": f"{self.topic_prefix}/send_status",
            "icon": "mdi:send",
            "device": {
                "identifiers": ["sms_gateway"],
                "name": "SMS Gateway",
                "model": "GSM Modem",
                "manufacturer": "Gammu Gateway"
            }
        }
        
        # SMS send button
        button_config = {
            "name": "Send SMS",
            "unique_id": "sms_gateway_send_button",
            "command_topic": f"{self.topic_prefix}/send_button",
            "payload_press": "PRESS",
            "icon": "mdi:message-plus",
            "device": {
                "identifiers": ["sms_gateway"],
                "name": "SMS Gateway",
                "model": "GSM Modem",
                "manufacturer": "Gammu Gateway"
            }
        }
        
        # Phone number input text
        phone_text_config = {
            "name": "Phone Number",
            "unique_id": "sms_gateway_phone_number",
            "command_topic": f"{self.topic_prefix}/phone_number/set",
            "state_topic": f"{self.topic_prefix}/phone_number/state",
            "icon": "mdi:phone",
            "mode": "text",
            "pattern": r"^\+?[\d\s\-\(\)]+$",
            "device": {
                "identifiers": ["sms_gateway"],
                "name": "SMS Gateway",
                "model": "GSM Modem",
                "manufacturer": "Gammu Gateway"
            }
        }
        
        # Message input text
        message_text_config = {
            "name": "Message Text",
            "unique_id": "sms_gateway_message_text",
            "command_topic": f"{self.topic_prefix}/message_text/set",
            "state_topic": f"{self.topic_prefix}/message_text/state",
            "icon": "mdi:message-text",
            "mode": "text",
            "max": 160,
            "device": {
                "identifiers": ["sms_gateway"],
                "name": "SMS Gateway",
                "model": "GSM Modem",
                "manufacturer": "Gammu Gateway"
            }
        }
        
        # Modem Status sensor
        device_status_config = {
            "name": "Modem Status",
            "unique_id": "sms_gateway_modem_status",
            "state_topic": f"{self.topic_prefix}/device_status/state",
            "value_template": "{{ value_json.status }}",
            "json_attributes_topic": f"{self.topic_prefix}/device_status/state",
            "icon": "mdi:connection",
            "device": {
                "identifiers": ["sms_gateway"],
                "name": "SMS Gateway",
                "model": "GSM Modem",
                "manufacturer": "Gammu Gateway"
            }
        }
        
        # Publish discovery configs
        discoveries = [
            ("homeassistant/sensor/sms_gateway_signal/config", signal_config),
            ("homeassistant/sensor/sms_gateway_network/config", network_config),
            ("homeassistant/sensor/sms_gateway_last_sms/config", sms_config),
            ("homeassistant/sensor/sms_gateway_send_status/config", send_status_config),
            ("homeassistant/sensor/sms_gateway_modem_status/config", device_status_config),
            ("homeassistant/button/sms_gateway_send_button/config", button_config),
            ("homeassistant/text/sms_gateway_phone_number/config", phone_text_config),
            ("homeassistant/text/sms_gateway_message_text/config", message_text_config)
        ]
        
        for topic, config in discoveries:
            self.client.publish(topic, json.dumps(config, ensure_ascii=False), retain=True)
        
        logger.info("Published MQTT discovery configurations including SMS send button")
        
        # Publish initial states immediately after discovery
        self._publish_initial_states()
        
        # Wait a moment for HA to process discovery, then force empty text fields
        import time
        time.sleep(1)
        self._publish_empty_text_fields()
        
        # Give HA another moment to send retained state messages back to us
        time.sleep(0.5)
    
    def publish_signal_strength(self, signal_data: Dict[str, Any]):
        """Publish signal strength data"""
        if not self.connected:
            return
            
        topic = f"{self.topic_prefix}/signal/state"
        self.client.publish(topic, json.dumps(signal_data, ensure_ascii=False), retain=True)
        logger.info(f"📡 Published signal strength to MQTT: {signal_data.get('SignalPercent', 'N/A')}%")
    
    def publish_network_info(self, network_data: Dict[str, Any]):
        """Publish network information"""
        if not self.connected:
            return
            
        topic = f"{self.topic_prefix}/network/state"
        self.client.publish(topic, json.dumps(network_data, ensure_ascii=False), retain=True)
        logger.info(f"📡 Published network info to MQTT: {network_data.get('NetworkName', 'Unknown')}")
    
    def publish_sms_received(self, sms_data: Dict[str, Any]):
        """Publish received SMS data"""
        if not self.connected:
            return
            
        # Add timestamp
        sms_data['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
        
        topic = f"{self.topic_prefix}/sms/state"
        self.client.publish(topic, json.dumps(sms_data, ensure_ascii=False))
        
        logger.info(f"📡 Published SMS to MQTT: {sms_data.get('Number', 'Unknown')} -> {sms_data.get('Text', '')}")
    
    def publish_device_status(self):
        """Publish USB device connectivity status"""
        if not self.connected:
            return
            
        status_data = self.device_tracker.get_status_data()
        
        topic = f"{self.topic_prefix}/device_status/state"
        self.client.publish(topic, json.dumps(status_data, ensure_ascii=False), retain=True)
        
        # Log status changes
        status = status_data.get('status')
        if hasattr(self, '_last_device_status') and self._last_device_status != status:
            if status == 'online':
                logger.info(f"📶 Modem: ONLINE (after {status_data.get('consecutive_failures', 0)} failures)")
            elif status == 'offline':
                logger.warning(f"❌ Modem: OFFLINE (no response for {status_data.get('seconds_since_last_success', 0)}s)")
            elif status == 'unknown':
                logger.info("❓ Modem: UNKNOWN (no communication attempts yet)")
        
        self._last_device_status = status
        
    def track_gammu_operation(self, operation_name, gammu_function, *args, **kwargs):
        """Execute gammu operation with connectivity tracking"""
        try:
            result = gammu_function(*args, **kwargs)
            self.device_tracker.record_success()
            self.publish_device_status()
            logger.debug(f"✅ Gammu operation '{operation_name}' succeeded")
            return result
        except Exception as e:
            self.device_tracker.record_failure(f"{operation_name}: {str(e)}")
            self.publish_device_status()
            logger.warning(f"❌ Gammu operation '{operation_name}' failed: {e}")
            raise
    
    def _publish_initial_states(self):
        """Publish initial sensor states on startup"""
        # This will be called from the main thread with access to gammu machine
        pass
    
    def publish_initial_states_with_machine(self, gammu_machine):
        """Publish initial states with gammu machine access"""
        if not self.connected:
            logger.info("📡 MQTT not connected, skipping initial state publish")
            return
            
        try:
            from gammu import GSMNetworks
            
            # Publish initial signal strength with connectivity tracking
            signal = self.track_gammu_operation("GetSignalQuality", gammu_machine.GetSignalQuality)
            self.publish_signal_strength(signal)
            
            # Publish initial network info with connectivity tracking
            network = self.track_gammu_operation("GetNetworkInfo", gammu_machine.GetNetworkInfo)
            network["NetworkName"] = GSMNetworks.get(network.get("NetworkCode", ""), 'Unknown')
            self.publish_network_info(network)
            
            # Publish empty SMS state initially
            empty_sms = {"Date": "", "Number": "", "State": "", "Text": "", "timestamp": ""}
            topic = f"{self.topic_prefix}/sms/state"
            self.client.publish(topic, json.dumps(empty_sms, ensure_ascii=False), retain=True)
            
            logger.info("📡 Published initial states to MQTT")
            
        except Exception as e:
            logger.error(f"Error publishing initial states: {e}")
    
    def start_sms_monitoring(self, gammu_machine, check_interval=30):
        """Start SMS monitoring in background thread"""
        if not self.connected:
            return
            
        def _sms_monitor_loop():
            logger.info(f"📱 Started SMS monitoring (check every {check_interval}s)")
            last_sms_count = 0
            
            while self.connected:
                try:
                    from support import retrieveAllSms, deleteSms
                    
                    # Check for new SMS with connectivity tracking
                    all_sms = self.track_gammu_operation("retrieveAllSms", retrieveAllSms, gammu_machine)
                    previous_count = last_sms_count
                    current_count = len(all_sms)
                    
                    # If there are new SMS since last check
                    if current_count > previous_count:
                        logger.info(f"📱 Detected {current_count - previous_count} new SMS messages")
                        
                        # Process new SMS (from the end, newest first)
                        for i in range(previous_count, current_count):
                            if i < len(all_sms):
                                sms_record = all_sms[i]
                                sms = sms_record.copy()
                                sms.pop("Locations", None)
                                
                                # Publish to MQTT
                                self.publish_sms_received(sms)
                                
                                # Delete SMS from SIM after it has been processed
                                try:
                                    self.track_gammu_operation("deleteSms", deleteSms, gammu_machine, sms_record)
                                    logger.debug(f"Deleted SMS from {sms.get('Number', '')} after publishing to MQTT")
                                except Exception as delete_error:
                                    logger.warning(f"Could not delete SMS after publishing: {delete_error}")
                        last_sms_count = previous_count
                    else:
                        last_sms_count = current_count
                    
                except Exception as e:
                    logger.error(f"Error monitoring SMS: {e}")
                
                time.sleep(check_interval)
        
        # Only start if both MQTT and SMS monitoring are enabled  
        if (self.config.get('mqtt_enabled', False) and 
            self.config.get('sms_monitoring_enabled', True)):
            thread = threading.Thread(target=_sms_monitor_loop, daemon=True)
            thread.start()
    
    def publish_status_periodic(self, gammu_machine, interval=60):
        """Publish status data periodically in background thread"""
        if not self.connected:
            return
            
        def _publish_loop():
            while self.connected:
                try:
                    # Publish signal strength with connectivity tracking
                    signal = self.track_gammu_operation("GetSignalQuality", gammu_machine.GetSignalQuality)
                    self.publish_signal_strength(signal)
                    
                    # Publish network info with connectivity tracking
                    from gammu import GSMNetworks
                    network = self.track_gammu_operation("GetNetworkInfo", gammu_machine.GetNetworkInfo)
                    network["NetworkName"] = GSMNetworks.get(network.get("NetworkCode", ""), 'Unknown')
                    self.publish_network_info(network)
                    
                except Exception as e:
                    logger.error(f"Error publishing periodic status: {e}")
                
                time.sleep(interval)
        
        if self.config.get('mqtt_enabled', False):
            thread = threading.Thread(target=_publish_loop, daemon=True)
            thread.start()
            logger.info(f"Started MQTT periodic publishing (interval: {interval}s)")
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.client and self.connected:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Disconnected from MQTT broker")


