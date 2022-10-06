import json
import csv
import datetime
import os

from psycopg2 import Timestamp

attendances = {}
# Open attendances JSON file
with open('data/attendances.json') as f:
  attendances = json.loads(f.read())

print("processed", len(attendances), "attendances")

# add your code for processing this data here! 


# defining helper functions


# function to convert unix timestamps to date strings
def unix_to_date_string(unix_date):
  if unix_date:
    return datetime.datetime.fromtimestamp(int(unix_date)).strftime('%Y-%m-%d %H:%M:%S')
  else:
    return None


# function to extract a person dictionary from an attendance record and flatten it
def get_person(record):
  # extracting "person" dictionary from the record
  person_dict = record['person']

  # dropping the 'id' column since we already have 'person_id'
  del person_dict['id']

  # converting date columns from unix to timestamp strings
  for date_col in ['created_date', 'modified_date','blocked_date']:
    person_dict[date_col] = unix_to_date_string(person_dict[date_col])

  # extracting values from nested dictionaries
  for dict_col in ['email_addresses','phone_numbers','postal_addresses']:
    col_list = person_dict[dict_col]
    for item in col_list:
      if item['primary']:
        new_col = [val for val in item.keys() if val != 'primary'][0]
        person_dict[new_col] = item[new_col]
    del person_dict[dict_col]

  # returning the person_id and the simplified dictionary
  return person_dict['person_id'], person_dict


# function to extract an event dictionary from an attendance record and flatten it
def get_event(record):
  # extracting "event" dictionary from the record
  event_dict = record['event']

  # renaming the id column for ease of joins later
  event_dict['event_id'] = event_dict['id']
  del event_dict['id']

  # replacing nested sponsor dictionary with a sponsor id (we'd hopefully have a sponsors table with the other info!)
  if event_dict['sponsor']:
    event_dict['sponsor_id'] = event_dict['sponsor']['id']
  else: 
    event_dict['sponsor_id'] = None
  del event_dict['sponsor']
  
  # replacing nested location dictionary with the venue (we'd hopefully have a venue table with the other info!)
  try:
    event_dict['venue'] = event_dict['location']['venue']
  except: 
    event_dict['venue'] = None
  del event_dict['location']

  # converting the nested contact dictionary to 4 separate columns and then deleting it
  for item in ['name','email_address','phone_number']:
    try:
      event_dict[f'contact_{item}'] = event_dict['contact'][item]
    except:
      event_dict[f'contact_{item}'] = None

  try:
    event_dict['owner_user_id'] = event_dict['contact']['owner_user_id']
  except: 
    event_dict['owner_user_id'] = None

  del event_dict['contact']

  # converting date columns from unix to timestamp strings
  for date_col in ['created_date', 'modified_date']:
    event_dict[date_col] = unix_to_date_string(event_dict[date_col])

  # returning the event_id and the simplified dictionary
  return event_dict['event_id'], event_dict


# function to extract a timeslot dictionary from an attendance record and flatten it
def get_timeslot(record):
  # extracting "event" dictionary from the record
  timeslot_dict = record['timeslot']

  # renaming the id column for ease of joins later
  timeslot_dict['timeslot_id'] = timeslot_dict['id']
  del timeslot_dict['id']

  # converting date columns from unix to timestamp strings
  for date_col in ['start_date', 'end_date']:
    timeslot_dict[date_col] = unix_to_date_string(timeslot_dict[date_col])

  # returning the timeslot_id and the simplified dictionary
  return timeslot_dict['timeslot_id'], timeslot_dict


# function to flatten an attendance record once we've extracted what we need from it
def flatten_attendance_record(record):

  new_record = record

  # renaming the id column for ease of joins later
  new_record['attendance_id'] = new_record['id']
  del new_record['id']

  # converting date columns from unix to timestamp strings
  for date_col in ['created_date','modified_date']:
    new_record[date_col] = unix_to_date_string(new_record[date_col])

  # since we extracted all the data from the nested dictionaries, we can flatten them to just their unique id now
  for id_col in ['sponsor','timeslot','person','event']:
    try:
      new_record[f'{id_col}_id'] = new_record[id_col]['id']
    except:
      new_record[f'{id_col}_id'] = None
    del new_record[id_col]

  # flattening referrer to utm_source  --  this might not be the correct approach but since there was no referrer_id...
  new_record['utm_source'] = new_record['referrer']['utm_source']
  del new_record['referrer']

  # flattening custom fields into a string for downstream transformation/extraction
  new_record['custom_signup_field_values'] = str(new_record['custom_signup_field_values'])[1:-1]

  # returning the attendance_id and the flattened record
  return new_record['attendance_id'], new_record


# function to process a list of attendance records and store the new flat data in lists of dictionaries
def process_records(list_of_records):
  # creating dictionaries to store records in -- this will eliminate any duplicates since each id will be unique, unlike lists!
  people = {}
  events = {}
  timeslots = {}
  flat_attendances = {}

  print(f'Starting to process {len(list_of_records)} records')

  # looping through records and using helper functions to extract people, events, and timeslots to store in our dictionaries
  for i, record in enumerate(list_of_records):
    # extracting person dict
    person_id, person_row = get_person(record)
    people[person_id] = person_row

    # extracting event dict
    event_id, event_row = get_event(record)
    events[event_id] = event_row

    # extracting timeslot dict
    timeslot_id, timeslot_row = get_timeslot(record)
    timeslots[timeslot_id] = timeslot_row

    # cleaning up the attendance record
    attendance_id, attendance_row = flatten_attendance_record(record)
    flat_attendances[attendance_id] = attendance_row

    if i > 0 and i % 100 == 0:
      print(f'Processed {i} of out {len(list_of_records)} records')

  print(f'Converted {len(list_of_records)} records into {len(people)} people, {len(events)} events, and {len(timeslots)} timeslots')

  # now that we have unique records, we don't need the id keys! we just want the dictionaries so we can convert to a CSV
  return list(people.values()), list(events.values()), list(timeslots.values()), list(flat_attendances.values())


# function to export our table equivalents to CSV
def list_of_dicts_to_csv(list_of_dicts,csv_name):

  with open(f'output/{csv_name}.csv', 'w', encoding='utf8', newline='') as output_file:
      writer = csv.DictWriter(output_file, 
                          fieldnames=list_of_dicts[0].keys(),

                        )
      writer.writeheader()
      writer.writerows(list_of_dicts)
  
  print(f'Successfully wrote {csv_name} to a CSV')
  

# defining main
def main():

  # processing the records into lists of dictionaries
  people, events, timeslots, flat_attendances = process_records(attendances)

  # converting each of those lists of dictionaries into CSVs
  for list_of_dicts, file_name in zip([people, events, timeslots, flat_attendances], ['people','events','timeslots', 'flat_attendances']):
    
    # deleting existing files if they exist
    try:
      os.remove(f'output/{file_name}.csv')
      print(f'Deleted {file_name}.csv')
    except:
      pass

    # writing to CSV
    list_of_dicts_to_csv(list_of_dicts, file_name)

# run main
if __name__ == '__main__':
    main()

# see https://github.com/mobilizeamerica/api#attendances for data model documentation