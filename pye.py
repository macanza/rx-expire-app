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

# 2. Setup Persistent Session States
if "inventory" not in st.session_state:
    st.session_state.inventory = []
if "processed_keys" not in st.session_state:
    st.session_state.processed_keys = set()

# 3. User Interface Layout
st.set_page_config(page_title="RX-Expire Pro Dashboard",
                   page_icon="🛡️", layout="centered")

st.title("🛡️ RX-Expire Pro Dashboard")
st.caption(
    "Automated inventory tracking, smart expiration analysis, and live database sync.")
st.write("---")

# --- FEATURE 1: SMART EXPIRATION ALERTS PANEL ---
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

# 4. Core Automated Processing Engine (With Bulk Upload Enhancements)
if scan_queue:
    success_count = 0
    total_files = len(scan_queue)

    # FEATURE 2: BULK UPLOAD PROGRESS TRACKING
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
                    ]
                )
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

            # Smart Date Math Engine
            days_remaining = 999
            if iso_date_str:
                try:
                    target_date = datetime.strptime(
                        iso_date_str, "%Y-%m-%d").date()
                    today = datetime.now().date()
                    days_remaining = (target_date - today).days
                except:
                    pass

            # Direct Database Insert
            supabase.table("inventory").insert({
                "Medication": medication_title if medication_title else "Pending Override",
                "Expiry Date": expiration_string,
                "Status": "Verified ✅"
            }).execute()

            st.session_state.inventory.append({
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
        st.rerun()

st.write("---")

# 5. FEATURE 3: LIVE INTERACTIVE DATA EDITOR (Manual Override Fallback)
st.subheader("📋 Active Inventory Log Batch")
st.caption("💡 Double-click any empty text cell below to manually add or edit medication details on the fly.")

if st.session_state.inventory:
    dataframe_view = pd.DataFrame(st.session_state.inventory)

    # Swapped from st.dataframe to st.data_editor to allow manual overrides live
    edited_df = st.data_editor(
        dataframe_view,
        use_container_width=True,
        column_config={
            "Days Remaining": st.column_config.NumberColumn("Days Left", format="%d days"),
            "Verification Check": st.column_config.SelectboxColumn("Status", options=["Verified ✅", "Flagged ⚠️"])
        }
    )

    # Sync visual alterations back into the persistent session tracking arrays
    st.session_state.inventory = edited_df.to_dict(orient="records")
else:
    st.info("No scanned medications logged in this session yet. Ready for tracking data inputs.")

if st.session_state.inventory:
    if st.button("🗑️ Purge Current Session Logs"):
        st.session_state.inventory = []
        st.session_state.processed_keys.clear()
        st.rerun()
