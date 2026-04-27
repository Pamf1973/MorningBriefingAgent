import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.litellm import LiteLLMModel
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load environment variables
load_dotenv()

# Google API Scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar.readonly'
]

def get_google_credentials():
    """Handles OAuth flow and gets Google API credentials."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return creds

@tool
def check_gmail(hours_back: int = 12) -> str:
    """Fetches unread emails from the last specified hours using Gmail API."""
    try:
        creds = get_google_credentials()
        service = build('gmail', 'v1', credentials=creds)
        
        # Calculate time string for Gmail query
        time_limit = int((datetime.now() - timedelta(hours=hours_back)).timestamp())
        query = f"is:unread after:{time_limit}"
        
        results = service.users().messages().list(userId='me', q=query, maxResults=20).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return "No unread emails found."
            
        email_data = []
        for msg in messages:
            msg_details = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata', 
                metadataHeaders=['Subject', 'From', 'Date']
            ).execute()
            
            headers = msg_details.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
            sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown Sender")
            date = next((h['value'] for h in headers if h['name'] == 'Date'), "Unknown Date")
            snippet = msg_details.get('snippet', '')[:200]
            
            email_data.append(f"From: {sender}\nSubject: {subject}\nDate: {date}\nSnippet: {snippet}")
            
        return "\n\n".join(email_data)
    except Exception as e:
        return f"Error checking Gmail: {str(e)}"

@tool
def check_calendar(hours_ahead: int = 24) -> str:
    """Fetches upcoming events for the next specified hours using Google Calendar API."""
    try:
        creds = get_google_credentials()
        service = build('calendar', 'v3', credentials=creds)
        
        now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        time_max = (datetime.utcnow() + timedelta(hours=hours_ahead)).isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary', timeMin=now, timeMax=time_max,
            maxResults=20, singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return "No upcoming events found."
            
        event_data = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            title = event.get('summary', 'No Title')
            location = event.get('location', 'No Location')
            attendees = [a.get('email') for a in event.get('attendees', []) if 'email' in a]
            
            event_data.append(f"Event: {title}\nStart: {start}\nEnd: {end}\nLocation: {location}\nAttendees: {', '.join(attendees)}")
            
        return "\n\n".join(event_data)
    except Exception as e:
        return f"Error checking Calendar: {str(e)}"

@tool
def check_slack(hours_back: int = 12, max_channels: int = 5) -> str:
    """Fetches recent messages from top active channels using Slack SDK."""
    try:
        token = os.getenv("SLACK_BOT_TOKEN")
        if not token:
            return "Error: SLACK_BOT_TOKEN not found in environment variables."
            
        client = WebClient(token=token)
        oldest_time = (datetime.now() - timedelta(hours=hours_back)).timestamp()
        
        channels_result = client.conversations_list(types="public_channel,private_channel", exclude_archived=True)
        channels = channels_result.get('channels', [])
        
        slack_data = []
        channels_processed = 0
        
        for channel in channels:
            if channels_processed >= max_channels:
                break
                
            try:
                history = client.conversations_history(channel=channel['id'], oldest=str(oldest_time), limit=5)
                messages = history.get('messages', [])
                
                if messages:
                    channel_name = channel.get('name', 'Unknown')
                    msg_texts = [m.get('text', '') for m in messages[:5] if 'subtype' not in m] # Ignore system messages
                    
                    if msg_texts:
                        slack_data.append(f"Channel: #{channel_name}\nMessages:\n- " + "\n- ".join(msg_texts))
                        channels_processed += 1
            except SlackApiError as e:
                if e.response["error"] == "not_in_channel":
                    continue
                else:
                    slack_data.append(f"Error reading channel {channel.get('name')}: {e.response['error']}")
                    
        if not slack_data:
            return "No recent messages found in Slack."
            
        return "\n\n".join(slack_data)
    except Exception as e:
        return f"Error checking Slack: {str(e)}"

def run():
    model = LiteLLMModel(
        model_id="openrouter/openrouter/free",
        params={
            "max_tokens": 4096,
            "api_key": os.getenv("OPENROUTER_API_KEY"),
            "api_base": "https://openrouter.ai/api/v1"
        }
    )

    system_prompt = """You are an executive assistant agent. You must ALWAYS call all three of your tools (check_gmail, check_calendar, check_slack) in order to gather information. 
    
After observing the results of the tools, synthesize a prioritized morning briefing using exactly these sections:
URGENT
UPCOMING EVENTS
SLACK HIGHLIGHTS
OTHER EMAILS
SUGGESTED ACTIONS

Do not just output raw data. Synthesize it into a clear, readable briefing."""

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[check_gmail, check_calendar, check_slack]
    )

    print("Running Morning Briefing Agent...")
    response = agent("What did I miss? Give me my morning briefing.")
    
    print("\n=== FINAL BRIEFING ===")
    print(response)

if __name__ == "__main__":
    run()
