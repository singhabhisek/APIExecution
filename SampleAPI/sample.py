import json
import base64
from urllib.parse import urlparse

# Load the input Postman collection JSON
with open('My Wave Collection.postman_collection.json', 'r') as file:
    postman_data = json.load(file)

# Prepare the output structure
output = {
    "entries": []
}

# Recursive function to process the Postman items
def process_item(item, service_name=None):
    request_count = 1  # To track the request number for sampleRequestLocation

    for sub_item in item:
        # If it has nested items, call recursively
        if 'item' in sub_item:
            # Use the name from the sub_item or inherit the parent service_name
            current_service_name = sub_item.get('name', service_name)
            process_item(sub_item['item'], service_name=current_service_name)
        else:
            # Extract request details
            request = sub_item.get('request', {})
            headers = {header['key']: header['value'] for header in request.get('header', [])}
            url = request.get('url', {})
            endpoint = url.get('raw', '')
            method = request.get('method', '')

            # Determine the service name: either from the name field or fallback to last part of the URL path
            if service_name:
                final_service_name = service_name
            else:
                # Parse the URL and use the last path segment as the fallback service name
                parsed_url = urlparse(endpoint)
                path_segments = parsed_url.path.strip('/').split('/')
                final_service_name = path_segments[-1] if path_segments else 'DefaultService'

            # Check if 'auth' section exists and handle authentication
            auth = request.get('auth', {})
            if auth:
                if auth.get('type') == 'bearer':
                    bearer_token_info = auth.get('bearer', [{}])
                    token = bearer_token_info[0].get('value', '')
                    if token:
                        headers['Authorization'] = f"Bearer {token}"
                elif auth.get('type') == 'basic':
                    basic_auth = auth.get('basic', [])
                    username = ''
                    password = ''
                    for cred in basic_auth:
                        if cred.get('key') == 'username':
                            username = cred.get('value', '')
                        elif cred.get('key') == 'password':
                            password = cred.get('value', '')
                    if username and password:
                        credentials = f"{username}:{password}"
                        encoded_credentials = base64.b64encode(credentials.encode()).decode()
                        headers['Authorization'] = f"Basic {encoded_credentials}"

            # Create an entry for the "application config" format
            entry = {
                "serviceName": final_service_name,
                "operationName": sub_item['name'],
                "useCase": f"Description of Use Case for {final_service_name}",
                "successCriteria": "order",  # Default to "order", you can adjust based on the use case
                "endpoint": endpoint,
                "sampleRequestLocation": f"static/request{request_count}.txt",  # Set dynamic request location
                "sampleRequestText": "",  # Add sample request text, which may be populated below
                "httpMethod": method,
                "headers": headers
            }

            # Check if the request has a body and set the sampleRequestText accordingly
            body = request.get('body', {})
            if 'raw' in body:
                raw_body = body['raw']
                # Escape the body content (for quotes, backslashes, newlines)
                escaped_body = raw_body.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                entry['sampleRequestText'] = escaped_body
            else:
                # Ensure sampleRequestText is present but blank if no body
                entry['sampleRequestText'] = ""

            # Add the entry to the output
            output["entries"].append(entry)
            request_count += 1


# Start processing the items in the Postman collection
process_item(postman_data.get('item', []))

# Write the transformed data to an output file
with open('application_config.json', 'w') as outfile:
    json.dump(output, outfile, indent=4)

print("Transformation completed successfully!")
