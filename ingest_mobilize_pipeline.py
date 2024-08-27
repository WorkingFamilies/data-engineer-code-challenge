"""Ingests Event Attendances data from Mobilize API and loads the data into bigquery."""
import requests
from google.cloud import bigquery
import os
import logging
import smart_open
import json
from datetime import datetime, timezone

def download_attendances_data() -> json[list[dict]]:
    """
    Send a get request to the mobilize API's Attendances endpoint and retrieves all data from attendances endpoint
    """
    base_url = "https://api.mobilize.us/v1/"    
    endpoint = "attendances"
    headers = {"Authorization": "Bearer {}".format(os.environ.get("MOBILIZE_API_KEY"))}

    response = requests.get(base_url + endpoint, headers=headers)

    result = response.json

    if result["error"]:
        logging.error(f"Failed to retrieve attendances data with error: {result["error"]}")
    
    return result

def extract_event_data(row: dict) -> dict:
    """Takes a row of Mobilize API data and returns a dict of specific key:value pairs for that event.
    
    Args:
        row: a dict of events from the Mobilize API json response
    """
    event = {
        key: value
        for key, value in row["event"].items()
        if key
        in (
            "created_date",
            "modified_date",
            "id",
            "title",
            "event_type",
            "summary",
            "description",
        )
    }
    return event


def save_data_to_gcs(data: list[dict], filepath: str) -> str:
    """
    Takes a json of event data, transforms data into rows, and saves to google cloud storage with the given filepath.

    Args:
        data: a list of attendance objects from the Mobilize attendances API
        filepath: the filepath to write to in GCS, relative to 'gs://mobilize/{filepath}'
    """

    with smart_open.open(f'gs://mobilize/{filepath}', 'wb') as fout:
        for row in data:
            try:
                fout.write(extract_event_data(row))
            except Exception as e:
                logging.error(f"Error loading row {row}, with error {e}")

def load_events_to_bigquery(filepath: str):
    """
    Stream events data from a filepath in google cloud storage into bigquery events table
    
    Args:
        filepath: the filepath to read from in GCS, relative to 'gs://mobilize/{filepath}'
    """
    client = bigquery.Client()
    table = client.get_table("wfp-data-project.mobilize.events")

    # stream from GCS
    for event in smart_open(f'gs://mobilize/{filepath}'):
        try:
            client.insert_rows(table, [event])
        except Exception as e:
            logging.error(f"Error loading row into bigquery. Row: {event}")


timestamp = datetime.now(timezone.utc)

response_json = download_attendances_data()
data = response_json["data"]

# Only try loading data if the API returned any data.
if data:
    filepath = f"attendances/{timestamp}.json"

    data_csv = extract_event_data()

    save_data_to_gcs(data_csv, filepath)
    load_events_to_bigquery(filepath)

