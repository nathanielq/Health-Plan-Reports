# Health-Plan-Reports
Tech Stack - Python, Polars, Google Sheets API, Gmail API, Google Cloud Platform, HTML/CSS

Overview:
During free periods, students self-select into classrooms meaning teachers have no static roster and no access to health plan data for the students in their care. In an emergency, that missing information could be critical. This script solves that by automatically delivering each teacher a personalized report of health plans for every student assigned to their free period that day.

How it works:
Script that uses Google sheets API to read in student health plan data. Polars is used to trim the data and combine with another sheet of student rostering, such that students are mapped to classrooms via student number in a manner that provides each teacher with a list of students under their watch during a free period with a health plan. This is then put into dynamic html tables that are sent in emails using Gmail API to each teacher. Number of teachers and the number of students needing to be included are dynamic and change daily. This is built to handle those changes. 

SETUP:
Create project in Google Cloud Platform with Service Account that has Google Sheets API and GMail API enabled. Create a service account and download the service account key.json file (service_account_key.json.example contains a link for instructions on setting up a service account with Python use in mind). In your Google Workspace Admin Console give the service account the gmail.modify and spreadsheet.readonly scopes in domain-wide delegation. Use the Google libraries to build a service object for the service account to use in the script. See IHP.py for reference. The file is triggered via Windows Task Scheduler daily at a set time prior to the free-period beginning.
