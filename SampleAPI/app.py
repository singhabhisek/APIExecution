import os
import sqlite3
import time
from datetime import datetime

from flask import Flask, render_template, request, jsonify, url_for, flash, redirect, session
import requests
import json
import xml.etree.ElementTree as ET

from requests import RequestException

import logging
import os
from logging.handlers import TimedRotatingFileHandler

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Initialize logging
log_directory = "logs"  # Directory to store log files
os.makedirs(log_directory, exist_ok=True)

# Configure log file rotation (daily)
log_filename = os.path.join(log_directory, "service_execution.log")
logger = logging.getLogger("ServiceLogger")
logger.setLevel(logging.DEBUG)

# Log handler with daily rollover
handler = TimedRotatingFileHandler(log_filename, when="midnight", interval=1, backupCount=30)
handler.setLevel(logging.DEBUG)

# Log format
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


# Helper function to log actions with the current user
def get_logged_in_user():
    return os.getlogin()  # Gets the current Windows user


def log_action(action, service_name=None, operation_name=None, url=None, message=None, iteration=None):
    user = get_logged_in_user()
    log_message = f"User: {user} - Action: {action}"

    if service_name and operation_name:
        log_message += f" - Service: {service_name} - Operation: {operation_name}"
    if url:
        log_message += f" - URL: {url}"
    if iteration:
        log_message += f" - Iteration: {iteration}"
    if message:
        log_message += f" - Message: {message}"

    logger.info(log_message)


def log_error(error_message, url=None):
    user = get_logged_in_user()
    log_message = f"User: {user} - Error: {error_message}"
    if url:
        log_message += f" - URL: {url}"
    logger.error(log_message)



@app.context_processor
def inject_visitor_count():
    count = 0
    session['username'] = 'Default'
    # year = datetime.now().year
    # db = get_db_connection()
    # cursor = db.cursor()
    #
    # cursor.execute('''
    #     SELECT COUNT(DISTINCT user_id)
    #     FROM unique_visitors
    #     WHERE year = ?
    # ''', (year,))
    # count = cursor.fetchone()[0]

    version = '1.0'  # Define your version number here
    # print("hello5")

    user = {'userid': session['username'], 'role': 'admin', 'activeStatus': 'active'}
    return dict(visitor_count=count, version=version, user=user)



@app.route('/')
def index():
    """
    Render the upload_configuration.html templates with app_config.json data.
    """
    # Get the URL for app_config.json
    app_config_url = url_for('static', filename='app_config.json')
    with open(f'static/config/app_config.json') as f:
        app_config = json.load(f)
    return render_template('index.html', app_config=app_config, current_page='index')

UPLOAD_FOLDER = 'static/config'
ALLOWED_EXTENSIONS = {'json'}

def preprocess_json(json_string):
    # Replace single backslashes with double backslashes
    return json_string.replace('\\', '\\\\')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_json(data):
    required_keys = ['serviceName', 'operationName', 'useCase', 'successCriteria', 'endpoint', 'headers','sampleRequestLocation']
    entries_with_missing_keys = {}
    # Check if 'entries' key exists
    if 'entries' not in data:
        return False, {'error': 'The JSON file does not seem correct. Please recheck.'}

    for entry in data['entries']:

        # Preprocess sampleRequestLocation
        if 'sampleRequestLocation' in entry:
            entry['sampleRequestLocation'] = preprocess_json(entry['sampleRequestLocation'])

        missing_keys = [key for key in required_keys if key not in entry]
        if missing_keys:
            entries_with_missing_keys[entry.get('operationName', 'UnknownOperation')] = missing_keys

    if entries_with_missing_keys:
        return False, entries_with_missing_keys
    else:
        return True, {}

def backup_config(file_path):
    original_path = file_path #os.path.join(UPLOAD_FOLDER, 'config.json')
    filename_without_extension = os.path.splitext(os.path.basename(file_path))[0]

    timestamp = datetime.now().strftime("%Y%m%d%S")
    backup_path = os.path.join(UPLOAD_FOLDER, f'backup/{filename_without_extension}_{timestamp}.json')
    if os.path.exists(original_path):
        try:
            os.rename(original_path, backup_path)
            return True
        except Exception as e:
            print(f"Error while creating backup: {e}")
            return False
    else:
        return True

@app.route('/upload',  methods=['GET', 'POST'])
def upload():
    APP_CONFIG_FILE = 'static/config/app_config.json'

    if request.method == 'GET':
        return render_template('upload_config.html', current_page='upload')

    else:
        # print("Received Form Data:", request.form)  # Debugging line
        if 'file' not in request.files:
            log_error("No config file was provided.")
            return jsonify({'status': 'error', 'message': ' No config file was provided '}), 500
            # return redirect(request.url)
        file = request.files['file']

        # app_name = request.form['appName']
        app_name = request.form.get('appName')

        if file.filename == '':
            log_error("No selected file")
            flash('No selected file')

            return redirect(request.url)
        if file and allowed_file(file.filename):
            try:
                data = json.loads(file.read())
            except json.JSONDecodeError as e:
                log_error(f"Invalid JSON format: {e}")
                return jsonify({'status': 'error', 'message': 'Invalid JSON format'}), 500
            is_valid_json, missing_keys = validate_json(data)
            if is_valid_json:

                file_path = os.path.join('static/config',
                                         f"{app_name.lower().replace(' ', '_')}_config_file.json").replace('\\',
                                                                                                           '/')
                # Update app_config.json
                with open(APP_CONFIG_FILE, 'r+') as f:
                    data = json.load(f)
                    # Check if app_name already exists
                    existing_apps = [app['name'] for app in data['applications']]
                    if app_name not in existing_apps:
                       # return jsonify({'status': 'error', 'message': 'Application name already exists'}), 500
                        data['applications'].append({
                            'name': app_name,
                            'file': file_path
                        })
                        f.seek(0)
                        json.dump(data, f, indent=4)

                backup_successful = backup_config(file_path)
                if not backup_successful:
                    return jsonify({'status': 'error', 'message': 'Error creating backup'}), 500
                filename = 'config.json'
                file.seek(0)  # Reset file pointer to start before saving



                # file.save(os.path.join(UPLOAD_FOLDER, filename))
                file.save(file_path)
                print(file_path)
                log_action(action="File Uploaded", url=file_path)
                return jsonify({'status': 'success', 'message': 'File uploaded successfully'}), 200
            else:
                error_message = f'Invalid JSON structure. Missing keys for operations: {missing_keys}'
                log_error(error_message)
                return jsonify({'status': 'error', 'message': error_message}), 500
                # return jsonify({'status': 'error',
                #                 'message': 'Invalid JSON structure. Missing one or more required keys in "entries".'}), 500
        else:
            log_error("Invalid file format. Only JSON files are allowed.")
            return jsonify({'status': 'error', 'message': 'Invalid file format. Only JSON files are allowed.'}), 500
    return render_template('upload_config.html', current_page='upload')


@app.route('/user_info', methods=['GET'])
def get_user_info():
    # Assuming you have a function to get the current logged-in user
    # This could be from session or database depending on your auth mechanism
    user_id = get_logged_in_user()

    # Check user access level from the database
    conn = sqlite3.connect('user_access.db')
    cursor = conn.cursor()
    cursor.execute('SELECT access_level FROM user_access WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        access_level = result[0]
    else:
        access_level = "user"

    # access_level = "user"  # Replace with your function

    return jsonify({
        'userId': user_id,
        'accessLevel': access_level
    })

# Define a global variable to toggle the header
add_executed_by_header = True
# Define the timeout duration
request_timeout = 120  # in seconds

@app.route('/execute', methods=['POST'])
def execute():
    """
    Execute the selected services based on the provided JSON configuration.
    """
    try:
        data = request.get_json()  # Parse JSON data from request
        selected_services = data.get('services', [])
        targetJson = data.get('targetJson','')
        iteration_count = int(data.get('iterationCount', 1))  # Default to 1 if not provided
        iteration_count = min(iteration_count, 3)  # Ensure iteration_count is not greater than 3

        delay_between_requests = float(data.get('delayBetweenRequests', 0.5))  # Delay between requests in seconds

        # Load configuration from static.json
        if not targetJson:
            log_error("No target JSON config found!")
            return jsonify({'status': 'error', 'message': 'No target JSON config found!'})

        with open(targetJson) as f:
            config = json.load(f)


        # Populate services list from static
        services = []
        for entry in config['entries']:
            services.append(entry['serviceName'])

        if not selected_services:
            log_action(action="Execution", message="No services selected.")
            return jsonify({'status': 'error', 'message': 'No services selected!'})

        # Log the execution request with the current user and services selected
        log_action(action="Execution",
                   message=f"Starting execution for {len(selected_services)} service(s): {selected_services}. Iterations: {iteration_count}")

        result = {'status': 'success', 'responses': {}}
        for service in selected_services:
            service_parts = service.split(':')  # Split ServiceName:OperationName into parts
            if len(service_parts) != 2:
                log_error(f"Invalid service format: {service}")
                return jsonify({'status': 'error', 'message': 'Invalid service format: ' + service})

            service_name, operation_name = service_parts  # Extract ServiceName and OperationName

            responses = []
            status_descriptions = []  # List to store response codes

            overall_status = 'GREEN'  # Assume GREEN initially
            passed_count = 0  # Counter for passed iterations
            raw_requests = []  # List to store raw requests
            for entry in config['entries']:
                if entry['serviceName'] == service_name and entry.get(
                        'operationName') == operation_name:  # Check both ServiceName and OperationName

                    # method = 'GET' if entry.get('sampleRequestLocation') == '' else 'POST'
                    method = entry.get('httpMethod', 'GET')  # Default to GET if not specified
                    headers = entry.get('headers', {})
                    request_executed = False
                    processed_requests = set()
                    # Check if the service name and operation name combination has been processed
                    service_operation_key = (entry['serviceName'], entry.get('operationName', ''))

                    for i in range(iteration_count):  # Perform iterations
                        try:
                            # Log the execution for each service and operation with URL and iteration
                            log_action(action="Service Execution", service_name=service_name,
                                       operation_name=operation_name, url=entry['endpoint'], iteration=i + 1)

                            raw_request = {'method': method, 'url': entry['endpoint'], 'headers': headers}
                            if method == 'POST':

                                # Handling sample request files
                                if entry['sampleRequestLocation'] != '':
                                    try:
                                        with open(entry['sampleRequestLocation'], 'r') as f:
                                            sample_request_content = f.read()
                                    except FileNotFoundError:
                                        error_message = f"{service_name} - {operation_name} => File not found: {entry['sampleRequestLocation']}"
                                        return jsonify({'status': 'error', 'message': error_message}), 500
                                    try:
                                        xml_root = ET.fromstring(sample_request_content)
                                        # Convert XML object to string for display
                                        xml_string = ET.tostring(xml_root, encoding='unicode')
                                        raw_request['data'] = xml_string
                                        raw_request['xml'] = xml_string
                                        raw_request['headers']['Content-Type'] = 'application/xml'

                                    except ET.ParseError:
                                        # If parsing as XML fails, consider it as JSON
                                        try:
                                            json_content = json.loads(sample_request_content)
                                            raw_request['data'] = json_content
                                            raw_request['json'] = json_content
                                            raw_request['headers']['Content-Type'] = 'application/json'
                                        except ValueError:
                                            return jsonify(
                                                {'status': 'error', 'message': 'Invalid sample request content!'})
                            if service_operation_key not in processed_requests:
                                raw_requests.append(raw_request)
                                processed_requests.add(service_operation_key)  # Mark as processed

                            if not request_executed:
                                if add_executed_by_header:
                                    raw_request['headers']['executed_by'] = 'api_hc_tool'  # Add executed_by header if flag is set

                                if method == 'GET':
                                    if entry['sampleRequestLocation'] != '':
                                        # Read sample request content
                                        try:
                                            with open(entry['sampleRequestLocation'], 'r') as f:
                                                sample_request_content = f.read()
                                        except FileNotFoundError:
                                            error_message = f"{service_name} - {operation_name} => File not found: {entry['sampleRequestLocation']}"
                                            log_error(f"Execution error - GET: {error_message}", url=entry['sampleRequestLocation'])
                                            return jsonify({'status': 'error', 'message': error_message}), 500

                                        # Send request with appropriate content type
                                        content_type = 'application/json'
                                        try:
                                            # Try parsing the content as XML
                                            ET.fromstring(sample_request_content)
                                            content_type = 'application/xml'
                                        except ET.ParseError:
                                            # If parsing as XML fails, consider it as JSON
                                            try:
                                                json.loads(sample_request_content)
                                            except ValueError:
                                                # log_error(f"Execution error - GET: Invalid JSON OR XML request content!",
                                                #           url=entry['sampleRequestLocation'])

                                                error_message = f"{service_name} - {operation_name} => Invalid JSON OR XML request content: {entry['sampleRequestLocation']}"
                                                log_error(f"Execution error - GET: {error_message}",
                                                          url=entry['sampleRequestLocation'])
                                                return jsonify({'status': 'error', 'message': error_message}), 500

                                        headers['Content-Type'] = content_type
                                        start_time = time.time()
                                        response = requests.get(entry['endpoint'], headers=headers,
                                                                data=sample_request_content.encode('utf-8'))
                                        end_time = time.time()
                                    else:
                                        # Send GET request without data
                                        start_time = time.time()
                                        response = requests.get(entry['endpoint'], headers=headers, verify=False)
                                        end_time = time.time()
                                else:
                                    if entry['sampleRequestLocation'] != '':
                                        # Read sample request content
                                        try:
                                            with open(entry['sampleRequestLocation'], 'r') as f:
                                                sample_request_content = f.read()
                                        except FileNotFoundError:
                                            error_message = f"{service_name} - {operation_name} => File not found: {entry['sampleRequestLocation']}"
                                            log_error(f"Execution error - POST: {error_message}",
                                                      url=entry['sampleRequestLocation'])
                                            return jsonify({'status': 'error', 'message': error_message}), 500

                                        # Determine request content type based on sample request location file content
                                        content_type = 'application/json'
                                        try:
                                            # Try parsing the content as XML
                                            ET.fromstring(sample_request_content)
                                            content_type = 'application/xml'
                                        except ET.ParseError:
                                            # If parsing as XML fails, consider it as JSON
                                            try:
                                                json.loads(sample_request_content)
                                            except ValueError:
                                                log_error(
                                                    f"Execution error - POST: Invalid JSON OR XML request content!",
                                                    url=entry['sampleRequestLocation'])
                                                error_message = f"{service_name} - {operation_name} => Invalid JSON OR XML request content: {entry['sampleRequestLocation']}"
                                                log_error(f"Execution error - GET: {error_message}",
                                                          url=entry['sampleRequestLocation'])
                                                return jsonify({'status': 'error', 'message': error_message}), 500

                                        # Send request with appropriate content type
                                        if content_type == 'application/xml':
                                            start_time = time.time()
                                            response = requests.post(entry['endpoint'], headers=headers,
                                                                     data=sample_request_content.encode('utf-8'))
                                            end_time = time.time()
                                        else:
                                            start_time = time.time()
                                            response = requests.post(entry['endpoint'], headers=headers,
                                                                     json=json.loads(sample_request_content))
                                            end_time = time.time()
                                    else:
                                        # Send POST request without data
                                        start_time = time.time()
                                        response = requests.post(entry['endpoint'], headers=headers)
                                        end_time = time.time()
                                    request_executed = True
                                # Calculate response time
                                response_time = end_time - start_time

                            # Parse response to extract StatusCD and StatusDesc if available
                            status_cd = None
                            status_desc = None
                            try:
                                root = ET.fromstring(response.text)
                                status_cd_element = root.find('.//StatusCD')
                                status_cd = status_cd_element.text if status_cd_element is not None else ''

                                status_desc_element = root.find('.//StatusDesc')
                                status_desc = status_desc_element.text if status_desc_element is not None else ''
                            except (ET.ParseError, AttributeError):
                                try:
                                    json_response = json.loads(response.text)
                                    status_cd = json_response.get('StatusCD', '')
                                    status_desc = json_response.get('StatusDesc', '')
                                except (json.JSONDecodeError, AttributeError):
                                    pass

                            # Perform validation based on successCriteria
                            iteration_status = 'PASS' if entry['successCriteria'] in response.text else 'FAIL'
                            if iteration_status == 'PASS':
                                passed_count += 1  # Increment passed count
                            if overall_status != 'RED' and iteration_status == 'FAIL':
                                overall_status = 'AMBER'  # Update overall_status if any iteration fails
                            if overall_status != 'AMBER' and iteration_status == 'AMBER':
                                overall_status = 'AMBER'  # Update overall_status if any iteration is AMBER
                            if iteration_status == 'FAIL':
                                overall_status = 'RED'  # Update overall_status if any iteration fails

                            responses.append({'response': response.text, 'status': iteration_status, 'status_cd': status_cd, 'status_desc': status_desc, 'response_time': response_time})

                            # Append response code and message to status_descriptions
                            if iteration_status == 'FAIL':
                                overall_status = 'AMBER'
                                status_descriptions.append('200 - Business Exception')
                            else:
                                status_descriptions.append(f'{response.status_code} - {response.reason}')

                            # Log service response status
                            log_action("Service Execution", service_name, operation_name,
                                       message=f"Status: {iteration_status}", iteration=i + 1)

                            # Introduce delay between requests
                            time.sleep(delay_between_requests)

                        except requests.Timeout:
                            log_error(f"Timeout error on {service_name}:{operation_name}")

                            # Handle timeout exception
                            responses.append({
                                'response': 'Operation terminated due to timeout',
                                'status': 'ERROR',
                                'status_cd': 500,
                                'status_desc': 'Operation terminated due to timeout',
                                'response_time': request_timeout
                            })

                        except requests.exceptions.ConnectionError as e:
                            log_error(f"Connection error: {str(e)}")

                            overall_status = 'RED';
                            responses.append(
                                {'response': f'Connection error occurred while accessing the service: {str(e)}', 'status': 'ERROR'})
                            status_descriptions.append('500 - Internal Server Error')
                        except RequestException as e:
                            overall_status = 'RED';
                            responses.append(
                                {'response': f'Error occurred while accessing the service: {str(e)}', 'status': 'ERROR'})
                            status_descriptions.append(f'{response.status_code} - {response.reason}')
                    break

            # Now, serialize the raw requests to JSON
            serialized_raw_requests = []
            for requestw in raw_requests:
                # print(requestw)
                serialized_request = {
                    'method': requestw['method'],
                    'url': requestw['url'],
                    'headers': requestw['headers']
                }
                # Include data if present and not XML
                if 'data' in requestw:
                    if 'xml' in requestw:
                        serialized_request['data'] = requestw['xml']
                    else:
                        serialized_request['data'] = requestw['data']
                serialized_raw_requests.append(serialized_request)

            # Include serialized raw requests in the result
            result['responses'][service] = {
                'responses': responses,
                'passed_count': passed_count,
                'total_iterations': iteration_count,
                'overall_status': overall_status,
                'status_descriptions': status_descriptions,
                'raw_requests': serialized_raw_requests
            }

        print(result)
        log_action("Execution Complete", message="All services executed successfully.")

        return jsonify(result)
    except ValueError as e:
        log_error(f"ValueError: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})


# Load data from config.json
def load_data(app_config):
    try:
        with open(app_config, 'r') as file:
            config_data = json.load(file)
        # Extract the relevant data from the config data
        data = []
        for entry in config_data.get('entries', []):
            data.append({
                'serviceName': entry.get('serviceName', ''),
                'operationName': entry.get('operationName', ''),
                'useCase': entry.get('useCase', ''),
                'successCriteria': entry.get('successCriteria', ''),
                'endpoint': entry.get('endpoint', ''),
                'sampleRequestLocation': entry.get('sampleRequestLocation', ''),
                'sampleRequestText': entry.get('sampleRequestText', ''),
                'httpMethod': entry.get('httpMethod', ''),
                'headers': entry.get('headers', {})
            })
        return data
    except Exception as e:
        # Log the error or handle it appropriately
        print(f"Error loading data: {e}")
        return []

# Save data to config.json
def save_data(data, targetJSON):
    try:
        # Log the current state of data before any modifications
        # logger.debug(f"Current data before saving: {json.dumps(data, indent=4)}")

        # Remove the 'appConfig' key from each record
        for record in data:
            # Log the record that is being modified
            logger.debug(f"Removing 'appConfig' from record: {json.dumps(record, indent=4)}")
            record.pop('appConfig', None)

        # Log the data that will be saved
        logger.info(f"Saving data to {targetJSON}: {json.dumps(data, indent=4)}")

        with open(targetJSON, 'w') as file:
            json.dump({"entries": data}, file, indent=4)
        logger.info(f"Data successfully saved to {targetJSON}")
        return True
    except Exception as e:
        # Log the error or handle it appropriately
        print(f"Error saving data: {e}")
        log_error(f"Error saving data: {e}", url=targetJSON)
        return False

@app.route('/edit_configuration')
def edit_configuration():
    return render_template('edit_configuration.html', current_page='edit')

@app.route('/data', methods=['POST'])
def get_data():
    try:
        print("dfdfdfdfdfdf")
        app_config = request.json.get('appConfig')
        print(app_config)
        data = load_data(app_config)
        print(data)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add', methods=['POST'])
def add_record():
    try:
        new_record = request.json
        app_config = new_record.get('appConfig')
        data = load_data(app_config)

        # Check if the combination of serviceName and operationName already exists
        exists = any((r['serviceName'].lower() == new_record.get('serviceName', '').lower() and
                      r['operationName'].lower() == new_record.get('operationName', '').lower()) for r in data)

        if exists:
            log_error("Record with the same Service Name and Operation Name already exists!", url=app_config)
            return jsonify({"success": False, "message": "Record with the same Service Name and Operation Name already exists!"}), 400
        else:
            data.append(new_record)
            if save_data(data, app_config):
                log_action(action="Record Added", service_name=new_record['serviceName'],
                           operation_name=new_record['operationName'], url=app_config)
                return jsonify({"success": True, "message": "Record added successfully!"})
            else:
                log_error("Failed to add record. Please try again later.", url=app_config)
                return jsonify({"success": False, "message": "Failed to add record. Please try again later."}), 500
    except Exception as e:
        log_error(f"Error adding record: {str(e)}", url=app_config)
        return jsonify({"error": str(e)}), 500


# Route to save request text to file
@app.route('/save_request_text', methods=['POST'])
def save_request_text():
    try:
        data = request.json
        fileName = data.get('fileName')
        sampleRequestText = data.get('sampleRequestText')
        filePath = os.path.join('static', 'requests', fileName)

        with open(filePath, 'w') as file:
            file.write(sampleRequestText)
        log_action(action="Request Text Saved", url=filePath)
        return jsonify({"success": True, "message": "Request text saved successfully!"})
    except Exception as e:
        log_error(f"Error saving request text: {str(e)}", url=filePath)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/edit/<int:index>', methods=['PUT'])
def edit_record(index):
    try:
        edited_record = request.json

        app_config = edited_record.get('appConfig')
        data = load_data(app_config)
        data[index] = edited_record
        if save_data(data, app_config):
            log_action(action="Record Edited", service_name=edited_record['serviceName'],
                       operation_name=edited_record['operationName'], url=app_config)
            return jsonify({"success": True, "message": "Record edited successfully!"})
        else:
            log_error("Failed to edit record. Please try again later.", url=app_config)
            return jsonify({"success": False, "message": "Failed to edit record. Please try again later."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/delete/<int:index>', methods=['DELETE'])
def delete_record(index):
    try:
        target_json = request.json.get('appConfig', None)
        data = load_data(target_json)
        del data[index]
        if save_data(data, target_json):
            log_action(action="Record Deleted", url=target_json)
            return jsonify({"success": True, "message": "Record deleted successfully!"})
        else:
            log_error("Failed to delete record. Please try again later.", url=target_json)
            return jsonify({"success": False, "message": "Failed to delete record. Please try again later."}), 500
    except Exception as e:
        log_error(f"Error deleting record: {str(e)}", url=target_json)
        return jsonify({"error": str(e)}), 500


@app.route('/add_application', methods=['POST'])
def add_application():
    # Get the application name from the form data
    application_name = request.form.get('applicationName')

    # Check if the application name already exists (case insensitive)
    with open('static/config/app_config.json', 'r') as f:
        data = json.load(f)
        existing_applications = [app['name'].lower() for app in data['applications']]
    if application_name.lower() in existing_applications:
        log_error("Application already exists", url=application_name)
        return jsonify({'error': 'Application already exists'}), 400

    # Add the new application to app.py
    new_application = {
        "name": application_name,
        "file": f"static/config/{application_name}_config_file.json"
    }
    data['applications'].append(new_application)
    with open('static/config/app_config.json', 'w') as f:
        json.dump(data, f, indent=4)

    # Create a new configuration file for the application
    config_file_path = f"static/config/{application_name}_config_file.json"
    with open(config_file_path, 'w') as f:
        initial_entry = {"entries": []}
        json.dump(initial_entry, f, indent=4)

    log_error(f"Application Added - {application_name}", url=application_name)
    return jsonify({'success': True, 'message': 'Application added successfully'}), 200


@app.route('/get_applications', methods=['GET'])
def get_applications():
    try:
        # Load the app_config.json file
        with open('static/config/app_config.json', 'r') as file:
            app_config = json.load(file)

        # Extract the list of applications
        applications = app_config.get('applications', [])

        # Return the list of applications as JSON
        return jsonify({'applications': applications}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)


# User Story
# As a developer or tester, I want to use this API tool to execute requests to multiple services in sequence or in parallel with iterations, so I can verify if the services behave as expected (i.e., respond with expected statuses and within acceptable time limits).
#
# This tool allows me to:
#
# Choose specific services and their operations for execution.
# Define how many times I want to execute the services.
# Apply a delay between consecutive requests.
# Automatically log the request, response, and execution status for each service.
# If an error occurs during the process (like timeout or connection error), the tool logs the error and returns the details. Additionally, it allows me to load service configurations from a JSON file, which contains information about services, their URLs, headers, and request types.
#
# Flow Diagram
# Here is a simplified flow diagram that visualizes the process:
#
# plaintext
# Copy code
# [ User Requests Service Execution ] --> [ Parse Request JSON Input ] --> [ Validate Input Data ]
#     |
#     v
# [ Load Service Configuration ] --> [ For Each Selected Service ]
#     |
#     v
# [ Loop for Iterations ]
#     |
#     +--------------------> [ Create Request for Service ] ---> [ Execute Request (GET/POST) ]
#     |                                  |                                 |
#     |                                  |                                 v
#     |                                  |                    [ Log Request and Response ]
#     |                                  |                                 |
#     |                                  |                                 v
#     |                                  |                   [ Check for Success Criteria ] -->(PASS/FAIL)
#     |                                  |                                 |
#     |                                  v                                 v
#     +---------------------------- [ Introduce Delay ]          [ Log Status: AMBER/RED]
#                                             |
#                                             v
#                                   [ Check for Errors or Timeouts ]
#                                             |
#                                             v
#                                 [ Collect Raw Requests & Responses ]
#                                             |
#                                             v
#                                   [ Return Final Execution Result ]
# How the Code Logic Works
# Receive Input:
#
# The API receives a POST request at /execute containing a JSON payload.
# This payload includes the list of services to be executed, the number of iterations, and the delay between requests.
# Validate Input:
#
# The selected services are validated to ensure that the request format is correct (serviceName
# ).
# The configuration file (targetJson) is loaded, containing the details for each service (URL, method, headers, etc.).
# Start Execution:
#
# For each selected service, the tool splits the service string into serviceName and operationName.
# It loops through each service and its operation to execute it for the number of specified iterations (up to 3 iterations by default).
# Perform Request:
#
# Depending on whether the service method is GET or POST, the request is constructed.
# POST requests: If a sample request file is provided, it will be read and sent as part of the request.
# GET requests: The sample request data, if present, is appended as headers or part of the URL.
# For each request, the response is captured, and additional processing is performed (such as adding an executed_by header, if enabled).
# Check Response:
#
# Once a request is executed, the response is checked for:
# Status code (200, 500, etc.)
# Success criteria defined in the configuration (e.g., checking if a certain string or status is present in the response).
# The request result is marked as PASS or FAIL, and the overall execution status is updated to:
# GREEN if all iterations pass.
# AMBER if some iterations fail.
# RED if a critical failure occurs (like a connection error or timeout).
# Handle Errors:
#
# If any issues occur during execution (like timeouts or connection errors), the tool logs the error, and the service's status is updated accordingly.
# Logging and Delays:
#
# After each request, logs are created to capture the request, response, and status.
# A delay (defined by the user) is introduced between consecutive iterations or service executions.
# Final Result:
#
# Once all iterations are completed for all services, the tool compiles the results (responses, status descriptions, raw requests, etc.) and sends them back to the user as a JSON response.
