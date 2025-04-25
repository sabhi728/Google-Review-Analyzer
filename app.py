import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI
from dotenv import load_dotenv
import os
import tempfile
import time
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime, timedelta


load_dotenv()

# Configure OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def analyze_sentiment(text):
    """Analyze sentiment using OpenAI API with retry logic"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a sentiment analysis expert. Analyze the following review and respond with ONLY one word: 'Positive', 'Negative', or 'Neutral'."},
                {"role": "user", "content": text}
            ],
            temperature=0.3,
            max_tokens=10
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        if "rate_limit" in str(e).lower():
            st.warning("Rate limit reached. Waiting before retrying...")
            time.sleep(5)
            raise
        st.error(f"Error analyzing sentiment: {str(e)}")
        return "Error"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def classify_review(text):
    """Classify review based on service, location, or product"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Classify this review into categories. Respond with ONLY the category name: 'Service', 'Location', 'Product', or 'Other'."},
                {"role": "user", "content": text}
            ],
            temperature=0.3,
            max_tokens=10
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"Error classifying review: {str(e)}")
        return "Other"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def detect_complaints(text):
    """Detect and flag customer complaints"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Analyze this review for complaints. Respond with 'Yes' if there are complaints, 'No' if there are none."},
                {"role": "user", "content": text}
            ],
            temperature=0.3,
            max_tokens=10
        )
        return response.choices[0].message.content.strip() == "Yes"
    except Exception as e:
        st.error(f"Error detecting complaints: {str(e)}")
        return False

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_weekly_summary(reviews_df):
    """Generate a detailed weekly summary report"""
    try:
        reviews_text = " ".join(reviews_df['Review Text'].astype(str))
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """Generate a detailed weekly summary report including:
                1. Overall sentiment distribution
                2. Key positive and negative themes
                3. Specific customer complaints
                4. Action items for improvement
                Format the response in clear sections with bullet points."""},
                {"role": "user", "content": reviews_text}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"Error generating weekly summary: {str(e)}")
        return "Error generating weekly summary"

def main():
    st.set_page_config(page_title="Google Reviews Analyzer", layout="wide")
    st.title("Google Reviews Sentiment Analysis")
    
    # File upload
    uploaded_file = st.file_uploader("Upload your Google Reviews Excel file", type=['csv', 'xlsx'])
    
    if uploaded_file is not None:
        # Read the file
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        
        # Check if 'Review Text' column exists
        if 'Review Text' not in df.columns:
            st.error("Please ensure your file contains a 'Review Text' column")
            return
        
        # Add date column if not present
        if 'Date' not in df.columns:
            df['Date'] = datetime.now().date()
        
        # Add batch processing
        batch_size = 5
        total_reviews = len(df)
        
        # Analyze sentiment for each review
        if st.button("Analyze Reviews"):
            with st.spinner("Analyzing reviews..."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i in range(0, total_reviews, batch_size):
                    batch = df.iloc[i:i+batch_size]
                    for idx, row in batch.iterrows():
                        df.at[idx, 'Sentiment'] = analyze_sentiment(row['Review Text'])
                        df.at[idx, 'Category'] = classify_review(row['Review Text'])
                        df.at[idx, 'Has_Complaint'] = detect_complaints(row['Review Text'])
                        progress = (idx + 1) / total_reviews
                        progress_bar.progress(progress)
                        status_text.text(f"Processing review {idx + 1} of {total_reviews}")
                        time.sleep(0.5)
                
                # Display results
                st.subheader("Sentiment Analysis Results")
                
                # Create sentiment pie chart
                sentiment_counts = df['Sentiment'].value_counts()
                fig_sentiment = px.pie(values=sentiment_counts.values, 
                                    names=sentiment_counts.index,
                                    title="Sentiment Distribution")
                st.plotly_chart(fig_sentiment)
                
                # Create category pie chart
                category_counts = df['Category'].value_counts()
                fig_category = px.pie(values=category_counts.values,
                                    names=category_counts.index,
                                    title="Review Categories")
                st.plotly_chart(fig_category)
                
                # Display complaints
                complaints = df[df['Has_Complaint'] == True]
                if not complaints.empty:
                    st.subheader("Customer Complaints")
                    st.dataframe(complaints[['Review Text', 'Sentiment', 'Category']])
                
                # Generate and display weekly summary
                st.subheader("Weekly Summary Report")
                weekly_summary = generate_weekly_summary(df)
                st.write(weekly_summary)
                
                # Display full data table
                st.subheader("Analyzed Reviews")
                st.dataframe(df)
                
                # Export options
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Export Full Analysis"):
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
                            df.to_csv(tmp.name, index=False)
                            with open(tmp.name, 'rb') as f:
                                st.download_button(
                                    label="Download Full Analysis CSV",
                                    data=f,
                                    file_name="analyzed_reviews.csv",
                                    mime="text/csv"
                                )
                with col2:
                    if st.button("Export Weekly Report"):
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tmp:
                            with open(tmp.name, 'w') as f:
                                f.write(weekly_summary)
                            with open(tmp.name, 'rb') as f:
                                st.download_button(
                                    label="Download Weekly Report",
                                    data=f,
                                    file_name="weekly_report.txt",
                                    mime="text/plain"
                                )

if __name__ == "__main__":
    main() 