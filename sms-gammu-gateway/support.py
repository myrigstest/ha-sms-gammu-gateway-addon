"""
SMS Gammu Gateway - Support functions
Gammu integration functions for SMS operations and state machine management

Based on: https://github.com/pajikos/sms-gammu-gateway
Licensed under Apache License 2.0
"""

import sys
import os
import gammu

GAMMU_DEBUG_LOG = '/data/gammu-debug.log'


def init_state_machine(pin, device_path='/dev/ttyUSB0', debug=False):
    """Initialize gammu state machine with HA add-on config"""
    sm = gammu.StateMachine()

    # Create gammu config dynamically
    config_lines = [
        "[gammu]",
        f"device = {device_path}",
        "connection = at",
    ]

    if debug:
        config_lines.extend([
            f"logfile = {GAMMU_DEBUG_LOG}",
            "logformat = textalldate",
        ])

    config_content = "\n".join(config_lines) + "\n"
    
    # Write config to temporary file
    config_file = '/tmp/gammu.config'
    with open(config_file, 'w') as f:
        f.write(config_content)
    
    sm.ReadConfig(Filename=config_file)

    if debug:
        try:
            sm.SetDebugFile(GAMMU_DEBUG_LOG)
            log_level = getattr(gammu, 'LOG_DEBUG', None)
            if log_level is not None:
                sm.SetDebugLevel(log_level)
        except Exception as debug_error:
            print(f"Warning: Could not enable Gammu debug logging: {debug_error}")
    
    try:
        sm.Init()
        print(f"Successfully initialized gammu with device: {device_path}")
        
        # Try to check security status
        try:
            security_status = sm.GetSecurityStatus()
            print(f"SIM security status: {security_status}")
            
            if security_status == 'PIN':
                if pin is None or pin == '':
                    print("PIN is required but not provided.")
                    sys.exit(1)
                else:
                    sm.EnterSecurityCode('PIN', pin)
                    print("PIN entered successfully")
                    
        except Exception as e:
            print(f"Warning: Could not check SIM security status: {e}")
            
    except gammu.ERR_NOSIM:
        print("Warning: SIM card not accessible, but device is connected")
    except Exception as e:
        print(f"Error initializing device: {e}")
        print("Available devices:")
        import os
        try:
            devices = [d for d in os.listdir('/dev/') if d.startswith('tty')]
            for device in sorted(devices):
                print(f"  /dev/{device}")
        except:
            pass
        raise
        
    return sm


def retrieveAllSms(machine):
    """Retrieve all SMS messages from SIM/device memory"""
    try:
        status = machine.GetSMSStatus()
        allMultiPartSmsCount = status['SIMUsed'] + status['PhoneUsed'] + status['TemplatesUsed']

        allMultiPartSms = []
        start = True

        while len(allMultiPartSms) < allMultiPartSmsCount:
            if start:
                currentMultiPartSms = machine.GetNextSMS(Start=True, Folder=0)
                start = False
            else:
                currentMultiPartSms = machine.GetNextSMS(Location=currentMultiPartSms[0]['Location'], Folder=0)
            allMultiPartSms.append(currentMultiPartSms)

        allSms = gammu.LinkSMS(allMultiPartSms)

        results = []
        for sms in allSms:
            smsPart = sms[0]

            result = {
                "Date": str(smsPart['DateTime']),
                "Number": smsPart['Number'],
                "State": smsPart['State'],
                "Locations": [smsPart['Location'] for smsPart in sms],
            }

            decodedSms = gammu.DecodeSMS(sms)
            if decodedSms == None:
                result["Text"] = smsPart['Text']
            else:
                text = ""
                for entry in decodedSms['Entries']:
                    if entry['Buffer'] != None:
                        text += entry['Buffer']

                result["Text"] = text

            results.append(result)

        return results
    
    except Exception as e:
        print(f"Error retrieving SMS: {e}")
        return []


def deleteSms(machine, sms):
    """Delete SMS by location"""
    try:
        list(map(lambda location: machine.DeleteSMS(Folder=0, Location=location), sms["Locations"]))
    except Exception as e:
        print(f"Error deleting SMS: {e}")


def message_requires_unicode(text):
    """Check if SMS text needs Unicode encoding (e.g. contains Cyrillic)"""
    if not text:
        return False
    return any(ord(char) > 127 for char in text)


def encodeSms(smsinfo):
    """Encode SMS for sending"""
    return gammu.EncodeSMS(smsinfo)
