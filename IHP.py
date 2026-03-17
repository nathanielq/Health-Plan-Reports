# <> Imports <> #
# - Config - #
import config
# - Built In - #
import sys
from datetime import datetime
# - Third Party - #
import paramiko
import base64
import polars as pl
from pathlib import Path
from apiclient import discovery
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import google.oauth2.service_account
from googleapiclient.errors import HttpError
# <> Logging <> #
log_file = config.log_file
sys.stdout = open(config.log_file, 'a')
sys.stderr = sys.stdin
cur_time = datetime.now().strftime("%m-%d %H:%M")
print(f'Starting Flex_IHP at {cur_time}\n')

# <> Updated oauth2 method of creating service account credentials <> #
def Get_Service(service):
    try:
        credential = google.oauth2.service_account.Credentials.from_service_account_file(
        config.service_key, scopes=config.service_scopes, subject=config.gmail_delegated_user_email)
    except:
        print(f'Could not generate service credentials')
    if service == 'email':
        return discovery.build('gmail', 'v1', credentials=credential)
    elif service == 'sheets':
        return discovery.build('sheets','v4', credentials=credential)


# <> Read the IHP Google Sheet for all values <> #
def Get_IHP_Data(service):
    try:
        print('Getting Data..')
        results = service.spreadsheets().values().get(
                spreadsheetId=config.file_id, 
                range=config.sheet_range).execute()
        print('Grabbed data')
        values = results.get("values", [])
    except Exception as e:
        print(f'Could not get data: {e}')

    headers = values[0]
    rows = values[1:]
    # - Empty cells in GSheets are treated as non existent when reading. 
    #   the formula below checks each row and pads it with ''values
    #   until it reaches the same row length as the header length - #
    width = len(headers)
    rows = [r + [''] * (width-len(r)) for r in rows]
    # - Create polars dataframe - #
    hp_df = pl.DataFrame(rows, schema=headers, orient="row")
    key_df = Get_Students_From_Activity_File()
    
    df = Trim_Data(hp_df, key_df)
    return df

def Get_Students_From_Activity_File():
    # - If testing skip paramiko and return test file df - #
    if config.test_flag == 'test':
        print('Running in test mode..')
         # - Read in csv to pl df - #
        key_df = pl.read_csv(config.test_download_path, separator=',')
        # - Select only necessary columns - #
        key_df = key_df.select(pl.col('SIS ID'), pl.col('Teacher FN'), pl.col('Teacher LN'), pl.col('CUT Status'), pl.col('Flex Period'))
        return key_df
    print('Running in Production Mode')
    # - Get Flex_Attendance_Full from Securly file server - #
    with paramiko.SSHClient() as ssh:
        # - Open known hosts file and load that here - #
        try:
            ssh.load_host_keys(config.known_hosts)
        except FileNotFoundError as e:
            print(f'Could not load host keys file:\n {e}')
        # - Connect to the sftp server and get the flex_activities file - #
        try:
            ssh.connect(username=config.username, hostname=config.host, password=config.password, port=22)
            with ssh.open_sftp() as sftp:
                sftp.get(config.get_path, config.download_path)
                print('Got File from server')
        except paramiko.ssh_exception.AuthenticationException as e:
            print(f"Could not Authenticate to server: {e}")
    
    # - Read in csv to pl df - #
    key_df = pl.read_csv(config.download_path, separator=',')
    # - Select only necessary columns - #
    key_df = key_df.select(pl.col('SIS ID'), pl.col('Teacher FN'), pl.col('Teacher LN'), pl.col('CUT Status'), pl.col('Flex Period'))
    return key_df

# <> Function trim down to only necessary data <> #
def Trim_Data(result, key_df):
    # - Select Only Necessary columns - #
    columns = config.columns
    result = result.select(columns)
    # - filter to only show non empty health plan notes - #
    result = result.filter(pl.any_horizontal(pl.col('Health Plan Notes')!='', pl.col('Active Alerts')!=''))
    # -  filter to only have students that are not manually excluded and in gator time- #
    key_df = key_df.filter(pl.any_horizontal(pl.col('CUT Status')!= 'Manually excluded'), pl.col('Flex Period')!='After School Clubs')
    # - Join the keys_df to the result_df via matching student ids - #
    result = result.join_where(key_df, pl.col('Student Number').cast(pl.String) == pl.col('SIS ID').cast(pl.String))
    # - Drop columns containing student ID (not relevant) - #
    result = result.drop(['Student Number', 'SIS ID'])
    class_lists = result.partition_by('Teacher LN')
    columns.append('Teacher LN')
    columns.remove('Student Number')
    return class_lists

# <> Use Gmail API for greater security <> #
def Send_Email(body, teacher_name, teacher_email, email_service):
    try:
        # - Create the email message - #
        message = MIMEMultipart('related')
        # - Test Mode - #
        if config.test_flag == 'test':
            message['To'] = config.test_email
            message['Subject'] = f'[TEST] IHP Reports {teacher_name}'
        # - Production Mode - #
        elif config.test_flag == 'prod':
            message["To"] = teacher_email
            message['Subject'] = f'IHP Reports for {teacher_name}'
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

        # - Conver the misd logo png to mimeimage so it can be in the email - #
        img_bytes = Path("./0.png").read_bytes()
        img = MIMEImage(img_bytes, _subtype="png")
        img.add_header("Content-ID","<logo>")
        img.add_header("Content-Disposition", "inline", filename="0.png")
        message.attach(img)

        # - Properly encoded message for Gmail (base64) - #
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        # - raw text for final message - #
        create_message = {'raw': encoded_message}
        # - send the actual message currently impersonating my email - #
        send_message = (
            email_service.users()
            .messages()
            .send(userId='me', body=create_message).execute()
        )
    except HttpError as error:
        print(f'An error Occurred: {error}')
        send_message = None
    print(send_message)

# <> I am a genius and remembered ASMUpload grabs legal names and emails in a csv from Q every night <> #
def Get_Teacher_Emails():
    # - read in as df through polars PL - #
    staff_df = pl.read_csv(config.staff_file, separator=',')
    # - Grab necessary columns - #
    staff_df = staff_df.select(pl.col('first_name'),pl.col('last_name'), pl.col('email_address'))
    # - Convert columns to list of dicts - #
    mapping_list = staff_df.to_dicts()
    # - modify mapping_list to contain a full name key,value pair from first_name last_name values - #
    for mapping in mapping_list:
        mapping['full_name'] = mapping['first_name'].lower().strip() + ' ' + mapping['last_name'].lower().strip()
    return mapping_list
        
# <> Put email for each teacher together before being sent <> #
def Build_Email_Template(class_dfs):
    # - Generate the Credentials for admin access
    email_service = Get_Service('email')
    email_list = Get_Teacher_Emails()
    counts = {'total num': 0, 'matched_emails': 0, 'unmatched_emails': 0}
    teacher_list = []
    # - The total df is split into individual classes. Iterate through those classes - #
    for classroom in class_dfs:
        print(classroom)
        counts['total num'] += 1
        body = config.body
        # - Combine all columns into a single struct in a new column named 'Students' - #
        classroom = classroom.select(pl.struct(pl.all()).alias('Students'))
        # - Convert to a python list - #
        student_list = classroom["Students"].to_list()
        # - Teacher_name for building contacts - #
        teacher_name = student_list[0].get('Teacher FN') + ' ' + student_list[0].get('Teacher LN')
        # - Get the email of the Gator Time Teacher - #
        teacher_email = next((email.get('email_address') for email in email_list if teacher_name.lower()
                              .strip() == email.get('full_name').lower().strip()), None)
        print(teacher_name, teacher_email)
        teacher_list.append(teacher_email)

        # - Set teacher_email to myself and change subject if teacher_email == None - #
        if teacher_email is None:
            print(f'[Error] Could not get teacher email. Setting it to error_email for error checking..')
            teacher_email = config.error_email
            counts['unmatched_emails'] += 1
        else:
            counts['matched_emails'] += 1

        # - Styling for rounded edges in first row first cell and last row first cell
        last_row_style_1 = ""
        last_row_style_2 = ""
        # - Build a table from each student in the class being a row - #
        rows = []
        for i,student in enumerate(student_list):
            # - Alternating colors - #
            if i % 2 == 0:
                style = "'background-color:#f2f2f2; color: #393e46; padding-top: 5px; padding-bottom: 5px;'"
            else:
                style = "'background-color: #393e46; color:#f2f2f2; padding-top: 5px; padding-bottom: 5px;'"
            # - See above for rounded edges - #
            if i == len(student_list) - 1:
                last_row_style_1 = "'border-radius: 0 0 0 10px; padding-left: 5px;"
                last_row_style_2 = "'border-radius: 0 0 10px 0;'"
            
            # - Build the table - #
            rows.append(f""" 
            <tr style={style}>
                <td style={last_row_style_1} padding-left: 5px;'>{student.get('Full Name (LF)')}</td>
                <td>{student.get("Health Plan Notes")}</td>
                <td style={last_row_style_2}>{student.get("Active Alerts")}</td>
            </tr>""")
        # - add closing tags - #
        body += ''.join(rows) + """
                </tbody>
                </table>
                </div>
            </body>
        </html>"""

        # - format to replace teacher_name variable (it's in config.py) - #
        body = body.format(teacher_name=teacher_name)
        # - send completed table to the Email_List function to be sent via API - #
        Send_Email(body, teacher_name, teacher_email, email_service)
    print(counts)
    email_string = ','.join(teacher_list)
    try:
        with open(config.teacher_email_path, 'w', encoding='utf-8') as csv:
            csv.write(email_string)
            print(f'Wrote {len(teacher_list)} emails to teacher_emails.csv')
    except FileNotFoundError as e:
        print(f"Could not find teacher_email.csv: {e}")
    except PermissionError as e:
        print(f"Could not write to teacher_emails.csv: {e}")
    except Exception as e:
        print(f"Could not write teacher_list to teacher_emails.sv: {e}")

# <> Main Calls <> #
if __name__ == '__main__':
    sheets_service = Get_Service('sheets')
    class_dfs = Get_IHP_Data(sheets_service)
    # - Send email to teachers - #
    Build_Email_Template(class_dfs)
    print('\nFinished Running Flex_IHP.py\n')