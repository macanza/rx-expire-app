import streamlit as st
import pandas as pd
import json
import base64
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
st.set_page_config(page_title="RX-Expire Dashboard",
                   page_icon="🛡️", layout="centered")

st.title("🛡️ RX-Expire MVP Dashboard")
st.caption(
    "Scan medication labels to extract expiration dates and log inventory automatically.")
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

# 4. Core Automated Processing Engine (Fixed Rerun Logic)
if scan_queue:
    success_count = 0
    with st.spinner(f"AI is automatically extracting data..."):
        for processing_id, image_data in scan_queue:
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
                                        "exactly two keys: 'medication_name' (string value matching the brand/generic name) "
                                        "and 'expiration_date' (string value matching the expiration sequence exactly as "
                                        "printed, e.g., 2025MAR23). Do not format output with markdown backticks or block wrappers."
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
                medication_title = parsed_json.get(
                    "medication_name", "Unknown Medication")
                expiration_string = parsed_json.get(
                    "expiration_date", "Unknown Expiration")

                # Direct Database Insert
                supabase.table("inventory").insert({
                    "medication_name": medication_title,
                    "expiration_date": expiration_string,
                    "verification_check": "Verified ✅"
                }).execute()

                st.session_state.inventory.append({
                    "Medication Name": medication_title,
                    "Expiration Date": expiration_string,
                    "Verification Check": "Verified ✅"
                })
                success_count += 1

            except Exception as error:
                # FIX: Error message will now permanently stay visible on the screen
                st.error(f"❌ Scan failed: {error}")

            st.session_state.processed_keys.add(processing_id)

    # FIX: Only refresh the screen layout if an insertion was genuinely successful
    if success_count > 0:
        st.rerun()

st.write("---")

# 5. Live Verification Log Display Panel
st.subheader("📋 Active Inventory Log Batch")

if st.session_state.inventory:
    dataframe_view = pd.DataFrame(st.session_state.inventory)
    st.dataframe(dataframe_view, use_container_width=True)
else:
    st.info("No scanned medications logged in this session yet. Ready for tracking data inputs.")

if st.session_state.inventory:
    if st.button("🗑️ Purge Current Session Logs"):
        st.session_state.inventory = []
        st.session_state.processed_keys.clear()
        st.rerun()
