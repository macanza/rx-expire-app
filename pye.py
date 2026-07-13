import streamlit as st
import pandas as pd
from openai import OpenAI
from supabase import create_client, Client
import base64
import json

# 1. Premium Page Configuration
st.set_page_config(
    page_title="RX-Expire MVP Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Initialize Database & AI Clients safely from Secrets


@st.cache_resource
def init_connections():
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    openai_key = st.secrets["OPENAI_API_KEY"]

    supabase_client = create_client(supabase_url, supabase_key)
    openai_client = OpenAI(api_key=openai_key)

    return supabase_client, openai_client


supabase, openai_client = init_connections()

# Helper function to convert the camera image for OpenAI Vision


def encode_image_bytes(image_bytes):
    return base64.b64encode(image_bytes).decode("utf-8")


# 3. Main Dashboard UI Layout
st.title("📦 RX-Expire MVP Dashboard")
st.caption("Scan inventory to recover expiring manufacturer credits")

# Setup layout columns
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📷 Live Viewfinder")

    # Capture live image from the user's laptop camera
    img_file = st.camera_input(
        "Position the medication label clearly in the frame")

    if img_file is not None:
        st.info("Reading label contents... Processing AI analysis.")

        # 1. Convert image bytes to base64
        bytes_data = img_file.getvalue()
        base64_image = encode_image_bytes(bytes_data)

        # 2. Prompt OpenAI Vision to extract target data structures strictly
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Analyze this medication label image. Extract the following properties: "
                                    "1. 'Medication': The exact name of the drug. "
                                    "2. 'Manufacturer': The pharma company name. "
                                    "3. 'Expiry Date': The expiration date formatted strictly as YYYY-MM-DD. "
                                    "Return ONLY a clean JSON object with these keys: "
                                    "{'Medication': '...', 'Manufacturer': '...', 'Expiry Date': '...'}"
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ]
            )

            # Parse response text into a clean Python dictionary
            extracted_data = json.loads(response.choices[0].message.content)

            # Show the user what the AI found
            st.success(f"✅ Scanned Successfully!")
            st.write(extracted_data)

            # 3. Insert directly into Supabase Inventory Table (lowercase 'inventory')
            with st.spinner("Logging into database inventory..."):
                supabase.table("inventory").insert(extracted_data).execute()
                st.toast("Saved to database successfully!", icon="🔥")

        except Exception as e:
            st.error(f"Error extracting data: {e}")

with col2:
    st.subheader("📊 Current Inventory Tracking")

    # Pull current data rows straight from Supabase (lowercase 'inventory')
    try:
        res = supabase.table("inventory").select(
            "*").order("created_at", desc=True).execute()

        if res.data:
            df = pd.DataFrame(res.data)
            # Reorganize table viewing order nicely
            df_display = df[["id", "Medication",
                             "Manufacturer", "Expiry Date", "created_at"]]
            st.dataframe(df_display, use_container_width=True)

            # Simple metric cards for context
            st.metric(label="Total Items Logged", value=len(df))
        else:
            st.info("No records found in database yet. Ready for your first scan!")

    except Exception as e:
        st.error(f"Failed to fetch inventory rows: {e}")
