import streamlit as st
import os
import glob
import sys
import pandas as pd
from datetime import date
import final as backend
import json

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)

# Process single or multiple files
def process_files(file_paths):
    for file_path in file_paths:
        converted_path = backend.convert_to_csv(file_path)
        if converted_path:
            backend.process_csv(converted_path)

# Extract attendance records for a given date
from datetime import datetime

def extract_records(date_str):
    conn = backend.get_db_connection()
    cursor = conn.cursor()
    query = """
    SELECT 
        CONCAT_WS(' ', e.emp_firstname, e.emp_middle_name, e.emp_lastname) AS full_name,
        e.employee_id as employee_id,
        e.emp_number as employee_number,
        a.punch_in_user_time,
        a.punch_out_user_time 
    FROM ohrm_attendance_record a
    JOIN hs_hr_employee e ON a.employee_id = e.emp_number
    WHERE DATE(a.punch_in_utc_time) = %s
    """
    cursor.execute(query, (date_str,))
    columns = [desc[0] for desc in cursor.description]
    records = cursor.fetchall()
    conn.close()

    df = pd.DataFrame(records, columns=columns)

    # Compute duration
    def calculate_duration(row):
        try:
            punch_in = pd.to_datetime(row['punch_in_user_time'])
            punch_out = pd.to_datetime(row['punch_out_user_time'])
            duration = punch_out - punch_in
            total_hours = duration.total_seconds() / 3600
            return f"{int(total_hours)}h {int((total_hours % 1) * 60)}m"
        except Exception:
            return "Invalid time"

    df["worked_duration"] = df.apply(calculate_duration, axis=1)
    return df

# Check for employees who didn't punch in using attendance records and staff mapping JSON


def check_for_punch_in(df, staff_mapping_file):
    try:
        # Load and parse the staff mapping JSON
        with open(staff_mapping_file, 'r') as f:
            raw_mapping = json.load(f)

        # Normalize staff mapping
        staff_mapping = {
            int(float(emp_id)): {
                'employee_number': entry['employee_number'],
                'full_name': entry['full_name']
            }
            for emp_id, entry in raw_mapping.items()
            if isinstance(entry, dict) and 'employee_number' in entry and 'full_name' in entry
        }

        # Ensure 'employee_number' in df is integer
        df['employee_number'] = pd.to_numeric(df['employee_number'], errors='coerce').dropna().astype(int)

        # Set of employees who punched in
        present_employee_numbers = set(df['employee_number'].unique())

        # All mapped employee numbers from the JSON
        mapped_employee_numbers = {v['employee_number'] for v in staff_mapping.values()}

        # Find who is missing
        missing_numbers = mapped_employee_numbers - present_employee_numbers

        # Track which employee_numbers have already been added
        seen_employee_numbers = set()

        # Prepare missing entries (deduplicated by employee_number)
        missing_data = []
        for emp_id, info in staff_mapping.items():
            emp_number = info['employee_number']
            if emp_number in missing_numbers and emp_number not in seen_employee_numbers:
                missing_data.append({
                    'employee_id': emp_id,
                    'employee_number': emp_number,
                    'full_name': info['full_name']
                })
                seen_employee_numbers.add(emp_number)

        return pd.DataFrame(missing_data)

    except Exception as e:
        print(f"Error processing staff mapping: {e}")
        return pd.DataFrame(columns=['employee_id', 'employee_number', 'full_name'])


# --- UI ---

st.title("Punch Sync & Attendance Viewer")

with st.sidebar:
    st.header("📁 File Processing")

    mode = st.radio("Select mode:", ["Upload single file", "Process folder"])

    if mode == "Upload single file":
        uploaded_file = st.file_uploader("Upload a file", type=["csv", "xlsx", "xls"])
        if uploaded_file:
            temp_path = os.path.join("temp", uploaded_file.name)
            os.makedirs("temp", exist_ok=True)
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            if st.button("Process File"):
                process_files([temp_path])
                st.success("File processed successfully.")

    elif mode == "Process folder":
        folder_path = st.text_input("Enter folder path (absolute or relative):", "data")
        if st.button("Process Folder"):
            if os.path.isdir(folder_path):
                all_files = glob.glob(os.path.join(folder_path, "*"))
                process_files(all_files)
                st.success("All files processed.")
            else:
                st.error("Invalid folder path.")

    st.markdown("---")
    st.header("📅 View Attendance")

    selected_date = st.date_input("Select a date", value=date.today())
    fetch = st.button("Fetch Records")

    st.markdown("---")
    st.header("🌴 Who's on Leave Today")

    leave_df = backend.who_is_in_leave()
    if not leave_df.empty:
        st.dataframe(leave_df)
        csv_leave = leave_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Leave List",
            data=csv_leave,
            file_name=f"leave_list_{date.today().isoformat()}.csv",
            mime="text/csv"
        )
    else:
        st.success("No one is on leave today.")
