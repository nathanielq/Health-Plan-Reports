# <> Flex_IHP Config File <> #
# - Imports - #
import keyring
import os
# <> Test Flag <> #
test_flag = 'prod'
# <> Flex Attendance File <> #

# <> SFTP Connection <> #
host = 'HOSTNAME'
username = 'USERNAME'
# - Password stored via Windows Credential Manager - #
password = keyring.get_password(username='WINDOWS_CREDENTIALS_USERNAME', service_name='WINDOWS_CREDENTIALS_SERVICE_NAME')
known_hosts = os.path.join(os.path.expanduser("~"), '.ssh', 'known_hosts')

# - File Paths - #
local_path = 'NAME_OF_LOCAL_FILE'
get_path = 'SFTP_FILE_PATH'
test_download_path = 'LOCAL_PATH_FOR_TESTING'
staff_file = 'PATH_FOR_TEACHER_EMAILS'
download_path = 'DOWNLOAD_PATH'

# - Log File - #
log_file = 'LOG_FILE_PATH'

# <> Google Variables <> #
# - Google API Scope - #
service_scopes = ['https://www.googleapis.com/auth/gmail.send',
                  'https://www.googleapis.com/auth/spreadsheets']
# - Google API Token and Creds file paths - #
# - Any changes to scope will require deleting creds and then running the auth flow again - #
# - creds/keys/tokens should be stored in project directory - #
service_key = '\\Flex_IHP\\service_account_key.json'
gmail_delegated_user_email = 'EMAIL_TO_SEND_FROM'
file_id = 'GOOGLE_SHEET_FILE_ID'
sheet_name = 'SHEET_NAME'
sheet_range = "SHEET_RANGE"

# - File Variables - #
columns = ['Student Number','Full Name (LF)', 'Health Plan Notes', 'Active Alerts']

# <> Email Builder <> #
error_email = 'ERROR_EMAIL'
test_email = 'TEST_EMAIL'
from_email = 'FROM_EMAIL'
cc_emails = 'CC_EMAIL_STRING_NOT_A_LIST'
# - Start the email template here. Build in the main python after - #
body = """
    <html lang='en-US'>
    <head>
            <style>
            body{{background-color: #f2f2f2; color: #393e46; text-align:center;}}
            h1{{text-align: center; font-family: Monospace;}}
            table.table{{
            margin-top: 0;
            border: 2px solid black;
            border-radius: 10px;
            border-collapse: separate;
            border-spacing: 0;
            width: 100%;
            }}

            th, td{{
                padding: 8px;
                vertical-align: top;
            }}
            .logo{{vertical-align: bottom;}}
            .email_body{{align: center;}}
        </style>
    </head>
    <body>
    <div class = 'email_body'>
        <h1>
            <img src="cid:logo" width="50" height="50" class="logo">
            <strong>Flex Period Student IHPs for {teacher_name}</strong>
            <img src="cid:logo" width="50" height="50" class="logo"> 
        </h1>
        <table class='table' role='presentation'> 
            <thead>
                <tr style='background-color: #f95959; font-size: 20px;'>
                    <th scope="col" style="border-radius: 10px 0 0 0; margin-right: 20px;">Student</th>
                    <th scope="col">Health Plan Notes</th>
                    <th scope='col'  style="border-radius: 0 10px 0 0" >Active Alerts</th>
                </tr>
            </thead>
            <tbody>
            """
row_template = """ 
            <tr style={style}>
                <td style={final_row_1} padding-left: 5px;'>{student_name}</td>
                <td>{hp_notes}</td>
                <td style={final_row_2}>{alert}</td>
            </tr>"""

table_closer = """
                </tbody>
                </table>
                </div>
            </body>
        </html>"""

even_row = "'background-color:#f2f2f2; color: #393e46; padding-top: 5px; padding-bottom: 5px;'"
odd_row = "'background-color: #393e46; color:#f2f2f2; padding-top: 5px; padding-bottom: 5px;'"

final_row_1 = "'border-radius: 0 0 0 10px; padding-left: 5px;"
final_row_2 = "'border-radius: 0 0 10px 0;'"