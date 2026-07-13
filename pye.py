import streamlit as st
import pandas as pd
from openai import OpenAI
from supabase import create_client, Client
import base64
import json

# # 1. Premium Page Configuration
st.set_page_config(
    page_title="RX-Expire MVP Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# # 2. Initialize Session State Memory Loop
# This creates a local temporary database array so items stack up on screen
if "inventory" not in st.session_state:
    st.session_state.inventory = []

# Title and App Sub-headings
st.title("🛡️ RX-Expire MVP Dashboard")
st.markdown(
    "Scan medication labels to extract expiration dates and log inventory automatically.")

# Sidebar status tool
with st.sidebar:
    st.header("⚙️ System Status")
    # Grabs the new API key you just securely updated in your secrets.toml file
    openai_key = st.secrets.get("OPENAI_API_KEY", "")
    if openai_key:
        st.success("OpenAI Key: Loaded & Secure 🔐")
    else:
        st.error("OpenAI Key: Missing in secrets.toml ⚠️")

# # 3. User Interface: Camera and File Upload Layout
st.markdown("---")
st.subheader("📸 Label Scanner Panel")

# Gives the pharmacist the ability to flip between a laptop webcam or an upload box
use_live_camera = st.checkbox("Toggle Live Webcam Mode")

if use_live_camera:
    uploaded_image = st.camera_input(
        "Position the bottle label clearly inside the viewfinder frame")
else:
    uploaded_image = st.file_uploader(
        "Drop a snapshot file of the label here", type=["jpg", "jpeg", "png"])

# # 4. Processing Pipeline: OpenAI Vision Call
if uploaded_image is not None:
    st.image(uploaded_image, caption="Current Uploaded Target Label", width=320)

    if st.button("🔍 Run AI Vision Analysis"):
        with st.spinner("Analyzing text layout and extracting dates..."):
            try:
                # Convert the image file bytes to a base64 text string for the API call
                image_bytes = uploaded_image.getvalue()
                base64_image = base64.b64encode(image_bytes).decode("utf-8")

                # Fire up the OpenAI engine using your secure environment variable
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

                # Process the image label using the primary multimodality model
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Identify the main medication name and the expiration date on this label. Return the answer ONLY as a clean JSON object containing keys 'medication_name' and 'expiration_date'. Do not wrap the code block in markdown backticks."
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=250
                )

                # Parse out raw JSON text safely into Python data structures
                raw_json = response.choices[0].message.content.strip()
                parsed_data = json.loads(raw_json)

                # Store the extracted items inside temporary variables
                st.session_state["temp_med"] = parsed_data.get(
                    "medication_name", "Unknown Label")
                st.session_state["temp_exp"] = parsed_data.get(
                    "expiration_date", "YYYY-MM-DD")
                st.success("Extraction Completed Successfully!")

            except Exception as error_msg:
                st.error(f"System connection failure: {error_msg}")
                # Fallback data simulation so you can continue testing layouts if API limits hit
                st.session_state["temp_med"] = "Fallback Sample Med 500mg"
                st.session_state["temp_exp"] = "2028-12-31"

# # 5. Data Adjustments & Verification UI
if "temp_med" in st.session_state:
    st.markdown("---")
    st.subheader("🎯 Pharmacist Verification Review")
    st.info(
        "Verify or adjust details manually before pushing data to the inventory logs.")

    col1, col2 = st.columns(2)
    with col1:
        confirmed_med = st.text_input(
            "Verified Med Title:", value=st.session_state["temp_med"])
    with col2:
        confirmed_exp = st.text_input(
            "Verified Expiration String:", value=st.session_state["temp_exp"])

    # Append the review row directly to the running tracking list when triggered
    if st.button("📥 Commit Entry to Inventory Log"):
        st.session_state.inventory.append({
            "Medication Name": confirmed_med,
            "Expiration Date": confirmed_exp,
            "Verification Check": "Verified ✅"
        })
        st.toast(f"Logged {confirmed_med} successfully!")

# # 6. Dynamic Visual Live Inventory Grid Display
if st.session_state.inventory:
    st.markdown("---")
    st.subheader("📋 Active Inventory Log Batch")

    # Render the array list structure into a visual interactive table frame
    inventory_dataframe = pd.DataFrame(st.session_state.inventory)
    st.dataframe(inventory_dataframe, use_container_width=True)

    # Allow resetting the current working batch session array cleanly
    if st.button("🗑️ Purge Current Batch"):
        st.session_state.inventory = []
        st.rerun()
