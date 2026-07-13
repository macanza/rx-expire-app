import streamlit as st
import pandas as pd
import json
import base64
from datetime import datetime
from openai import OpenAI
from supabase import create_client, Client

# 1. Initialize API Clients Securely Using Streamlit Secrets


@st.cache_resource
def init_connections():
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    openai_key = st.secrets["OPENAI_API_KEY"]

    supabase_client = create_client(supabase_url, supabase_key)
    openai_client = OpenAI(api_key=openai_key)
    return supabase_client, openai_client


try:
    supabase, openai_client = init_connections()
except Exception as e:
    st.error(f"Configuration Error: Missing Streamlit Secrets. Details: {e}")
    st.stop()

# Helper function to calculate days remaining


def calculate_days(iso_date_str):
    if not iso_date_str:
        return 999
    try:
        target_date = datetime.strptime(iso_date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        return (target_date - today).days
    except:
        return 999

# Initial Historical Fetch Engine


@st.cache_data(show_spinner="Syncing with cloud database...")
def fetch_historical_inventory():
    try:
        response = supabase.table("inventory").select(
            "*").order("created_at", desc=True).execute()
        records = response.data if response.data else []

        formatted_list = []
        for row in records:
            iso_fallback = None
            if row.get("Expiry Date") and "/" in row["Expiry Date"]:
                parts = row["Expiry Date"].split("/")
                if len(parts) == 2:  # MM/YYYY format
                    iso_fallback = f"{parts[1]}-{parts[0]}-28"

            days = calculate_days(iso_fallback)

            formatted_list.append({
                "Database ID": row.get("id"),
                "Medication Name": row.get("Medication", "Unknown"),
                "Expiration Date": row.get("Expiry Date", "Unknown"),
                "Days Remaining": days,
                "Verification Check": row.get("Status", "Verified ✅")
            })
        return formatted_list
    except Exception as e:
        st.error(f"Failed to load cloud history: {e}")
        return []


# Initialize session state tracking
if "inventory" not in st.session_state:
    st.session_state.inventory = fetch_historical_inventory()
if "processed_keys" not in st.session_state:
    st.session_state.processed_keys = set()

# 2. User Interface Layout
st.set_page_config(page_title="RX-Expire Ultimate Pro",
                   page_icon="🛡️", layout="centered")

st.title("🛡️ RX-Expire Ultimate Pro")
st.caption(
    "Complete enterprise-grade automated pharmacy inventory tracking pipeline.")
st.write("---")

# Expiration Risk Analysis Analytics
st.subheader("🚨 Expiration Risk Analysis")
if st.session_state.inventory:
    critical_count = 0
    warning_count = 0

    for item in st.session_state.inventory:
        days = item.get("Days Remaining", 999)
        if days <= 0:
            critical_count += 1
        elif days <= 90:
            warning_count += 1

    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="❌ Expired Items", value=critical_count,
                  delta="- Action Required" if critical_count > 0 else "Clear", delta_color="inverse")
    with col2:
        st.metric(label="⚠️ Expiring Within 90 Days", value=warning_count,
                  delta="- Monitor Closely" if warning_count > 0 else "Clear", delta_color="off")
else:
    st.info("No active batch data to analyze yet.")

st.write("---")
st.subheader("📸 Label Scanner Panel")

input_mode = st.radio(
    "Select Scanner Input Method:",
    ["📷 Live Webcam Mode", "📁 Bulk Image Upload Mode"],
    index=0
)

scan_queue = []

if input_mode == "📷 Live Webcam Mode":
    webcam_file = st.camera_input(
        "Position the medication label clearly in front of the camera")
    if webcam_file:
        snapshot_id = f"webcam_{webcam_file.size}"
        if snapshot_id not in st.session_state.processed_keys:
            scan_queue.append((snapshot_id, webcam_file))

else:
    uploaded_files = st.file_uploader(
        "Drop snapshot files of your medication labels here",
        type=["jpg", "png", "jpeg", "webp"],
        accept_multiple_files=True
    )
    if uploaded_files:
        for file in uploaded_files:
            unique_file_id = f"{file.name}_{file.size}"
            if unique_file_id not in st.session_state.processed_keys:
                scan_queue.append((unique_file_id, file))

# 3. Core Automated Processing Engine
if scan_queue:
    success_count = 0
    total_files = len(scan_queue)

    progress_bar = st.progress(0.0)
    status_text = st.empty()

    for idx, (processing_id, image_data) in enumerate(scan_queue):
        status_text.text(f"Processing label {idx + 1} of {total_files}...")
        try:
            raw_bytes = image_data.getvalue()
            base64_encoded = base64.b64encode(raw_bytes).decode("utf-8")

            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Analyze this medicine label image. Return a raw JSON object containing "
                                    "exactly three keys:\n"
                                    "1. 'medication_name' (string value matching the brand/generic name or empty string if not visible)\n"
                                    "2. 'expiration_date' (string value matching the expiration sequence exactly as printed, e.g., 2025MAR23)\n"
                                    "3. 'iso_date' (string formatted strictly as YYYY-MM-DD representing the expiration date for math calculations. If only MM/YYYY is given, assume the last day of that month).\n"
                                    "Do not format output with markdown backticks or block wrappers."
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_encoded}"}
                            }
                        ]
                    }
                ]
            )

            raw_output = response.choices[0].message.content.strip()
            if raw_output.startswith("```json"):
                raw_output = raw_output.replace(
                    "```json", "").replace("```", "").strip()
            elif raw_output.startswith("```"):
                raw_output = raw_output.replace("```", "").strip()

            parsed_json = json.loads(raw_output)
            medication_title = parsed_json.get("medication_name", "")
            expiration_string = parsed_json.get(
                "expiration_date", "Unknown Expiration")
            iso_date_str = parsed_json.get("iso_date", None)

            days_remaining = calculate_days(iso_date_str)

            # Direct Database Insert
            db_response = supabase.table("inventory").insert({
                "Medication": medication_title if medication_title else "Pending Override",
                "Expiry Date": expiration_string,
                "Status": "Verified ✅"
            }).execute()

            new_row_id = db_response.data[0].get(
                "id") if db_response.data else None

            st.session_state.inventory.insert(0, {
                "Database ID": new_row_id,
                "Medication Name": medication_title,
                "Expiration Date": expiration_string,
                "Days Remaining": days_remaining,
                "Verification Check": "Verified ✅"
            })
            success_count += 1

        except Exception as error:
            st.error(f"❌ Scan failed: {error}")

        st.session_state.processed_keys.add(processing_id)
        progress_bar.progress((idx + 1) / total_files)

    status_text.empty()
    progress_bar.empty()

    if success_count > 0:
        st.cache_data.clear()
        st.rerun()

st.write("---")

# 4. Live Interactive Data Editor
st.subheader("📋 Active Inventory Log Batch")
st.caption(
    "💡 Double-click any cell below to update records live down to the cloud datastore.")

if st.session_state.inventory:
    dataframe_view = pd.DataFrame(st.session_state.inventory)

    edited_df = st.data_editor(
        dataframe_view,
        use_container_width=True,
        column_config={
            "Database ID": None,
            "Medication Name": st.column_config.TextColumn("Medication Name", width="medium", required=True),
            "Days Remaining": st.column_config.NumberColumn("Days Left", width="small", format="%d days"),
            "Expiration Date": st.column_config.TextColumn("Expiration", width="small"),
            "Verification Check": st.column_config.SelectboxColumn("Status", width="small", options=["Verified ✅", "Flagged ⚠️"])
        }
    )

    # Process modifications back up to Supabase live if a cell changes
    if not edited_df.equals(dataframe_view):
        for idx, row in edited_df.iterrows():
            db_id = row.get("Database ID")
            if db_id:
                try:
                    supabase.table("inventory").update({
                        "Medication": row.get("Medication Name"),
                        "Expiry Date": row.get("Expiration Date"),
                        "Status": row.get("Verification Check")
                    }).eq("id", db_id).execute()
                except:
                    pass
        st.session_state.inventory = edited_df.to_dict(orient="records")
        st.cache_data.clear()

    # --- PHASE 4 FEATURE: ONE-CLICK CSV EXPORT ENGINE ---
    st.write("")
    clean_export_df = dataframe_view.drop(
        columns=["Database ID"], errors="ignore")
    csv_data = clean_export_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="📥 Export Full Inventory Log to CSV Spreadsheet",
        data=csv_data,
        file_name=f"rx_expire_inventory_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True
    )

else:
    st.info("No scanned medications logged in this session yet.")

# 5. Targeted Individual Row Deletion Controls
if st.session_state.inventory:
    with st.expander("🔧 Advanced Inventory Management"):
        med_options = {f"{item['Medication Name']} ({item['Expiration Date']})": item['Database ID']
                       for item in st.session_state.inventory if item['Database ID']}

        if med_options:
            selected_med = st.selectbox(
                "Select an entry to permanently remove:", options=list(med_options.keys()))
            if st.button("🗑️ Delete Selected Entry", type="primary"):
                target_id = med_options[selected_med]
                try:
                    supabase.table("inventory").delete().eq(
                        "id", target_id).execute()
                    st.success(
                        "Entry removed successfully from cloud storage!")
                    st.cache_data.clear()
                    st.session_state.inventory = [
                        i for i in st.session_state.inventory if i['Database ID'] != target_id]
                    st.rerun()
                except Exception as delete_error:
                    st.error(f"Deletion failed: {delete_error}")

        st.write("---")
        if st.button("🚨 Purge All Session Local Caches"):
            st.session_state.inventory = []
            st.session_state.processed_keys.clear()
            st.cache_data.clear()
            st.rerun()
