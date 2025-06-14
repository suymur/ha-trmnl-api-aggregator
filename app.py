from flask import Flask, jsonify, request
import requests
import json
import functools
import yaml
from datetime import datetime, timedelta, timezone # Add timezone for UTC
import os
import sys
import logging
import secrets
from apscheduler.schedulers.background import BackgroundScheduler
import zoneinfo # New import for timezone handling

app = Flask(__name__)

# Home Assistant configuration
HA_URL = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

# Timezone and Time Format configuration
TIMEZONE_STR = os.getenv("TIMEZONE", "UTC") # Default to UTC if not specified
TIME_FORMAT = os.getenv("TIME_FORMAT", "%H:%M:%S") # Default to HH:MM:SS if not specified

# API Token for external access (e.g., from your trmnl server)
API_BEARER_TOKEN = os.getenv("API_BEARER_TOKEN")

# Base URL for the application, useful when deployed behind a reverse proxy
BASE_URL = os.getenv("BASE_URL", "")

# The specific API path for the e-ink device
EINK_API_PATH = os.getenv("EINK_API_PATH", "/eink-data")

# Configure logging
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

if not HA_URL:
    logging.error("HA_URL environment variable is not set. Please configure it in your .env file.")
    sys.exit(1)

if not HA_TOKEN:
    logging.error("HA_TOKEN environment variable is not set. Please configure it in your .env file.")
    sys.exit(1)

# New: Check for API_BEARER_TOKEN
if not API_BEARER_TOKEN:
    logging.error("API_BEARER_TOKEN environment variable is not set. This token is required for external access security. Please configure it in your .env file.")
    sys.exit(1)

# Validate and set up timezone
try:
    target_timezone = zoneinfo.ZoneInfo(TIMEZONE_STR)
except zoneinfo.ZoneInfoNotFoundError:
    logging.error(f"Invalid TIMEZONE specified: '{TIMEZONE_STR}'. Please use a valid IANA timezone name (e.g., 'Europe/Berlin'). Exiting.")
    sys.exit(1)
except ImportError: # This should ideally not happen if Python 3.9+ is used, but good for robustness
    logging.error("The 'zoneinfo' module is not available. Please ensure you are running Python 3.9+ or install 'pytz' and adjust the code. Exiting.")
    sys.exit(1)


# Ensure EINK_API_PATH starts with '/'
if not EINK_API_PATH.startswith('/'):
    EINK_API_PATH = '/' + EINK_API_PATH

logging.info(f"E-ink API endpoint path set to: {EINK_API_PATH}")
if BASE_URL: # This check is for logging only, BASE_URL is already processed above
    logging.info(f"Base URL for reverse proxy: {BASE_URL}")

# New: Decorator for token authentication
def token_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            logging.warning("Unauthorized access attempt: Missing Authorization header.")
            return jsonify({"error": "Unauthorized: Missing Authorization header"}), 401

        try:
            token_type, token = auth_header.split(None, 1) # Split by first space
        except ValueError:
            logging.warning("Unauthorized access attempt: Invalid Authorization header format.")
            return jsonify({"error": "Unauthorized: Invalid Authorization header format"}), 401

        if token_type.lower() != 'bearer':
            logging.warning(f"Unauthorized access attempt: Invalid token type '{token_type}'.")
            return jsonify({"error": "Unauthorized: Invalid token"}), 401
            
        # Use constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(token, API_BEARER_TOKEN):
            logging.warning("Unauthorized access attempt: Invalid Bearer token.")
            return jsonify({"error": "Unauthorized: Invalid token"}), 401

        logging.info("Token authentication successful.")
        return f(*args, **kwargs)
    return decorated_function
    
# Global variable to store the last fetched data
last_fetched_data = {}

CONFIG_FILE = os.getenv("CONFIG_FILE", "config.yaml")

def load_config():
    """Loads Home Assistant sensor entities from the config.yaml file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.warning(f"{CONFIG_FILE} not found. Using default sensors.")
        # Default sensors if config.yaml is missing
        # Updated default to match new structure
        return {"home_assistant_sensors": [
            {"entity_id": "sensor.living_room_temperature", "fields": ["state", "attributes.unit_of_measurement"]},
            {"entity_id": "sensor.living_room_humidity", "fields": ["state", "attributes.unit_of_measurement"]},
            {"entity_id": "weather.home", "fields": ["state"]},
            {"entity_id": "sensor.energy_usage", "fields": ["state", "attributes.unit_of_measurement"]}
        ]}
    except yaml.YAMLError as e:
        logging.error(f"Error parsing {CONFIG_FILE}: {e}. Using default sensors.")
        # Default sensors if config.yaml is malformed
        # Updated default to match new structure
        return {"home_assistant_sensors": [
            {"entity_id": "sensor.living_room_temperature", "fields": ["state", "attributes.unit_of_measurement"]},
            {"entity_id": "sensor.living_room_humidity", "fields": ["state", "attributes.unit_of_measurement"]},
            {"entity_id": "weather.home", "fields": ["state"]},
            {"entity_id": "sensor.energy_usage", "fields": ["state", "attributes.unit_of_measurement"]}
        ]}
    
# Helper to get nested values from a dictionary
def get_nested_value(data, path):
    parts = path.split('.')
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None # Path not found
    return current

def is_utc_timestamp(value):
    """Check if a value is a UTC timestamp string and convert it to local timezone format."""
    if not isinstance(value, str):
        return False, value
    
    # Common UTC timestamp patterns
    utc_patterns = [
        # ISO format with timezone info
        lambda s: s.endswith('+00:00') or s.endswith('Z'),
        # ISO format patterns
        lambda s: 'T' in s and ('.' in s or ':' in s) and len(s) > 15
    ]
    
    # Check if it matches UTC timestamp patterns
    if not any(pattern(value) for pattern in utc_patterns):
        return False, value
    
    try:
        # Try to parse as ISO format timestamp
        if value.endswith('Z'):
            dt_object = datetime.fromisoformat(value.replace('Z', '+00:00'))
        else:
            dt_object = datetime.fromisoformat(value)
        
        # Convert to target timezone and format
        local_dt = dt_object.astimezone(target_timezone)
        formatted_time = local_dt.strftime(TIME_FORMAT)
        
        logging.debug(f"Converted UTC timestamp '{value}' to local time '{formatted_time}'")
        return True, formatted_time
        
    except (ValueError, TypeError) as e:
        logging.debug(f"Failed to parse potential timestamp '{value}': {e}")
        return False, value

def _fetch_and_process_ha_data():
    """
    Fetches specified sensor data from Home Assistant, processes it,
    and returns a compact JSON response suitable for e-ink displays.
    """
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Load the list of sensors to fetch from config.yaml
    config = load_config()
    entities_to_fetch = config.get("home_assistant_sensors", [])
    
    compact_data = {} # Dictionary to store the processed data for the e-ink display
    
    # Fetch each sensor from Home Assistant
    for entity_config in entities_to_fetch:
        logging.debug(f"Processing entity config: {entity_config}")
        sensor_id = entity_config.get("entity_id")
        fields_to_extract = entity_config.get("fields", ["state"]) # Default to 'state' if no fields specified

        if not sensor_id:
            logging.warning("Skipping entity with no 'entity_id' specified in config.yaml.")
            continue

        try:
            response = requests.get(
                f"{HA_URL}/api/states/{sensor_id}",
                headers=headers,
                timeout=5 # Set a timeout for the request
            )
            
            logging.debug(f"HA API response for {sensor_id}: Status {response.status_code}, Text: {response.text[:200]}...") # Log first 200 chars of response

            if response.status_code == 200:
                sensor_data = response.json()
                logging.debug(f"Successfully fetched data for {sensor_id}: {json.dumps(sensor_data, indent=2)}")
                
                # Get friendly name for better keys, fallback to entity_id part
                friendly_name = get_nested_value(sensor_data, 'attributes.friendly_name')
                if not friendly_name:
                    friendly_name = sensor_id.split('.')[-1]
                
                # Sanitize friendly_name for use as a dictionary key prefix
                key_prefix = friendly_name.lower().replace(' ', '_').replace('.', '_').replace('-', '_')

                for field_path in fields_to_extract:
                    value = get_nested_value(sensor_data, field_path)
                    logging.debug(f"  Extracting field '{field_path}' for {sensor_id}. Value: {value}")
                    
                    # Determine the key for compact_data
                    # If only 'state' is requested, use just the friendly name as key
                    if field_path == 'state' and len(fields_to_extract) == 1:
                        output_key = key_prefix
                    else:
                        # Otherwise, combine friendly name and field name
                        field_name_short = field_path.split('.')[-1]
                        output_key = f"{key_prefix}_{field_name_short}"

                    # Special handling for timestamp device_class if 'state' is requested (remaining time calculation)
                    if field_path == 'state' and get_nested_value(sensor_data, 'attributes.device_class') == 'timestamp':
                        if value != 'unknown' and value is not None:
                            try:
                                dt_object = datetime.fromisoformat(value)
                                time_diff = dt_object - datetime.now(dt_object.tzinfo)
                                if time_diff.total_seconds() > 0:
                                    total_seconds = int(time_diff.total_seconds())
                                    hours, remainder = divmod(total_seconds, 3600)
                                    minutes, seconds = divmod(remainder, 60)
                                    compact_data[output_key] = f"{hours:02d}h {minutes:02d}m"
                                else:
                                    compact_data[output_key] = "Done"
                            except ValueError:
                                logging.warning(f"Could not parse timestamp for {sensor_id} field {field_path}: {value}")
                                compact_data[output_key] = value # Fallback to raw value
                        else:
                            compact_data[output_key] = value # "unknown" or None
                    else:
                        # Check if value is a UTC timestamp and convert it
                        is_timestamp, converted_value = is_utc_timestamp(value)
                        compact_data[output_key] = converted_value
                        logging.debug(f"  Added to compact_data: '{output_key}': {converted_value}" + 
                                    (f" (converted from UTC timestamp)" if is_timestamp else ""))
                    
            else:
                logging.error(f"Failed to fetch {sensor_id} from Home Assistant. Status code: {response.status_code}, Response: {response.text}")
        except requests.exceptions.Timeout:
            logging.warning(f"Timeout fetching {sensor_id} from Home Assistant.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching {sensor_id}: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred while processing {sensor_id}: {e}")
    
    # Add current timestamp to the data, indicating when it was last updated
    # Get current UTC time
    now_utc = datetime.now(timezone.utc)
    # Convert to target timezone
    now_local = now_utc.astimezone(target_timezone)
    # Format using the specified format
    compact_data["last_updated"] = now_local.strftime(TIME_FORMAT)
    
    return compact_data

def scheduled_data_pull():
    """Function to be called by the scheduler to pull and store data."""
    global last_fetched_data
    logging.info("Performing scheduled data pull...")
    fetched_data = _fetch_and_process_ha_data()
    if fetched_data and len(fetched_data) > 1: # Check for more than just last_updated
        last_fetched_data = fetched_data
        logging.info("Data pull complete. Data updated.")
        logging.debug(f"Retrieved data: {json.dumps(fetched_data, indent=2)}")
    else:
        logging.warning("Data pull failed or returned empty/incomplete. Keeping previous data.")
        logging.debug(f"Fetched data was: {json.dumps(fetched_data, indent=2) if fetched_data else 'None'}")

@app.route(EINK_API_PATH)  # This is the API endpoint your e-ink device will call
@token_required # Apply the decorator here
def get_eink_data():
    """
    Returns the last fetched data.
    """
    if not last_fetched_data:
        # If no data has been fetched yet (e.g., app just started),
        # attempt to fetch it immediately for the first request.
        # This is a fallback and might block the first request briefly.
        logging.info("No data available yet. Attempting immediate data fetch for first request.")
        scheduled_data_pull() # Call the pull function directly
        if not last_fetched_data: # If still no data after immediate pull
            return jsonify({"error": "Data not yet available or failed to fetch."}), 503

    return jsonify(last_fetched_data)

if __name__ == '__main__':
    # Initialize and start the scheduler
    scheduler = BackgroundScheduler()
    polling_interval_minutes = int(os.getenv("POLLING_INTERVAL_MINUTES", 5)) # Default to 5 minutes
    scheduler.add_job(scheduled_data_pull, 'interval', minutes=polling_interval_minutes)
    scheduler.start()

    # Perform an initial data pull immediately on startup
    scheduled_data_pull()

    # Run the Flask app, accessible from any IP on port 8234
    app.run(host='0.0.0.0', port=8234)
