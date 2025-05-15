#!/usr/bin/env python3

import pandas as pd
from datetime import datetime, date, timedelta
import mysql.connector
import glob
import numpy as np
from dateutil import parser
from dotenv import load_dotenv
import re
import os
import json
import streamlit as st
import sys


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)

# counter for duplicate / records that already exists
counter = 0
# yesterday = date.today() - timedelta(days=1)
# date_str = yesterday.strftime("%m/%d/%Y")
global date_str 
def get_db_connection():
    load_dotenv(resource_path('.env'))
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        port=int(os.getenv("MYSQL_PORT")),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )
    return conn

def convert_to_csv(file_path):
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext == ".csv":
        print(f"Skipped CSV: {file_path}")
        return file_path  # Already CSV, return path as-is

    elif ext in [".xls", ".xlsx"]:
        df = pd.read_excel(file_path)
        csv_path = file_path.rsplit(".", 1)[0] + ".csv"
        df.to_csv(csv_path, index=False)
        print(f"Converted to CSV: {csv_path}")
        os.remove(file_path)  # Remove the original file
        return csv_path

    else:
        print(f"Unsupported file type: {file_path}")
        return None

def clean_offset(offset):
    if not offset:
        return None
    offset = str(offset).strip()
    
    # Check for format like +05:30 or -04:00
    match = re.match(r'^([+-]?)(\d{1,2}):(\d{2})$', offset)
    if match:
        sign, hours, minutes = match.groups()
        total = int(hours) + int(minutes) / 60
        return str(total if sign != '-' else -total)
    
    # If it's a plain float string like "5.5", return it as is
    try:
        return str(float(offset))
    except:
        return None
    
# Function to combine date and time
def combine_datetime(time_str):
    global date_str
    try:
        # Combine yesterday's date with the time and convert it to datetime
        return datetime.strptime(f"{date_str} {time_str.strip()}", "%m/%d/%Y %H:%M")
    except Exception:
        return pd.NaT  # Return NaT (Not a Time) for invalid time values
    
def record_exists(employee_id, punch_in_utc_time):
    conn = get_db_connection()
    cursor = conn.cursor() 
    query = """
    SELECT COUNT(*) FROM ohrm_attendance_record
    WHERE employee_id = %s AND DATE(punch_in_utc_time) = %s
    """
    cursor.execute(query, (employee_id, str(punch_in_utc_time).split(' ')[0]))
    return cursor.fetchone()[0] > 0

def insert_data_to_db(df):
    conn = get_db_connection()
    cursor = conn.cursor()
    global counter 
    for row in df.itertuples(index=False):
        try:
            print(f"Processing row: {row}")
            punch_in_utc_time =  row.punch_in_utc_time
            punch_in_user_time =  row.punch_in_user_time
            punch_out_utc_time =  row.punch_out_utc_time
            punch_out_user_time = row.punch_out_user_time
            # Clean offset as float string
            punch_in_offset = clean_offset(row.punch_in_time_offset)
            punch_out_offset = clean_offset(row.punch_out_time_offset)

            # Default state and timezone
            state = row.state if not pd.isna(row.state) else None
            punch_in_tz = row.punch_in_timezone_name if not pd.isna(row.punch_in_timezone_name) else "Asia/Kolkata"
            punch_out_tz = row.punch_out_timezone_name if not pd.isna(row.punch_out_timezone_name) else "Asia/Kolkata"

            # Check if the record already exists
            if not record_exists(row.employee_id, punch_in_utc_time):
                cursor.execute("""
                    INSERT INTO ohrm_attendance_record (
                        employee_id,
                        punch_in_utc_time,
                        punch_in_note,
                        punch_in_time_offset,
                        punch_in_user_time,
                        punch_out_utc_time,
                        punch_out_note,
                        punch_out_time_offset,
                        punch_out_user_time,
                        state,
                        punch_in_timezone_name,
                        punch_out_timezone_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    int(row.employee_id),
                    punch_in_utc_time,
                    row.punch_in_note if not pd.isna(row.punch_in_note) else None,
                    punch_in_offset,
                    punch_in_user_time,
                    punch_out_utc_time if not pd.isna(punch_out_utc_time) else None,
                    row.punch_out_note if not pd.isna(row.punch_out_note) else None,
                    punch_out_offset,
                    punch_out_user_time,
                    state,
                    punch_in_tz,
                    punch_out_tz
                ))
            else:
                counter += 1
                print(f"Record already exists for employee_id {row.employee_id} on {str(punch_in_utc_time).split(' ')[0]}")
            print(" {count} records already exists in the database.".format(count=counter))
            
        except Exception as e:
            print(f"❌ Error inserting row {row}: {e}")   
    conn.commit()
    conn.close()
    print("✅ All attendance data inserted successfully ")

def process_csv(file_path):

    global date_str
    # Extract date from file name using regex
    match = re.search(r'(\d{2}\.\d{2}\.\d{4})', file_path)
    if match:
        date_str = match.group(1)  # '06.06.2025'
    else:
        raise ValueError("Date not found in file name")
    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
    date_str = date_obj.strftime("%m/%d/%Y")  
    #date_str = date_str.strftime("%m/%d/%Y")
    df = pd.read_csv(file_path)
    # Drop completely empty columns and rows
    df_cleaned = df.dropna(axis=1, how='all').dropna(axis=0, how='all')
    # Remove the first 5 rows
    df_cleaned = df_cleaned.iloc[5:]
    # Keep rows where first column is numeric
    df_cleaned = df_cleaned[pd.to_numeric(df_cleaned.iloc[:, 0], errors='coerce').notna()]
    # Remove rows with unwanted first values
    df_cleaned = df_cleaned[~df_cleaned.iloc[:, 0].isin(['Department', 'SNo'])]
    # Drop empty columns again if needed
    df_cleaned = df_cleaned.dropna(axis=1, how='all')
    # Rename columns
    new_columns = ['SNo', 'E. Code', 'Name', 'Shift', 'InTime', 'OutTime', 'Work Dur.', 'OT', 'Tot. Dur.', 'Status']
    # print(df_cleaned.columns)
    df_cleaned.columns = new_columns
    # Reset 'SNo' as auto-increment
    df_cleaned['SNo'] = range(1, len(df_cleaned) + 1)
    # Convert 'InTime' and 'OutTime' to full datetime
    df_cleaned['punch_in_user_time'] = df_cleaned['InTime'].apply(combine_datetime)
    df_cleaned['punch_out_user_time'] = df_cleaned['OutTime'].apply(combine_datetime)

    mapping_file = resource_path('data/mapping.json')
    #Load the staff mapping JSON file
    with open(mapping_file, 'r') as f:
        staff_mapping = json.load(f)

    staff_no_to_emp_number = {
        int(float(staff_no)): details["employee_number"]
        for staff_no, details in staff_mapping.items()
    }

    # Ensure E. Code is integer
    df_cleaned['E. Code'] = df_cleaned['E. Code'].astype(float).astype(int)
    # Map emp_number using cleaned E. Code
    df_cleaned['emp_number'] = df_cleaned['E. Code'].map(staff_no_to_emp_number)

    
    # Remove rows where emp_number is NaN (ignore records without a valid mapping)
    df_cleaned = df_cleaned[df_cleaned['emp_number'].notna()]
    # Ensure emp_number is an integer (if possible) and handle NaNs
    df_cleaned['emp_number'] = pd.to_numeric(df_cleaned['emp_number'], errors='coerce').fillna(-1).astype(int)
    df_cleaned = df_cleaned.rename(columns={'emp_number': 'employee_id'})
    df_cleaned = df_cleaned.drop(['SNo','E. Code','Shift', 'InTime', 'OutTime', 'Status','Work Dur.', 'OT', 'Tot. Dur.'], axis=1)
    #print(df.head(5))
    # Get list of column names
    cols = list(df_cleaned.columns)
    df_cleaned = df_cleaned[[cols[-1]] + cols[:-1]]
    df_cleaned['punch_in_time_offset'] = 5.5
    df_cleaned['punch_out_time_offset'] = 5.5
    df_cleaned['punch_in_note'] = None
    df_cleaned['punch_out_note'] = None
    df_cleaned['punch_in_timezone_name'] = 'Asia/Kolkata'
    df_cleaned['punch_out_timezone_name'] = 'Asia/Kolkata'
    df_cleaned['state'] = np.where(
        df_cleaned['punch_in_user_time'].notna() & df_cleaned['punch_out_user_time'].notna(),
        'PUNCHED OUT',
        np.where(
            df_cleaned['punch_in_user_time'].notna() & df_cleaned['punch_out_user_time'].isna(),
            'PUNCHED OUT',
            None
        )
    )
    # Add punch_in_utc_time and punch_out_utc_time columns
    df_cleaned['punch_in_utc_time'] = df_cleaned['punch_in_user_time'] - pd.to_timedelta(df_cleaned['punch_in_time_offset'], unit='h')
    df_cleaned['punch_out_utc_time'] = df_cleaned['punch_out_user_time'] - pd.to_timedelta(df_cleaned['punch_out_time_offset'], unit='h')
    # Reorder columns
    df_cleaned = df_cleaned[
        [
            'employee_id',
            'Name',
            'punch_in_utc_time',
            'punch_in_note',
            'punch_in_time_offset',
            'punch_in_user_time',
            'punch_out_utc_time',
            'punch_out_note',
            'punch_out_time_offset',
            'punch_out_user_time',
            'state',
            'punch_in_timezone_name',
            'punch_out_timezone_name'
        ]
    ]
    #set default value "yesterdays date and 19:00:00 " to punchout user times and  punchout utc time if punchin values are present and punch out values are not:
    df_cleaned.loc[
        df_cleaned['punch_in_user_time'].notna() & df_cleaned['punch_out_user_time'].isna(),
        'punch_out_user_time'
    ] = pd.to_datetime(f"{date_str} 19:00:00")
    df_cleaned.loc[
        df_cleaned['punch_in_utc_time'].notna() & df_cleaned['punch_out_utc_time'].isna(),
        'punch_out_utc_time'
    ] = pd.to_datetime(f"{date_str} 19:00:00") - pd.to_timedelta(df_cleaned['punch_out_time_offset'], unit='h')
    df_cleaned = df_cleaned[~df_cleaned['punch_in_user_time'].isnull() & (df_cleaned['punch_in_user_time'].astype(str).str.strip() != '')]
    #cleaned_csv_path = file_path.rsplit(".", 1)[0] + "_cleaned.csv"
    #df_cleaned.to_csv( cleaned_csv_path, index=False)
    insert_data_to_db(df_cleaned)
    
