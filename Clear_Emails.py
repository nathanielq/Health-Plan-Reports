# <> Imports <> #
# - Local File - #
# - First party - #
import sys
from datetime import datetime
# - Third Party - #
import google.oauth2.service_account
from apiclient import discovery
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# <> Variables <> #
gmail_scope = ['https://www.googleapis.com/auth/gmail.modify']
teacher_emails = 'EMAILS_LIST_CSV_PATH'
trash_service_key = 'SERVICE_KEY_PATH'
log_file = 'FILE_PATH'

# <> Logging <> #
sys.stdout = open(log_file,'a', encoding='utf-8')
sys.stderr = sys.stdout
today = datetime.today()
print(f'Starting Clear_Emails at {today}\n')

# <> Open teacher emails file and read in emails <> #
def Get_Emails():
    with open(teacher_emails, 'r', encoding='utf-8-sig') as file:
        reader = file.read()
    return reader.split(',')

# <> Updated oauth2 method of creating service account credentials <> #
def Get_Service(user):
    try:
        credential = google.oauth2.service_account.Credentials.from_service_account_file(
        trash_service_key, scopes=gmail_scope, subject=user) # Delegate inbox of each user to the service account #
    except:
        print(f'Could not generate service credentials')
    return discovery.build('gmail', 'v1', credentials=credential)

# <> Actions on messages have to be done through ID so start with querying the message for the ID <> #
def Get_Email_ID(service):
    try:
        results = service.users().messages().list(userId='me', q='from:"FROM_ADDRESS" subject:"IHP Reports for" in:"anywhere"').execute()
        message_ids = results.get('messages', [])
    except HttpError as e:
        print(f'Failed to find email id: {e}')
    return message_ids

# <> Delete the email from user inbox via id <> #
def Delete_Emails(service, id):
    try:
        results = service.users().messages().trash(userId='me', id=id).execute()
        print(results)
    except HttpError as e:
        print(f'Failed to delete email: {e}')

# <> Get list of emails to impersonate <> #
email_list = Get_Emails()

# <> Iterate through list, generate impersonated creds, find the email ID via subject and then delete <> #
for email in email_list:
    print(f'\n{email}\n')
    service = Get_Service(email.strip().lower())
    ids = Get_Email_ID(service)
    for id_dict in ids:
        id = id_dict.get('id')
        Delete_Emails(service,id)

print(f'\nFinished Running Clear_Emails.py')
