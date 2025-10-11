#!/usr/bin/env python3
"""
SMS Gammu Gateway - Home Assistant Add-on
REST API SMS Gateway using python-gammu for USB GSM modems

Based on: https://github.com/pajikos/sms-gammu-gateway
Licensed under Apache License 2.0
"""

import os
import json
import logging
import yaml
from flask import Flask, request
from flask_httpauth import HTTPBasicAuth
from flask_restx import Api, Resource, fields, reqparse

from support import init_state_machine, retrieveAllSms, deleteSms, encodeSms, message_requires_unicode
from mqtt_publisher import MQTTPublisher
from gammu import GSMNetworks

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
mqtt_logger = logging.getLogger('mqtt_publisher')
mqtt_logger.setLevel(logging.INFO)

# Suppress Flask development server warning
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

def load_ha_config():
    """Load Home Assistant add-on configuration"""
    config_path = '/data/options.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    else:
        # Default values for testing outside HA
        return {
            'device_path': '/dev/ttyUSB0',
            'pin': '',
            'port': 5000,
            'ssl': False,
            'username': 'admin',
            'password': 'password',
            'mqtt_enabled': False,
            'mqtt_host': 'localhost',
            'mqtt_port': 1883,
            'mqtt_username': '',
            'mqtt_password': '',
            'mqtt_topic_prefix': 'homeassistant/sensor/sms_gateway',
            'sms_monitoring_enabled': True,
            'sms_check_interval': 60,
            'debug': False
        }

SECRET_DIRECTIVE = '!secret'
SECRET_FILES = (
    '/config/secrets.yaml',
    '/config/secrets.yml',
    '/data/secrets.yaml',
    '/data/secrets.yml',
)
_secrets_cache = None
_missing_secret_keys = set()


def _load_secrets():
    """Load secrets from known Home Assistant paths."""
    secrets = {}
    for path in SECRET_FILES:
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as secret_file:
                data = yaml.safe_load(secret_file) or {}
                if isinstance(data, dict):
                    # Later files can override earlier ones
                    secrets.update({str(key): value for key, value in data.items()})
                else:
                    logging.warning("Secrets file %s does not contain a mapping, skipping", path)
        except Exception as err:
            logging.warning("Failed to read secrets from %s: %s", path, err)
    return secrets


def _resolve_secret_directive(value):
    """Resolve !secret directive values to concrete secrets."""
    global _secrets_cache
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped.lower().startswith(SECRET_DIRECTIVE):
        return value

    parts = stripped.split(None, 1)
    if len(parts) != 2 or not parts[1].strip():
        logging.warning("Secret directive '%s' is missing a secret name", value)
        return ""

    secret_name = parts[1].strip()

    if _secrets_cache is None:
        _secrets_cache = _load_secrets()

    if secret_name not in _secrets_cache:
        if secret_name not in _missing_secret_keys:
            logging.warning("Secret '%s' not found in secrets files, using empty value", secret_name)
            _missing_secret_keys.add(secret_name)
        return ""

    secret_value = _secrets_cache[secret_name]
    # Convert non-string primitives to strings for consistency with config values
    if isinstance(secret_value, (int, float, bool)):
        return str(secret_value)
    if secret_value is None:
        logging.warning("Secret '%s' is defined but empty, using empty value", secret_name)
        return ""
    if not isinstance(secret_value, str):
        logging.warning("Secret '%s' has unsupported type %s, converting to string", secret_name, type(secret_value))
        return str(secret_value)
    return secret_value


def _resolve_secrets_in_structure(data):
    """Recursively resolve secrets in dicts/lists."""
    if isinstance(data, dict):
        return {key: _resolve_secrets_in_structure(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_resolve_secrets_in_structure(item) for item in data]
    if isinstance(data, str):
        return _resolve_secret_directive(data)
    return data

# Load configuration
config = load_ha_config()
config = _resolve_secrets_in_structure(config)
pin = config.get('pin') if config.get('pin') else None
ssl = config.get('ssl', False)
port = config.get('port', 5000)
username = config.get('username', 'admin')
password = config.get('password', 'password')
device_path = config.get('device_path', '/dev/ttyUSB0')
debug_enabled = config.get('debug', False)

if debug_enabled:
    logging.getLogger().setLevel(logging.DEBUG)
    mqtt_logger.setLevel(logging.DEBUG)
    logging.info("Debug logging enabled. Detailed output will be written to the add-on logs and /data/gammu-debug.log.")

# Initialize gammu state machine
machine = init_state_machine(pin, device_path, debug_enabled)

# Initialize MQTT publisher
mqtt_publisher = MQTTPublisher(config)
# Set gammu machine for MQTT SMS sending
mqtt_publisher.set_gammu_machine(machine)

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # Allow Cyrillic characters in JSON responses
app.config['RESTX_JSON'] = {'ensure_ascii': False}

# Check if running under Ingress
ingress_path = os.environ.get('INGRESS_PATH', '')

# Create simple HTML page for Ingress
@app.route('/')
def home():
    """Simple status page for Home Assistant Ingress"""
    from flask import Response, request
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>SMS Gammu Gateway</title>
        <meta charset="utf-8">
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                margin: 0;
                padding: 40px 20px;
                background: #f5f5f5;
                text-align: center;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background: white;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            }
            h1 {
                color: #333;
                margin-bottom: 20px;
                font-size: 2.2em;
            }
            .status {
                background: #e8f5e9;
                border: 2px solid #4caf50;
                padding: 20px;
                margin: 30px 0;
                border-radius: 10px;
                font-size: 1.2em;
            }
            .swagger-link {
                display: inline-block;
                padding: 15px 30px;
                background: #2196F3;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                margin: 20px 0;
                font-size: 1.1em;
                font-weight: bold;
            }
            .swagger-link:hover {
                background: #1976D2;
            }
            .info {
                background: #f0f8ff;
                border-left: 4px solid #2196F3;
                padding: 15px;
                margin: 20px 0;
                text-align: left;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📱 SMS Gammu Gateway</h1>
            
            <div class="status">
                <strong>✅ Gateway is running properly</strong><br>
                Version: 1.3.4
            </div>
            
            <a href="http://''' + request.host.split(':')[0] + ''':5000/docs/" 
               class="swagger-link" target="_blank">
                📋 Open Swagger API Documentation
            </a>
            
            <div class="info">
                <strong>REST API Endpoints:</strong><br>
                • GET /status/signal - Signal strength<br>
                • GET /status/network - Network information<br>
                • POST /sms - Send SMS (requires authentication)<br>
                • GET /sms - Get all SMS (requires authentication)<br>
                <br>
                <strong>Authentication in Swagger UI:</strong><br>
                1. Click the "Authorize" button 🔒 in the top right corner<br>
                2. Enter Username and Password from add-on configuration<br>
                3. Click "Authorize" - now you can test protected endpoints
            </div>
        </div>
    </body>
    </html>
    '''
    return Response(html, mimetype='text/html')

# Swagger UI Configuration  
# Put Swagger UI on /docs/ path for direct access via port 5000
api = Api(
    app, 
    version='1.3.4',
    title='SMS Gammu Gateway API',
    description='REST API for sending and receiving SMS messages via USB GSM modems (SIM800L, Huawei, etc.). Modern replacement for deprecated SMS notifications via GSM-modem integration.',
    doc='/docs/',  # Swagger UI on /docs/ path
    prefix='',
    authorizations={
        'basicAuth': {
            'type': 'basic',
            'in': 'header',
            'name': 'Authorization'
        }
    },
    security='basicAuth'
)

auth = HTTPBasicAuth()

@auth.verify_password
def verify(user, pwd):
    if not (user and pwd):
        return False
    return user == username and pwd == password

# API Models for Swagger documentation
sms_model = api.model('SMS', {
    'text': fields.String(required=True, description='SMS message text', example='Hello, how are you?'),
    'number': fields.String(required=True, description='Phone number (international format)', example='+420123456789'),
    'smsc': fields.String(required=False, description='SMS Center number (optional)', example='+420603052000'),
    'unicode': fields.Boolean(required=False, description='Force Unicode encoding (auto-enabled for non-ASCII text)', default=False)
})

sms_response = api.model('SMS Response', {
    'Date': fields.String(description='Date and time received', example='2025-01-19 14:30:00'),
    'Number': fields.String(description='Sender phone number', example='+420123456789'),
    'State': fields.String(description='SMS state', example='UnRead'),
    'Text': fields.String(description='SMS message text', example='Hello World!')
})

signal_response = api.model('Signal Quality', {
    'SignalStrength': fields.Integer(description='Signal strength in dBm', example=-75),
    'SignalPercent': fields.Integer(description='Signal strength percentage', example=65),
    'BitErrorRate': fields.Integer(description='Bit error rate', example=-1)
})

network_response = api.model('Network Info', {
    'NetworkName': fields.String(description='Network operator name', example='T-Mobile'),
    'State': fields.String(description='Network registration state', example='HomeNetwork'),
    'NetworkCode': fields.String(description='Network operator code', example='230 01'),
    'CID': fields.String(description='Cell ID', example='0A1B2C3D'),
    'LAC': fields.String(description='Location Area Code', example='1234')
})

send_response = api.model('Send Response', {
    'status': fields.Integer(description='HTTP status code', example=200),
    'message': fields.String(description='Response message', example='[1]')
})

reset_response = api.model('Reset Response', {
    'status': fields.Integer(description='HTTP status code', example=200),
    'message': fields.String(description='Reset message', example='Reset done')
})

# API Namespaces
ns_sms = api.namespace('sms', description='SMS operations (requires authentication)')
ns_status = api.namespace('status', description='Device status and information (public)')

@ns_sms.route('')
@ns_sms.doc('sms_operations')
class SmsCollection(Resource):
    @ns_sms.doc('get_all_sms')
    @ns_sms.marshal_list_with(sms_response)
    @ns_sms.doc(security='basicAuth')
    @auth.login_required
    def get(self):
        """Get all SMS messages from SIM/device memory"""
        allSms = mqtt_publisher.track_gammu_operation("retrieveAllSms", retrieveAllSms, machine)
        list(map(lambda sms: sms.pop("Locations", None), allSms))
        return allSms

    @ns_sms.doc('send_sms')
    @ns_sms.expect(sms_model)
    @ns_sms.marshal_with(send_response)
    @ns_sms.doc(security='basicAuth')
    @auth.login_required
    def post(self):
        """Send SMS message(s)"""
        parser = reqparse.RequestParser()
        parser.add_argument('text', required=False, help='SMS message text')
        parser.add_argument('message', required=False, help='SMS message text (alias for text)')
        parser.add_argument('number', required=False, help='Phone number(s), comma separated')
        parser.add_argument('target', required=False, help='Phone number (alias for number)')
        parser.add_argument('smsc', required=False, help='SMS Center number (optional)')
        parser.add_argument('unicode', required=False, help='Use Unicode encoding (true/false, auto-detected if omitted)')
        
        args = parser.parse_args()
        
        # Support both 'text' and 'message' parameters
        sms_text = args.get('text') or args.get('message')
        if not sms_text:
            return {"status": 400, "message": "Missing required field: text or message"}, 400
        
        # Support both 'number' and 'target' parameters
        sms_number = args.get('number') or args.get('target')
        if not sms_number:
            return {"status": 400, "message": "Missing required field: number or target"}, 400

        unicode_arg = args.get('unicode')
        unicode_requested = None
        if unicode_arg is not None:
            unicode_requested = str(unicode_arg).lower() in ('1', 'true', 'yes', 'on')
        
        unicode_enabled = bool(unicode_requested) if unicode_requested is not None else False
        if message_requires_unicode(sms_text) and not unicode_enabled:
            unicode_enabled = True
            logging.info("Detected non-ASCII characters in SMS text, enabling Unicode encoding automatically")
        
        smsinfo = {
            "Class": -1,
            "Unicode": unicode_enabled,
            "Entries": [
                {
                    "ID": "ConcatenatedTextLong",
                    "Buffer": sms_text,
                }
            ],
        }
        if unicode_enabled:
            smsinfo["Coding"] = "Unicode"
        
        messages = []
        for number in sms_number.split(','):
            for message in encodeSms(smsinfo):
                message["SMSC"] = {'Number': args.get("smsc")} if args.get("smsc") else {'Location': 1}
                message["Number"] = number.strip()
                messages.append(message)
        result = [mqtt_publisher.track_gammu_operation("SendSMS", machine.SendSMS, message) for message in messages]
        return {"status": 200, "message": str(result)}, 200

@ns_sms.route('/<int:id>')
@ns_sms.doc('sms_by_id')
class SmsItem(Resource):
    @ns_sms.doc('get_sms_by_id')
    @ns_sms.marshal_with(sms_response)
    @ns_sms.doc(security='basicAuth')
    @auth.login_required
    def get(self, id):
        """Get specific SMS by ID"""
        allSms = mqtt_publisher.track_gammu_operation("retrieveAllSms", retrieveAllSms, machine)
        if id < 0 or id >= len(allSms):
            api.abort(404, f"SMS with id '{id}' not found")
        sms = allSms[id]
        sms.pop("Locations", None)
        return sms

    @ns_sms.doc('delete_sms_by_id')
    @ns_sms.doc(security='basicAuth')
    @auth.login_required
    def delete(self, id):
        """Delete SMS by ID"""
        allSms = mqtt_publisher.track_gammu_operation("retrieveAllSms", retrieveAllSms, machine)
        if id < 0 or id >= len(allSms):
            api.abort(404, f"SMS with id '{id}' not found")
        mqtt_publisher.track_gammu_operation("deleteSms", deleteSms, machine, allSms[id])
        return '', 204

@ns_sms.route('/getsms')
@ns_sms.doc('get_and_delete_first_sms')
class GetSms(Resource):
    @ns_sms.doc('pop_first_sms')
    @ns_sms.marshal_with(sms_response)
    @ns_sms.doc(security='basicAuth')
    @auth.login_required
    def get(self):
        """Get first SMS and delete it from memory"""
        allSms = mqtt_publisher.track_gammu_operation("retrieveAllSms", retrieveAllSms, machine)
        sms = {"Date": "", "Number": "", "State": "", "Text": ""}
        if len(allSms) > 0:
            sms = allSms[0]
            mqtt_publisher.track_gammu_operation("deleteSms", deleteSms, machine, sms)
            sms.pop("Locations", None)
            # Publish to MQTT if enabled and SMS has content
            if sms.get("Text"):
                mqtt_publisher.publish_sms_received(sms)
        return sms

@ns_status.route('/signal')
@ns_status.doc('get_signal_quality')
class Signal(Resource):
    @ns_status.doc('signal_strength')
    @ns_status.marshal_with(signal_response)
    def get(self):
        """Get GSM signal strength and quality"""
        signal_data = mqtt_publisher.track_gammu_operation("GetSignalQuality", machine.GetSignalQuality)
        # Publish to MQTT if enabled
        mqtt_publisher.publish_signal_strength(signal_data)
        return signal_data

@ns_status.route('/network')
@ns_status.doc('get_network_info')
class Network(Resource):
    @ns_status.doc('network_information')
    @ns_status.marshal_with(network_response)
    def get(self):
        """Get network operator and registration information"""
        network = mqtt_publisher.track_gammu_operation("GetNetworkInfo", machine.GetNetworkInfo)
        network["NetworkName"] = GSMNetworks.get(network.get("NetworkCode", ""), 'Unknown')
        # Publish to MQTT if enabled
        mqtt_publisher.publish_network_info(network)
        return network

@ns_status.route('/reset')
@ns_status.doc('reset_modem')
class Reset(Resource):
    @ns_status.doc('modem_reset')
    @ns_status.marshal_with(reset_response)
    def get(self):
        """Reset GSM modem (useful for stuck connections)"""
        mqtt_publisher.track_gammu_operation("Reset", machine.Reset, False)
        return {"status": 200, "message": "Reset done"}, 200

if __name__ == '__main__':
    print(f"🚀 SMS Gammu Gateway v1.3.4 started successfully!")
    print(f"📱 Device: {device_path}")
    print(f"🌐 API available on port {port}")
    print(f"🏠 Web UI: http://localhost:{port}/")
    print(f"🔒 SSL: {'Enabled' if ssl else 'Disabled'}")
    
    # MQTT info
    if config.get('mqtt_enabled', False):
        print(f"📡 MQTT: Enabled -> {config.get('mqtt_host')}:{config.get('mqtt_port')}")
        
        # Wait a moment for MQTT connection, then publish initial states
        import time
        time.sleep(2)
        mqtt_publisher.publish_initial_states_with_machine(machine)
        
        # Start periodic MQTT publishing
        mqtt_publisher.publish_status_periodic(machine, interval=300)  # 5 minutes
        
        # Start SMS monitoring if enabled
        if config.get('sms_monitoring_enabled', True):
            check_interval = config.get('sms_check_interval', 60)
            mqtt_publisher.start_sms_monitoring(machine, check_interval=check_interval)
            print(f"📱 SMS Monitoring: Enabled (check every {check_interval}s)")
        else:
            print(f"📱 SMS Monitoring: Disabled")
    else:
        print(f"📡 MQTT: Disabled")
    
    print(f"✅ Ready to send/receive SMS messages")
    
    try:
        if ssl:
            app.run(port=port, host="0.0.0.0", ssl_context=('/ssl/cert.pem', '/ssl/key.pem'),
                    debug=False, use_reloader=False)
        else:
            app.run(port=port, host="0.0.0.0", debug=False, use_reloader=False)
    finally:
        # Cleanup MQTT connection
        mqtt_publisher.disconnect()

