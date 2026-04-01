# <> Imports <> #
# - Config - #
import config
# - Built In - #
import sys
import concurrent.futures
from datetime import datetime
from dataclasses import dataclass
# - Third Party - #
import paramiko
import base64
import polars as pl
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from googleapiclient import discovery
import google.oauth2.service_account
from googleapiclient.errors import HttpError

# <> Logging <> #
sys.stdout = open(config.log_file, 'a', encoding='utf-8')
sys.stderr = sys.stdout
cur_time = datetime.now().strftime("%m-%d %H:%M")
print(f'Starting Flex_IHP at {cur_time}\n')

# <> Class for making Google operations <> #
class Google_Service:
    def __init__(self, service):
        self.service = self.get_service(service)
        
    # <> Updated oauth2 method of creating service account credentials <> #
    def get_service(self, service):
        try:
            credential = google.oauth2.service_account.Credentials.from_service_account_file(
            config.service_key, scopes=config.service_scopes, subject=config.gmail_delegated_user_email)
        except Exception as e:
            raise Exception(f'Terminating program: {e}')
        # - Allow for creating email or sheets creds - #
        if service == 'email':
            return discovery.build('gmail', 'v1', credentials=credential)
        elif service == 'sheets':
            return discovery.build('sheets','v4', credentials=credential)
    
    # <> Read the IHP Google Sheet for all values <> #
    def get_ihp_data(self):
        try:
            print('Getting Data..')
            results = self.service.spreadsheets().values().get(
                    spreadsheetId=config.file_id,
                    range=config.sheet_range).execute()
            print('Grabbed data')
            values = results.get("values", [])
        except Exception as e:
            raise Exception(f'Could not get data: {e}')
        
        headers = values[0]
        rows = values[1:]
        width = len(headers)
        # - Fill empty rows to prevent errors - #
        rows = [r + [''] * (width-len(r)) for r in rows]
        # - return created dataframe - #
        return pl.DataFrame(rows, schema=headers, orient="row")

    # <> Use Gmail API for greater security <> #
    def send_email(self, body, teacher_name, teacher_email):
        # - Create the email message - #
        message = MIMEMultipart('related')
        # - Test Mode - #
        if config.test_flag == 'test':
            message['To'] = config.test_email
            message['Subject'] = f'[TEST] Gator Time IHP Reports {teacher_name}'
        # - Production Mode - #
        elif config.test_flag == 'prod':
            message["To"] = teacher_email
            message['Subject'] = f'Gator Time IHP Reports for {teacher_name}'
            message['Cc'] = config.cc_emails
        message['From'] = config.from_email
        
        # - if there was an error with the email gathering, send to myself with changed subject line - #
        if teacher_email == config.error_email:
            message['Subject'] = f'Could not locate teacher_email for {teacher_name}'
                
        # - Configure it to accept HTML - #
        alt = MIMEMultipart("alternative")
        html_body = MIMEText(body, 'html')
        alt.attach(html_body)
        message.attach(alt)

        # - Convert the MISD logo png to mimeimage so it can be in the email - #
        img_bytes = Path("./0.png").read_bytes()
        img = MIMEImage(img_bytes, _subtype="png")
        img.add_header("Content-ID","<logo>")
        img.add_header("Content-Disposition", "inline", filename="0.png")
        message.attach(img)

        # - Properly encoded message for Gmail (base64) - #
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        # - raw text for final message - #
        create_message = {'raw': encoded_message}
        # - send the actual message impersonating datadashboard - #
        try:
            send_message = (
                self.service.users()
                .messages()
                .send(userId='me', body=create_message).execute()
            )
        except HttpError as error:
            print(f'An error Occurred: {error}')
            send_message = None
        print(send_message)

# <> Counts Object to Track success/failures <> #
@dataclass
class Counts:
    matched: int = 0
    unmatched: int = 0

    def match_count(self):
        self.matched += 1
    def unmatch_count(self):
        self.unmatched += 1
    @property
    def total_num(self):
        return self.matched + self.unmatched    

# <> Function to get Student Flex Period Selections <> #
def get_students_from_activity_file():
    # - If testing skip paramiko and return test file df - #
    if config.test_flag == 'test':
        print('Running in test mode..')
        key_df = pl.read_csv(config.test_download_path, separator=',', encoding='utf-8')
        key_df = key_df.select(pl.col('SIS ID').cast(pl.String), pl.col('Teacher FN'), pl.col('Teacher LN'), pl.col('CUT Status'), pl.col('Flex Period'))
        return key_df

    # - Production Mode - #
    print('Running in Production Mode')
    # - Get Flex_Attendance_Full from Securly file server - #
    with paramiko.SSHClient() as ssh:
        try:
            ssh.load_host_keys(config.known_hosts)
        except FileNotFoundError as e:
            raise Exception(f'Terminating program. Could not load host keys file:\n {e}')
        try:
            ssh.connect(username=config.username, hostname=config.host, password=config.password, port=22)
            with ssh.open_sftp() as sftp:
                sftp.get(config.get_path, config.download_path)
                print('Got File from server')
        except paramiko.ssh_exception.AuthenticationException as e:
            ssh.close()
            raise Exception (f"Could not Authenticate to server: {e}")
        except FileNotFoundError as e:
            raise Exception(f'Could not locate Securly file: {e}')
    # - Read in the new file to df - #
    key_df = pl.read_csv(config.download_path, separator=',', encoding='utf-8')
    key_df = key_df.select(pl.col('SIS ID').cast(pl.String), pl.col('Teacher FN'), pl.col('Teacher LN'), pl.col('CUT Status'), pl.col('Flex Period'))
    return key_df

# <> Function trim down to only necessary data <> #
def trim_data(result, key_df):
    columns = config.columns
    columns[0] = pl.col('Student Number').cast(pl.String)
    result = result.select(columns)
    # - Filter result to only rows with IHPs | filter key to only results that are in a flex class #
    result = result.filter(pl.any_horizontal(pl.col('Health Plan Notes')!='', pl.col('Active Alerts')!=''))
    key_df = key_df.filter((pl.col('CUT Status')!= 'Manually excluded') & (pl.col('Flex Period')!='After School Clubs'))
    # - Combine dfs by student number. Drop columns and track useful ones. Split into classes by teach name - #
    key_df = key_df.rename({'SIS ID': 'Student Number'})
    result = result.join(key_df, on='Student Number')
    result = result.drop(['Student Number'])
    class_lists = result.partition_by('Teacher LN')
    return class_lists

# <> I am a genius and remembered ASMUpload grabs legal names and emails in a csv from Q every night <> #
def get_teacher_emails():
    try:
        staff_df = pl.read_csv(config.staff_file, separator=',')
    except Exception as e:
        raise Exception(f'Could not get teacher_emails: {e}')
    staff_df = staff_df.select(pl.col('first_name'),pl.col('last_name'), pl.col('email_address'))
    mapping_list = staff_df.to_dicts()
    # - modify mapping_list to contain a full name key,value pair from first_name last_name values - #
    for mapping in mapping_list:
        mapping['full_name'] = mapping['first_name'].lower().strip() + ' ' + mapping['last_name'].lower().strip()
    return mapping_list

# <> Function to create the rows for each classroom <> #
def build_rows(student_list):
    rows = []
    for i,student in enumerate(student_list):
        # - Alternating colors - #
        if i % 2 == 0: style = config.even_row
        else: style = config.odd_row
        # - Round edges of last row - #
        if i == len(student_list) - 1:
            final_row_1 = config.final_row_1
            final_row_2 = config.final_row_2
        else:
            final_row_1 = ""
            final_row_2 = ""

        # - Build Each Row - #
        student_name = student.get('Full Name (LF)')
        hp_notes = student.get('Health Plan Notes')
        alert = student.get('Active Alerts')
        row_template = config.row_template.format(
            style=style,
            final_row_1=final_row_1,
            student_name=student_name,
            hp_notes = hp_notes,
            final_row_2=final_row_2,
            alert=alert
        )
        rows.append(row_template)
    return rows

# <> Get the individual Teacher Name and Teacher Email for a classroom <> #
def get_teacher_info(student_list, email_list):
    teacher_name = student_list[0].get('Teacher FN') + ' ' + student_list[0].get('Teacher LN')
    teacher_email = next(
        (email.get('email_address') for email in email_list if teacher_name.lower()
        .strip() == email.get('full_name').lower().strip()), None)
    print(teacher_name, teacher_email)
    return teacher_name, teacher_email

# <> Write a list of emails that were sent to for deletion later on <> #
def write_emails_to_delete(teacher_list):
    email_string = ','.join(teacher_list)
    try:
        with open(config.teacher_email_path, 'w', encoding='utf-8') as csv:
            csv.write(email_string)
            print(f'Wrote {len(teacher_list)} emails to teacher_emails.csv')
    except Exception as e:
        raise Exception(f"Could not write to teacher_emails.csv {e}")

# <> Small function to build individual email_service and call Send_Email <> #
def send_email_func(body, name, email):
    email_service = Google_Service('email')
    email_service.send_email(body, name, email)

# <> exceute email creation and sending <> #
def email_executor(class_dfs, counter):
    email_list = get_teacher_emails()
    teacher_list = []
    futures = []
    # <> Process and Send Emails Concurrently <> #
    with concurrent.futures.ThreadPoolExecutor(max_workers = 2) as executor:
        # - The total df is split into individual classes. Iterate through those classes - #
        for classroom in class_dfs:
            # - Combine all columns into a single struct in a new column named 'Students' and make it a list - #
            classroom = classroom.select(pl.struct(pl.all()).alias('Students'))
            student_list = classroom["Students"].to_list()
            # - Teacher_name for building contacts - #
            teacher_name, teacher_email = get_teacher_info(student_list, email_list)
            # - Set teacher_email to myself and change subject if teacher_email == None - #
            if teacher_email is None:
                print(f'[Error] Could not get teacher email. Setting it to error_email for error checking..')
                teacher_email = config.error_email
                counter.unmatch_count()
            else:
                counter.match_count()
                teacher_list.append(teacher_email)
            # - Format teacher_name before row template is added - #
            body = config.body.format(teacher_name=teacher_name)
            # - Build a table from each student in the class being a row - #
            rows = build_rows(student_list)
            # - add closing tags - #
            body += ''.join(rows) + config.table_closer
            future = executor.submit(send_email_func, body, teacher_name, teacher_email)
            futures.append(future)
    # - Write a list of emails sent to so they can have their emails deleted later - #
    write_emails_to_delete(teacher_list)
    return futures

# <> Main Calls <> #
if __name__ == '__main__':

    # - Get IHP and Flex Period Data - #
    sheets_service = Google_Service('sheets')
    ihp_df = sheets_service.get_ihp_data()
    key_df = get_students_from_activity_file()
    class_dfs = trim_data(ihp_df, key_df)

    # - Email the data - #
    counter = Counts()
    futures = email_executor(class_dfs, counter)
    print(f'Matched Emails: {counter.matched} | Unmatched Emails: {counter.unmatched} | Total: {counter.total_num}')
    for fut in futures:
        if fut != 'None': print(fut.result())
    print('\nFinished Running Flex_IHP.py\n')